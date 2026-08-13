"""
🌊 心境配置中枢（Config Singleton）

**数据源优先级（从高到低）**：
1. 环境变量（XINHAI_* 前缀）— 最高优先级，用于敏感信息/临时覆盖
2. Rust 引擎 global_config 表 — 唯一持久化来源（通过 sync_from_engine 注入）
   注：引擎返回的记录结构可能为 { id, config_json(JSON字符串), created_at, updated_at }，
        Python 侧统一通过 _unwrap_engine_config 解包为扁平 {key: value}。
3. 本地代码兜底默认值 — 仅保证启动不崩溃，不做业务默认

**写入策略**：
- Python 侧永不写入默认配置文件（resources/global.json 或任何默认 JSON）。
- 所有保存都走 engine.global_config_update，由 Rust 引擎持久化到 global_config 表。

**热重载约定**：
- 按需触发：仅在外界显式调用 reload() 时重新加载，任何局部字段变更不自动触发全量
- 全部生效：只要 reload() 检测到 diff，无论是什么字段，都 increment_config_version
"""
import json
import os
import threading
from typing import Any, Dict, Optional
from app.common import paths as pa
from app.common import values as va
from app.common import vendor as ve
from app.common import model as mo
from app.common import keys as ke
from app.utils.text_utils import parse_comma_list
from app.utils.logger import FallbackLogger

# ============================================================
# 模块初始化阶段就设置第三方库的环境变量屏蔽开关
# 必须早于任何 huggingface_hub / transformers / mlflow 被 import 之前
# 同时在 _load() 开头再调用一次做双保险
# ============================================================
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("DISABLE_MLFLOW", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")


def _unwrap_engine_config(raw: Any) -> Dict[str, Any]:
    """
    解包引擎返回值：优先返回 config_json 内部扁平 {XINHAI_KEY: value}，
    若已是扁平 dict 或 JSON 字符串则直接返回。永远返回 dict（空 dict 兜底）。
    """
    if isinstance(raw, str):
        try:
            stripped = raw.strip()
            return _unwrap_engine_config(json.loads(stripped)) if stripped else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    if not isinstance(raw, dict):
        try:
            return dict(raw) if hasattr(raw, "items") else {}
        except Exception:
            return {}
    if "config_json" in raw and ("id" in raw or "created_at" in raw or "updated_at" in raw):
        inner = raw.get("config_json")
        if isinstance(inner, dict):
            return inner
        if isinstance(inner, str) and inner.strip():
            try:
                parsed = json.loads(inner)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, ValueError):
                return {}
        if inner is not None and hasattr(inner, "items"):
            try:
                return dict(inner)
            except Exception:
                return {}
        return {}
    return raw


class Config:
    """全局配置单例（线程安全 DCL 双检锁）"""

    CHINESE_NAME = "心海配置中枢"

    _instance = None
    _lock = threading.Lock()

    __slots__ = (
        "_initialized",
        "_raw_config_cache",  # Rust engine 同步下来的原始 JSON 字典（唯一持久化来源）
        "DATA_ROOT",

        # ========== 1. 路径 & 文件 ==========
        "LOGS_DIR",
        "LOGS_FALLBACK_DIR",
        "IMAGE_DIR",
        "VIDEO_DIR",
        "AUDIO_DIR",
        "LYRIC_DIR",
        "SQLITE_DIR",
        "MODEL_DIR",
        "DB_PATH",
        "PATH_FILE_PROSE_REFINER_DB",
        "PATH_FILE_INDEX_HTML",
        "PATH_FILE_STOPWORDS_TXT",
        "PATH_FILE_JIEBA_USERDICT_TXT",

        # ========== 2. 文本生成配置（Text 域：厂商+模型+专属参数）==========
        "TEXT_DEFAULT_VENDOR",
        "TEXT_DEFAULT_MODEL",
        "TEXT_API_TIMEOUT",
        "TEXT_PARAMS",
        "REASONING_AUTO_INJECT",
        "REASONING_EFFORT_MAP",
        # ========== 2.1 厂商级密钥（账号级，一个厂商一把 key，跨域通用）==========
        "DEEPSEEK_API_KEY",
        "TONGYI_API_KEY",
        # ========== 2.2 音频/图像/视频通道（每通道独立厂商+模型选择）==========
        "AUDIO_DEFAULT_VENDOR",
        "AUDIO_DEFAULT_MODEL",
        "IMAGE_DEFAULT_VENDOR",
        "IMAGE_DEFAULT_MODEL",
        "VIDEO_DEFAULT_VENDOR",
        "VIDEO_DEFAULT_MODEL",

        # ========== 3. LangSmith ==========
        "LANGSMITH_ENABLED",
        "LANGSMITH_API_KEY",
        "LANGSMITH_PROJECT",
        "LANGSMITH_ENDPOINT",

        # ========== 4. 段落切分 ==========
        "PARAGRAPH_TARGET_CHARS",
        "PARAGRAPH_TOLERANCE",
        "PARAGRAPH_SPLIT_MIN_CHARS",
        "PARAGRAPH_SPLIT_TARGET_CHARS",
        "PARAGRAPH_SPLIT_SENTENCE_PATTERN",

        # ========== 5. 日志 ==========
        "LOG_KEEP_DAYS",
        "LOG_MAX_BYTES",
        "LOG_BACKUP_COUNT",

        # ========== 6. 并发 ==========
        "MAX_LLM_STEP_CONCURRENCY",
        "CURRENT_LLM_STEP_CONCURRENCY",
        "MEDIUM_LLM_STEP_CONCURRENCY",
        "MAX_BATCH_TASK_CONCURRENCY",
        "CURRENT_BATCH_TASK_CONCURRENCY",
        "MEDIUM_BATCH_TASK_CONCURRENCY",

        # ========== 7. 重试 ==========
        "DEFAULT_RETRY_CONFIG",
        "GLOBAL_MAX_RETRIES",

        # ========== 8. 存储 & 缓存 ==========
        "STORAGE_BACKEND",
        "LLM_CACHE_MAX_SIZE",
        "LLM_CACHE_TTL",
        "REDIS_HOST",
        "REDIS_PORT",
        "REDIS_DB",
        "REDIS_PASSWORD",
        "REDIS_TIMEOUT",

        # ========== 9. 通知 ==========
        "NOTIFICATION_ENABLED",
        "NOTIFICATION_CHANNELS",
        "EMAIL_SMTP_SERVER",
        "EMAIL_PORT",
        "EMAIL_USERNAME",
        "EMAIL_PASSWORD",
        "EMAIL_TO",
        "FEISHU_WEBHOOK_URL",
        "FEISHU_AT_USER_IDS",
        "WECOM_WEBHOOK_URL",
        "WECOM_AT_USER_IDS",

        # ========== 10. 图片平台 ==========
        "UNSPLASH_ACCESS_KEY",
        "UNSPLASH_BASIC_PATH",
        "PEXELS_ACCESS_KEY",
        "PEXELS_BASIC_PATH",

        # ========== 11. 全局监控 & 指标 ==========
        "GLOBAL_ENABLE_METRICS",

        # ========== 12. SSE & Token 扩容 ==========
        "PROXY_BACKEND_SSE_URL",
        "SSE_HEARTBEAT_INTERVAL",
        "MAX_TOKENS_EXPANSION_FACTOR",
        "MAX_LENGTH_RETRIES",
        "FACTOR_INCREMENT",
        "FULL_TEXT_TOKENS_RATIO",
        "IMAGE_COUNT",
        "REFRESH_INTERVAL_MS",
        "HEADER_BG_IMAGE_ID",
        "FOOTER_BG_IMAGE_ID",
        "DEFAULT_BG_IMAGE_ID",
        "NOVEL_BG_IMAGE_ID",
        "MESSAGE_WALL_BG_IMAGE_ID",

        # ========== 13. 本地轻量模型 ==========
        "LOCAL_MODEL_MAX_MEMORY_MB",
        "LOCAL_MODEL_MONITOR_INTERVAL",
        "LOCAL_MODEL_MEMORY_THRESHOLD",
        "LOCAL_MODEL_MAX_EVICTION_ATTEMPTS",
        "LOCAL_MODEL_CONCURRENCY",
        "LOCAL_MODELS_DEFINITION",
        "ENABLE_TEXT_ANALYSIS_TASKS",
        "TEXT_ANALYSIS_TASKS",

        # ========== 14. 分词 & 文本工具 ==========
        "JIEBA_MIN_WORD_LEN",
        "TEXTRANK_TOP_K",
        "JIEBA_STOPWORDS_PATH",
        "JIEBA_USERDICT_PATH",
        "JIEBA_FILTER_STOPWORDS_DEFAULT",
        "VOCAB_FILTER_MAX_WORDS",
        "VOCAB_FILTER_MAX_FREQWORDS",
        "SEMANTIC_SIMILARITY_THRESHOLD",

        # ========== 16. 谋篇/分卷/定章 能力注入内容限制 ==========
        # 注入配置已改为 values.py 常量，此处不再定义

        # ========== 17. 翻译 API ==========
        "TRANSLATION_PROVIDER",
        "TRANSLATION_FROM",
        "TRANSLATION_TO",
        "TENCENT_TMT_SECRET_ID",
        "TENCENT_TMT_SECRET_KEY",
        "TENCENT_TMT_REGION",
    )

    def __new__(cls):
        # 快速检查，避免不必要的锁竞争
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    instance._raw_config_cache = {}
                    cls._instance = instance
        return cls._instance

    def __init__(self):
        with self._lock:
            if self._initialized:
                return
            self._initialized = True

        FallbackLogger.info("正在初始化心海配置中枢...")
        self._load()

    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        return cls()

    async def sync_from_engine(self, engine: Any) -> bool:
        """
        从 Rust 引擎 global_config 表同步配置（服务启动后调用）。
        注入到 _raw_config_cache，后续 _load() 会自动优先使用。
        对应引擎 lib.rs 的 global_config_get_full / global_config_update 方法。

        关键约定：无论引擎返回的是“行级包装结构”（{id/config_json/created_at/updated_at}）
        还是直接的扁平 KV，此方法统一解包为扁平 dict，再规范化 key 注入缓存。
        Python 侧永不手动写入默认配置文件。

        返回：True 表示内容发生了实际变更；False 表示无变更或同步失败。
        """
        try:
            if engine is None:
                FallbackLogger.warning("sync_from_engine：engine 为空，跳过同步")
                return False
            if not hasattr(engine, "global_config_get_full"):
                FallbackLogger.warning("Rust cognitor wheel 暂未实现 global_config_get_full，跳过同步")
                return False

            raw_data = engine.global_config_get_full()
            FallbackLogger.info(
                f"sync_from_engine 收到原始数据类型：{type(raw_data).__name__}，"
                f"准备解包..."
            )

            # 1) 先解包行级包装（id/config_json/created_at/updated_at 被剥离，只剩内部 KV）
            unwrapped = _unwrap_engine_config(raw_data)

            if not isinstance(unwrapped, dict) or len(unwrapped) == 0:
                FallbackLogger.info("Rust global_config 尚无有效 KV（首次运行或解包为空），保留当前默认")
                with self._lock:
                    if self._raw_config_cache != {}:
                        self._raw_config_cache = {}
                        return True
                return False

            # 2) key 规范化：统一大写，不带 XINHAI_ 前缀时自动补齐（兼容引擎存的语义键）
            normalized: Dict[str, Any] = {}
            skipped = 0
            for k, v in unwrapped.items():
                if not isinstance(k, str):
                    skipped += 1
                    continue
                upper = k.strip().upper()
                if not upper:
                    skipped += 1
                    continue
                if upper.startswith("XINHAI_"):
                    normalized[upper] = v
                else:
                    normalized[f"XINHAI_{upper}"] = v

            if skipped:
                FallbackLogger.warning(
                    f"sync_from_engine：有 {skipped} 条非法 key（空或非字符串）已跳过"
                )

            changed = False
            with self._lock:
                if self._raw_config_cache != normalized:
                    self._raw_config_cache = normalized
                    changed = True

            if changed:
                sample = sorted(normalized.keys())[:5]
                FallbackLogger.info(
                    f"已从 Rust 引擎同步 {len(normalized)} 条配置（内容有更新，sample={sample}...）"
                )
            else:
                FallbackLogger.info("Rust 引擎配置未发生变化，跳过刷新")
            return changed
        except Exception as e:
            FallbackLogger.error(f"sync_from_engine 失败（保留当前配置）：{e}", exc_info=True)
            return False

    def _load(self) -> None:
        """加载配置：优先级 环境变量 > _raw_config_cache（引擎注入）> 代码兜底默认值"""

        # 每次加载都再次应用第三方库的环境变量屏蔽（双保险）
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        os.environ.setdefault("DISABLE_MLFLOW", "1")
        os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

        self._setup_paths()

        # 唯一持久化来源：Rust 注入的缓存字典（为空则兜底空 dict，仅用环境变量+默认值）
        raw_config: Dict[str, Any] = getattr(self, "_raw_config_cache", {}) or {}

        def get_config(key: str, default, cast):
            # 优先级 1：环境变量
            if key in os.environ:
                val = os.environ[key]
                try:
                    if cast == int:
                        return int(val)
                    elif cast == float:
                        return float(val)
                    elif cast == bool:
                        return val.strip().lower() in va.VAL_SUCCESS_FLAG
                    elif cast == dict:
                        parsed = json.loads(val)
                        if isinstance(parsed, dict):
                            return parsed
                        raise ValueError(
                            f"环境变量 {key} 解析结果为 {type(parsed)}，预期为 dict。值: {val}"
                        )
                    elif cast == list:
                        if isinstance(val, str) and val.strip():
                            # 先尝试标准 JSON 数组格式：["a","b"]
                            try:
                                parsed = json.loads(val)
                                if isinstance(parsed, list):
                                    return parsed
                            except (json.JSONDecodeError, ValueError):
                                pass
                            # 兜底：中英文逗号 / 顿号分隔（兼容 "a，b、c,d" 这类混用）
                            fallback = parse_comma_list(val)
                            if fallback:
                                return fallback
                        return default
                    elif cast == str:
                        return val
                    else:
                        return val
                except Exception as e:
                    raise ValueError(
                        f"环境变量 {key} 格式错误且无法解析为 {cast}: {val}. 错误: {e}"
                    )

            # 优先级 2：Rust 引擎同步来的 _raw_config_cache
            raw_val = raw_config.get(key, default)

            # 优先级 3：代码兜底默认值
            if cast == dict:
                if isinstance(raw_val, str):
                    FallbackLogger.warning(
                        f"[配置容错] 检测到 {key} 被错误地存储为字符串类型，正在尝试自动修复..."
                    )
                    try:
                        parsed = json.loads(raw_val)
                        if isinstance(parsed, dict):
                            FallbackLogger.info(f"[配置容错] {key} 修复成功，已转换为字典。")
                            return parsed
                        FallbackLogger.error(
                            f"[配置容错] {key} 解析后仍不是字典 ({type(parsed)})，使用默认值。"
                        )
                        return default
                    except json.JSONDecodeError:
                        FallbackLogger.error(
                            f"[配置容错] {key} 字符串格式非法，无法解析，使用默认值。原始值: {raw_val}"
                        )
                        return default
                elif not isinstance(raw_val, dict):
                    FallbackLogger.error(
                        f"[配置容错] {key} 类型未知 ({type(raw_val)})，使用默认值。"
                    )
                    return default
            elif cast == list and not isinstance(raw_val, list):
                if isinstance(raw_val, str) and raw_val.strip():
                    # 先尝试 JSON 数组格式，失败再兜底按中英文逗号 / 顿号分割
                    try:
                        parsed = json.loads(raw_val)
                        if isinstance(parsed, list):
                            return parsed
                    except json.JSONDecodeError:
                        pass
                    fallback = parse_comma_list(raw_val)
                    if fallback:
                        return fallback
                return default

            return raw_val

        def lower_str(key: str, default: str) -> str:
            """读取字符串配置并统一小写化（厂商/模型标识专用，空值返回空串）"""
            val = get_config(key, default, cast=str)
            if val:
                return str(val).strip().lower()
            return str(default).strip().lower() if default else ""

        # === 2. 文本生成配置（Text 域）===
        self.TEXT_DEFAULT_VENDOR = lower_str("XINHAI_TEXT_DEFAULT_VENDOR", ve.VENDOR_DEEPSEEK)
        self.TEXT_DEFAULT_MODEL = lower_str("XINHAI_TEXT_DEFAULT_MODEL", mo.MODEL_DEEPSEEK_V4_FLASH)
        self.TEXT_API_TIMEOUT = get_config("XINHAI_TEXT_API_TIMEOUT", 300, cast=int)
        self.TEXT_PARAMS = get_config("XINHAI_TEXT_PARAMS", va.VAL_RECOMMENDED_PARAMS, cast=dict)

        # === 2.1 厂商级密钥（账号级，一个厂商一把 key，跨域通用）===
        self.DEEPSEEK_API_KEY = get_config("XINHAI_DEEPSEEK_API_KEY", "请输入密钥", cast=str)
        self.TONGYI_API_KEY = get_config("XINHAI_TONGYI_API_KEY", "请输入密钥", cast=str)

        # === 2.2 音频/图像/视频通道（每通道独立厂商+模型选择）===
        self.AUDIO_DEFAULT_VENDOR = lower_str("XINHAI_AUDIO_DEFAULT_VENDOR", ve.VENDOR_TONGYI)
        self.AUDIO_DEFAULT_MODEL = lower_str("XINHAI_AUDIO_DEFAULT_MODEL", mo.MODEL_COSYVOICE_V1)
        self.IMAGE_DEFAULT_VENDOR = lower_str("XINHAI_IMAGE_DEFAULT_VENDOR", ve.VENDOR_TONGYI)
        self.IMAGE_DEFAULT_MODEL = lower_str("XINHAI_IMAGE_DEFAULT_MODEL", mo.MODEL_Z_IMAGE_TURBO)
        self.VIDEO_DEFAULT_VENDOR = lower_str("XINHAI_VIDEO_DEFAULT_VENDOR", "")
        self.VIDEO_DEFAULT_MODEL = lower_str("XINHAI_VIDEO_DEFAULT_MODEL", "")
        self.REASONING_AUTO_INJECT = get_config(
            "XINHAI_REASONING_AUTO_INJECT", False, cast=bool
        )
        self.REASONING_EFFORT_MAP = get_config(
            "XINHAI_REASONING_EFFORT_MAP",
            {},
            cast=dict,
        )

        # === 3. LangSmith ===
        self.LANGSMITH_ENABLED = get_config(
            "XINHAI_LANGSMITH_ENABLED", False, cast=bool
        )
        self.LANGSMITH_API_KEY = get_config(
            "XINHAI_LANGSMITH_API_KEY", "请输入密钥", cast=str
        )
        self.LANGSMITH_PROJECT = get_config(
            "XINHAI_LANGSMITH_PROJECT", va.VAL_LANGSMITH_PROJECT, cast=str
        )
        self.LANGSMITH_ENDPOINT = get_config(
            "XINHAI_LANGSMITH_ENDPOINT", va.VAL_LANGSMITH_ENDPOINT, cast=str
        )
        if self.LANGSMITH_ENABLED and self.LANGSMITH_API_KEY and "请输入" not in str(self.LANGSMITH_API_KEY):
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = self.LANGSMITH_API_KEY
            os.environ["LANGCHAIN_PROJECT"] = self.LANGSMITH_PROJECT
            os.environ["LANGCHAIN_ENDPOINT"] = self.LANGSMITH_ENDPOINT
            FallbackLogger.info(f"LangSmith 已启用 | 项目: {self.LANGSMITH_PROJECT}")
        elif self.LANGSMITH_ENABLED:
            FallbackLogger.warning("LANGSMITH_ENABLED=true 但未提供有效 API KEY，已强制关闭")
            self.LANGSMITH_ENABLED = False
        else:
            FallbackLogger.info("LangSmith 未启用")

        # === 4. 段落切分 ===
        self.PARAGRAPH_TARGET_CHARS = get_config(
            "XINHAI_PARAGRAPH_TARGET_CHARS", 1350, cast=int
        )
        self.PARAGRAPH_TOLERANCE = get_config(
            "XINHAI_PARAGRAPH_TOLERANCE", 150, cast=int
        )
        self.PARAGRAPH_SPLIT_MIN_CHARS = get_config(
            "XINHAI_PARAGRAPH_SPLIT_MIN_CHARS", 10, cast=int
        )
        self.PARAGRAPH_SPLIT_TARGET_CHARS = get_config(
            "XINHAI_PARAGRAPH_SPLIT_TARGET_CHARS", 300, cast=int
        )
        self.PARAGRAPH_SPLIT_SENTENCE_PATTERN = get_config(
            "XINHAI_PARAGRAPH_SPLIT_SENTENCE_PATTERN",
            r"[。！？…\\.\\!\\?]+",
            cast=str,
        )

        # === 5. 日志 ===
        self.LOG_KEEP_DAYS = get_config(
            "XINHAI_LOG_KEEP_DAYS", va.VAL_LOG_KEEP_DAYS, cast=int
        )
        self.LOG_MAX_BYTES = get_config(
            "XINHAI_LOG_MAX_BYTES", va.VAL_LOG_MAX_BYTES, cast=int
        )
        self.LOG_BACKUP_COUNT = get_config(
            "XINHAI_LOG_BACKUP_COUNT", va.VAL_LOG_BACKUP_COUNT, cast=int
        )

        # === 6. 并发 ===
        self.MAX_LLM_STEP_CONCURRENCY = get_config(
            "XINHAI_MAX_LLM_STEP_CONCURRENCY", 30, cast=int
        )
        self.CURRENT_LLM_STEP_CONCURRENCY = get_config(
            "XINHAI_CURRENT_LLM_STEP_CONCURRENCY", 5, cast=int
        )
        self.MEDIUM_LLM_STEP_CONCURRENCY = get_config(
            "XINHAI_MEDIUM_LLM_STEP_CONCURRENCY", 20, cast=int
        )
        self.MAX_BATCH_TASK_CONCURRENCY = get_config(
            "XINHAI_MAX_BATCH_TASK_CONCURRENCY", 15, cast=int
        )
        self.CURRENT_BATCH_TASK_CONCURRENCY = get_config(
            "XINHAI_CURRENT_BATCH_TASK_CONCURRENCY", 2, cast=int
        )
        self.MEDIUM_BATCH_TASK_CONCURRENCY = get_config(
            "XINHAI_MEDIUM_BATCH_TASK_CONCURRENCY", 10, cast=int
        )

        # === 7. 重试 ===
        self.DEFAULT_RETRY_CONFIG = get_config(
            "XINHAI_DEFAULT_RETRY_CONFIG", va.VAL_DEFAULT_RETRY_CONFIG, cast=dict
        )
        self.GLOBAL_MAX_RETRIES = get_config(
            "XINHAI_GLOBAL_MAX_RETRIES", 10000, cast=int
        )

        # === 8. 存储 & 缓存 ===
        self.STORAGE_BACKEND = get_config(
            "XINHAI_STORAGE_BACKEND", ke.KEY_LOCAL, cast=str
        )
        self.LLM_CACHE_MAX_SIZE = get_config(
            "XINHAI_LLM_CACHE_MAX_SIZE", 4096, cast=int
        )
        self.LLM_CACHE_TTL = get_config("XINHAI_LLM_CACHE_TTL", 7200, cast=int)
        self.REDIS_HOST = get_config("XINHAI_REDIS_HOST", "127.0.0.1", cast=str)
        self.REDIS_PORT = get_config("XINHAI_REDIS_PORT", 6379, cast=int)
        self.REDIS_DB = get_config("XINHAI_REDIS_DB", 0, cast=int)
        self.REDIS_PASSWORD = get_config("XINHAI_REDIS_PASSWORD", "", cast=str)
        self.REDIS_TIMEOUT = get_config("XINHAI_REDIS_TIMEOUT", 5, cast=int)

        # === 9. 通知 ===
        self.NOTIFICATION_ENABLED = get_config(
            "XINHAI_NOTIFICATION_ENABLED", False, cast=bool
        )
        self.NOTIFICATION_CHANNELS = get_config(
            "XINHAI_NOTIFICATION_CHANNELS", va.VAL_NOTIFICATION_CHANNELS, cast=list
        )
        self.EMAIL_SMTP_SERVER = get_config(
            "XINHAI_EMAIL_SMTP_SERVER", va.VAL_EMAIL_SMTP_SERVER, cast=str
        )
        self.EMAIL_PORT = get_config("XINHAI_EMAIL_PORT", va.VAL_EMAIL_PORT, cast=int)
        self.EMAIL_USERNAME = get_config(
            "XINHAI_EMAIL_USERNAME", va.VAL_EMAIL_USERNAME, cast=str
        )
        self.EMAIL_PASSWORD = get_config(
            "XINHAI_EMAIL_PASSWORD", va.VAL_EMAIL_PASSWORD, cast=str
        )
        self.EMAIL_TO = get_config("XINHAI_EMAIL_TO", [], cast=list)
        self.FEISHU_WEBHOOK_URL = get_config(
            "XINHAI_FEISHU_WEBHOOK_URL", va.VAL_FEISHU_WEBHOOK_URL, cast=str
        )
        self.FEISHU_AT_USER_IDS = get_config(
            "XINHAI_FEISHU_AT_USER_IDS", [], cast=list
        )
        self.WECOM_WEBHOOK_URL = get_config(
            "XINHAI_WECOM_WEBHOOK_URL", va.VAL_WECOM_WEBHOOK_URL, cast=str
        )
        self.WECOM_AT_USER_IDS = get_config(
            "XINHAI_WECOM_AT_USER_IDS", [], cast=list
        )

        # === 10. 图片平台 ===
        self.UNSPLASH_ACCESS_KEY = get_config(
            "XINHAI_UNSPLASH_ACCESS_KEY", "请输入密钥", cast=str
        )
        self.UNSPLASH_BASIC_PATH = get_config(
            "XINHAI_UNSPLASH_BASIC_PATH", va.VAL_UNSPLASH_BASIC_URL, cast=str
        )
        self.PEXELS_ACCESS_KEY = get_config(
            "XINHAI_PEXELS_ACCESS_KEY", "请输入密钥", cast=str
        )
        self.PEXELS_BASIC_PATH = get_config(
            "XINHAI_PEXELS_BASIC_PATH", va.VAL_PEXELS_BASIC_URL, cast=str
        )

        # === 11. 全局监控 & 指标 ===
        self.GLOBAL_ENABLE_METRICS = get_config(
            "XINHAI_GLOBAL_ENABLE_METRICS", False, cast=bool
        )

        # === 12. SSE & Token 扩容 ===
        self.PROXY_BACKEND_SSE_URL = get_config(
            "XINHAI_PROXY_BACKEND_SSE_URL", "http://127.0.0.1:8000/api/sse", cast=str
        )
        self.SSE_HEARTBEAT_INTERVAL = get_config(
            "XINHAI_SSE_HEARTBEAT_INTERVAL", 30, cast=int
        )
        self.MAX_TOKENS_EXPANSION_FACTOR = get_config(
            "XINHAI_MAX_TOKENS_EXPANSION_FACTOR", 4.0, cast=float
        )
        self.MAX_LENGTH_RETRIES = get_config(
            "XINHAI_MAX_LENGTH_RETRIES", 3, cast=int
        )
        self.FACTOR_INCREMENT = get_config(
            "XINHAI_FACTOR_INCREMENT", 0.5, cast=float
        )
        self.FULL_TEXT_TOKENS_RATIO = get_config(
            "XINHAI_FULL_TEXT_TOKENS_RATIO", 3.5, cast=float
        )
        self.IMAGE_COUNT = get_config("XINHAI_IMAGE_COUNT", 218, cast=int)
        self.REFRESH_INTERVAL_MS = get_config(
            "XINHAI_REFRESH_INTERVAL_MS", 300000, cast=int
        )
        self.HEADER_BG_IMAGE_ID = get_config("XINHAI_HEADER_BG_IMAGE_ID", 164, cast=int)
        self.FOOTER_BG_IMAGE_ID = get_config("XINHAI_FOOTER_BG_IMAGE_ID", 166, cast=int)
        self.DEFAULT_BG_IMAGE_ID = get_config("XINHAI_DEFAULT_BG_IMAGE_ID", 1, cast=int)
        self.NOVEL_BG_IMAGE_ID = get_config("XINHAI_NOVEL_BG_IMAGE_ID", 1, cast=int)
        self.MESSAGE_WALL_BG_IMAGE_ID = get_config("XINHAI_MESSAGE_WALL_BG_IMAGE_ID", 1, cast=int)

        # === 13. 本地轻量模型 ===
        self.LOCAL_MODEL_MAX_MEMORY_MB = get_config(
            "XINHAI_LOCAL_MODEL_MAX_MEMORY_MB", 8192, cast=int
        )
        # 动态修正：取系统真实物理内存 × 50% 作为运行时上限
        self._runtime_fix_local_model_memory()
        self.LOCAL_MODEL_MONITOR_INTERVAL = get_config(
            "XINHAI_LOCAL_MODEL_MONITOR_INTERVAL", 30, cast=int
        )
        self.LOCAL_MODEL_MEMORY_THRESHOLD = get_config(
            "XINHAI_LOCAL_MODEL_MEMORY_THRESHOLD", 0.9, cast=float
        )
        self.LOCAL_MODEL_MAX_EVICTION_ATTEMPTS = get_config(
            "XINHAI_LOCAL_MODEL_MAX_EVICTION_ATTEMPTS", 5, cast=int
        )
        self.LOCAL_MODEL_CONCURRENCY = get_config(
            "XINHAI_LOCAL_MODEL_CONCURRENCY", 2, cast=int
        )
        self.LOCAL_MODELS_DEFINITION = get_config(
            "XINHAI_LOCAL_MODELS_DEFINITION",
            [
                {
                    "name": "embedding",
                    "modality": "text",
                    "loader_type": "huggingface_pipeline",
                    "task": "feature-extraction",
                    "model": "iic/nlp_gte_sentence-embedding_chinese-large",
                    "pipeline_kwargs": {},
                    "estimated_memory_mb": 621,
                }
            ],
            cast=list,
        )
        self.ENABLE_TEXT_ANALYSIS_TASKS = get_config(
            "XINHAI_ENABLE_TEXT_ANALYSIS_TASKS", False, cast=bool
        )
        self.TEXT_ANALYSIS_TASKS = get_config(
            "XINHAI_TEXT_ANALYSIS_TASKS", [ke.KEY_EMBEDDING], cast=list
        )

        # === 14. 分词 & 文本工具 ===
        self.JIEBA_STOPWORDS_PATH = get_config(
            "XINHAI_JIEBA_STOPWORDS_PATH", self.PATH_FILE_STOPWORDS_TXT, cast=str
        )
        self.JIEBA_USERDICT_PATH = get_config(
            "XINHAI_JIEBA_USERDICT_PATH", self.PATH_FILE_JIEBA_USERDICT_TXT, cast=str
        )
        self.JIEBA_FILTER_STOPWORDS_DEFAULT = get_config(
            "XINHAI_JIEBA_FILTER_STOPWORDS_DEFAULT", True, cast=bool
        )
        self.JIEBA_MIN_WORD_LEN = get_config("XINHAI_JIEBA_MIN_WORD_LEN", 2, cast=int)
        self.TEXTRANK_TOP_K = get_config("XINHAI_TEXTRANK_TOP_K", 10, cast=int)
        self.VOCAB_FILTER_MAX_WORDS = get_config(
            "XINHAI_VOCAB_FILTER_MAX_WORDS", 10, cast=int
        )
        self.VOCAB_FILTER_MAX_FREQWORDS = get_config(
            "XINHAI_VOCAB_FILTER_MAX_FREQWORDS", 15, cast=int
        )
        self.SEMANTIC_SIMILARITY_THRESHOLD = get_config(
            "XINHAI_SEMANTIC_SIMILARITY_THRESHOLD", 0.9, cast=float
        )

        # === 15. 谋篇/分卷/定章 能力注入内容限制（对应 global.json XINHAI_INJECTION_*）——fallback 必须与 global.json 默认值完全对齐，禁止分叉 ===
        # === 16. 织网角色关系条数上限 ===
        # 已迁移至 common/values.py VAL_WEAVE_RELS_MAX_COUNT_CHARACTER 常量，不再从 global.json 加载

        # === 17. 翻译 API ===
        self.TRANSLATION_PROVIDER = get_config(
            "XINHAI_TRANSLATION_PROVIDER", "tencent_tmt", cast=str
        )
        self.TRANSLATION_FROM = get_config(
            "XINHAI_TRANSLATION_FROM", "zh", cast=str
        )
        self.TRANSLATION_TO = get_config(
            "XINHAI_TRANSLATION_TO", "en", cast=str
        )
        self.TENCENT_TMT_SECRET_ID = get_config(
            "XINHAI_TENCENT_TMT_SECRET_ID", "请输入腾讯云 SecretId", cast=str
        )
        self.TENCENT_TMT_SECRET_KEY = get_config(
            "XINHAI_TENCENT_TMT_SECRET_KEY", "请输入腾讯云 SecretKey", cast=str
        )
        self.TENCENT_TMT_REGION = get_config(
            "XINHAI_TENCENT_TMT_REGION", "ap-beijing", cast=str
        )

    def _setup_paths(self) -> None:
        """初始化所有目录与路径"""
        self.DATA_ROOT = pa.DATA_ROOT
        self.MODEL_DIR = pa.MOUNT_LOCAL_MODEL_CACHE_DIR
        self.LOGS_DIR = pa.MOUNT_LOGS_DIR
        self.LOGS_FALLBACK_DIR = pa.MOUNT_LOGS_FALLBACK_DIR
        self.IMAGE_DIR = pa.MOUNT_IMAGE_DIR
        self.AUDIO_DIR = pa.MOUNT_AUDIO_DIR
        self.VIDEO_DIR = pa.MOUNT_VIDEO_DIR
        self.LYRIC_DIR = pa.MOUNT_LYRIC_DIR
        self.SQLITE_DIR = pa.MOUNT_SQLITE_DIR
        self.DB_PATH = self.SQLITE_DIR / pa.FILE_PROSE_REFINER_DB

        # 创建所有目录
        all_dirs = [
            self.DATA_ROOT, self.MODEL_DIR, self.LOGS_DIR, self.AUDIO_DIR,
            self.LOGS_FALLBACK_DIR, self.SQLITE_DIR, self.IMAGE_DIR, self.VIDEO_DIR,
            self.LYRIC_DIR,
        ]
        for d in all_dirs:
            d.mkdir(parents=True, exist_ok=True)

        # 路径
        self.PATH_FILE_INDEX_HTML = pa.PATH_FILE_INDEX_HTML
        self.PATH_FILE_STOPWORDS_TXT = str(pa.PATH_FILE_STOPWORDS_TXT)
        self.PATH_FILE_JIEBA_USERDICT_TXT = str(pa.PATH_FILE_JIEBA_USERDICT_TXT)
        self.PATH_FILE_PROSE_REFINER_DB = str(
            self.SQLITE_DIR / pa.FILE_PROSE_REFINER_DB
        )

    @staticmethod
    def _detect_total_ram_mb() -> Optional[int]:
        """检测系统可用物理内存总量（MB），用于动态修正本地模型内存上限。

        优先级：
        1. psutil（若已安装，跨平台，自动感知 cgroup 限额）
        2. cgroup 内存限额（Docker 容器场景，Linux 零依赖）
        3. /proc/meminfo（Linux 物理内存，零依赖）
        全部失败返回 None，由调用方保留默认值。
        """
        # 1. psutil（若已安装，跨平台，已内置 cgroup 感知）
        try:
            import psutil
            return int(psutil.virtual_memory().total // (1024 * 1024))
        except ImportError:
            pass  # psutil 未安装，走零依赖方案
        except Exception:
            return None  # psutil 已安装但调用失败，不再回退

        # 2. cgroup 内存限额（Docker 容器场景）
        #    cgroup v2: /sys/fs/cgroup/memory.max（"max" 表示无限制）
        #    cgroup v1: /sys/fs/cgroup/memory/memory.limit_in_bytes
        for cgroup_path in (
            "/sys/fs/cgroup/memory.max",
            "/sys/fs/cgroup/memory/memory.limit_in_bytes",
        ):
            try:
                with open(cgroup_path, "r", encoding="utf-8") as f:
                    val = f.read().strip()
                if val and val != "max":
                    limit_bytes = int(val)
                    # cgroup v1 无限制时返回接近 2^63 的巨大值，过滤
                    if 0 < limit_bytes < 1024 * 1024 * 1024 * 1024:  # < 1TB 视为真实限额
                        return int(limit_bytes // (1024 * 1024))
            except Exception:
                pass

        # 3. /proc/meminfo（Linux 物理内存，零依赖）
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        # 格式: "MemTotal:       16384000 kB"
                        return int(line.split()[1]) // 1024  # kB → MB
        except Exception:
            pass

        return None

    def _runtime_fix_local_model_memory(self) -> None:
        """动态修正本地模型内存上限：取系统真实物理内存 × 50%"""
        total_ram_mb = self._detect_total_ram_mb()
        if total_ram_mb and total_ram_mb > 0:
            runtime_max = int(total_ram_mb * 0.5)
            self.LOCAL_MODEL_MAX_MEMORY_MB = runtime_max
            FallbackLogger.info(
                f"动态修正本地模型内存上限：系统物理内存 {total_ram_mb}MB × 50% = {runtime_max}MB"
            )
        else:
            FallbackLogger.warning(
                "无法检测系统物理内存，保留配置文件中的默认值"
            )

    def get(self, key: str, default=None):
        """兼容按 key 动态取值（wecom/feishu notifier 使用）"""
        return getattr(self, key.upper(), default)

    def reload(self) -> None:
        """
        热重载（按需触发：仅当显式调用时才执行）。
        全部配置生效：只要检测到任何字段变化就 increment_config_version，不限于 LLM 敏感键。
        注：保留同步签名（非 async），兼容同步调用点如 startup 中的 config.reload()。
        """
        _MISSING = object()
        config_keys = {k for k in self.__slots__ if not k.startswith("_")}

        old_config = {k: getattr(self, k, _MISSING) for k in config_keys}
        self._load()
        new_config = {k: getattr(self, k, _MISSING) for k in config_keys}

        diff_keys = {k for k in config_keys if old_config[k] != new_config[k]}
        if not diff_keys:
            return

        FallbackLogger.info(f"配置重载变更项（{len(diff_keys)}）: {sorted(diff_keys)}")

        # 全部生效：任何字段 diff 都触发注册中心版本号 +1，executor 下次 get_executor 将强制清缓存
        from app.registry.global_singleton_registry import GlobalSingletonRegistry
        GlobalSingletonRegistry.increment_config_version()
        FallbackLogger.info("配置已重载，注册中心指纹已更新（全部生效）")


# 🌊 全局配置实例
config = Config.get_instance()
