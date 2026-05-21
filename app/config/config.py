"""
🌊 心境配置中枢
"""
import json
import os
import threading
from app.common import paths as pa
from app.common import values as va
from app.common import vendor as ve
from app.common import model as mo
from app.common import keys as ke
from app.utils.file_util import FileUtil
from app.utils.logger import FallbackLogger


class Config:
    CHINESE_NAME = "心海配置中枢"

    _instance = None
    _lock = threading.Lock()

    __slots__ = (
        "_initialized",
        "DATA_ROOT",

        # ========== 基础路径、平台与环境 ==========
        "PATH_FILE_SETTINGS_JSON",

        # ========== LLM 配置 ==========
        "LLM_DEFAULT_VENDOR",
        "LLM_DEFAULT_MODEL",
        "LLM_API_TIMEOUT",
        "LLM_PARAMS",
        "LLM_DEEPSEEK_API_KEY",

        # ========== LangSmith 配置 ==========
        "LANGSMITH_ENABLED",
        "LANGSMITH_API_KEY",
        "LANGSMITH_PROJECT",
        "LANGSMITH_ENDPOINT",

        # ========== 元认知中枢全局配置 ==========
        "METACOGNITION_ENABLED",
        "METACOGNITION_MAX_LLM_CALLS",
        "METACOGNITION_MAX_DEBATE_ROUNDS",
        "METACOGNITION_QUEUE_MAXSIZE",
        "METACOGNITION_MAX_WORKER",
        "METACOGNITION_EXPIRES_AT",
        "METACOGNITION_MAX_CHARS_PER_TURN",
        "METACOGNITION_MAX_DEBATE_TURNS_TO_INJECT",
        "METACOGNITION_MAX_ISSUES_TO_DISPLAY",
        "METACOGNITION_DATA_LOADER_DEFAULT_LEVEL",
        "METACOGNITION_MONITOR_ALERT_COOLDOWN",
        "METACOGNITION_QUEUE_HIGH_WATERMARK",
        "METACOGNITION_QUEUE_MID_WATERMARK",
        "METACOGNITION_QUEUE_CHECK_INTERVAL",
        "METACOGNITION_TARGET_CHARS",
        "METACOGNITION_TOLERANCE",

        # ========== 日志配置 ==========
        "LOG_KEEP_DAYS",
        "LOG_MAX_BYTES",
        "LOG_BACKUP_COUNT",

        # ========== 并发配置 ==========
        "MAX_LLM_STEP_CONCURRENCY",
        "CURRENT_LLM_STEP_CONCURRENCY",
        "MEDIUM_LLM_STEP_CONCURRENCY",
        "MAX_BATCH_TASK_CONCURRENCY",
        "CURRENT_BATCH_TASK_CONCURRENCY",
        "MEDIUM_BATCH_TASK_CONCURRENCY",
        "MAX_BATCH_TASKS",
        "MAX_BATCH_FILE_SIZE_BYTES",

        # ========== 默认重试配置 ==========
        "DEFAULT_RETRY_CONFIG",

        # ========== 存储配置 ==========
        "STORAGE_BACKEND",
        "LLM_CACHE_MAX_SIZE",
        "LLM_CACHE_TTL",
        "REDIS_HOST",
        "REDIS_PORT",
        "REDIS_DB",
        "REDIS_PASSWORD",
        "REDIS_TIMEOUT",

        # ========== 报告与通知 ==========
        "TEXT_REPORT_TITLE",
        "WATERMARK_ENABLED",
        "WATERMARK_TEXT",
        "WATERMARK_COLOR",
        "WATERMARK_OPACITY",
        "WATERMARK_FONT_SIZE",
        "WATERMARK_ANGLE",
        "WATERMARK_SPACING_COLS",
        "WATERMARK_SPACING_ROWS",
        "WATERMARK_PADDING",
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
        "SUSPEND_TIMEOUT_SECONDS",

        # ========== 图片平台 ==========
        "UNSPLASH_ACCESS_KEY",
        "UNSPLASH_BASIC_PATH",
        "PEXELS_ACCESS_KEY",
        "PEXELS_BASIC_PATH",

        # ========== Ollama ==========
        "OLLAMA_ENABLED",
        "OLLAMA_BASE_URL",
        "OLLAMA_MODEL",
        "OLLAMA_PARAMS",
        "OLLAMA_TIMEOUT",

        # ========== 全局重试与监控 ==========
        "GLOBAL_MAX_RETRIES",
        "GLOBAL_RETRY_TIMEOUT",
        "GLOBAL_ENABLE_METRICS",
        "POLISH_AUXILIARY_TASK_LIMIT",

        # ========== 文件路径 ==========
        "PATH_FILE_THE_WAY_JSON",
        "PATH_FILE_PLUGINS_JSON",
        "PATH_FILE_PROMPTS_JSON",
        "PATH_FILE_PUNCTUATION_RULES_JSON",
        "PATH_FILE_SPELL_RULES_JSON",
        "PATH_FILE_ANALYSIS_RULES_JSON",
        "PATH_FILE_PROSE_REFINER_DB",
        "PATH_FILE_INDEX_HTML",
        "PATH_FILE_REPORT_TEMPLATE_HTML",
        "PATH_FILE_REPORT_TEMPLATE_HTML_DIR",
        "PATH_FILE_STOPWORDS_TXT",

        "MOUNT_PATH_FILE_SETTINGS_JSON",
        "MOUNT_PATH_FILE_THE_WAY_JSON",
        "MOUNT_PATH_FILE_PLUGINS_JSON",
        "MOUNT_PATH_FILE_PROMPTS_JSON",
        "MOUNT_PATH_FILE_PUNCTUATION_RULES_JSON",
        "MOUNT_PATH_FILE_SPELL_RULES_JSON",
        "MOUNT_PATH_FILE_ANALYSIS_RULES_JSON",

        # ========== 存储目录 ==========
        "DYE_VAT_DIR",
        "REPORTS_DIR",
        "LOGS_DIR",
        "LOGS_FALLBACK_DIR",
        "TEXT_DIR",
        "METACOGNITION_DIR",
        "SQLITE_DIR",
        "CONFIG_DIR",
        "DB_PATH",

        # ========== 步骤全文级模型输出token控制 ==========
        "CONSISTENCY_FIX_MAX_TOKENS",
        "STRUCTURE_FIX_MAX_TOKENS",
        "RHETORIC_SYNTAX_FIX_MAX_TOKENS",
        "CREATIVE_ENHANCE_MAX_TOKENS",
        "CANDIDATES_OUTPUT_MAX_TOKENS",
        "FIDELITY_REPAIR_MAX_TOKENS",

        # 场景适配卡片注入条数控制
        "CHARACTER_PROFILES",
        "WORLDVIEW_RULES",
        "RELATIONSHIP_MAP",
        "STYLE_PREFERENCE",

        "PROXY_BACKEND_SSE_URL",
        "SSE_HEARTBEAT_INTERVAL",
        "MAX_TOKENS_EXPANSION_FACTOR",
        "FULL_TEXT_TOKENS_RATIO",
        "IMAGE_COUNT",
        "REFRESH_INTERVAL_MS",
        "MAX_LENGTH_RETRIES",
        "FACTOR_INCREMENT",
        "REASONING_AUTO_INJECT",
        "REASONING_EFFORT_MAP"
    )

    def __new__(cls):
        # 快速检查，避免不必要的锁竞争
        if cls._instance is None:
            with cls._lock:
                # 双重检查，确保只创建一个实例
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False  # 使用不同的标志
                    cls._instance = instance
        return cls._instance

    def __init__(self):
        # 使用实例级别的锁确保线程安全
        with self._lock:
            if self._initialized:
                return  # 已经初始化过，直接返回
            self._initialized = True

        FallbackLogger.info("🔄 正在初始化心海配置中枢...")
        self._load()

    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        return cls()  # 直接调用 __new__，会自动处理实例创建

    def _load(self):
        self._setup_paths()

        assert hasattr(self, 'PATH_FILE_SETTINGS_JSON'), "配置路径未生成！_setup_paths 可能执行失败。"
        raw_config = FileUtil().read_json_file(self.PATH_FILE_SETTINGS_JSON)

        def get_config(key: str, default, cast):
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
                        else:
                            raise ValueError(f"环境变量 {key} 解析结果为 {type(parsed)}，预期为 dict。值: {val}")
                    elif cast == str:
                        return val
                    else:
                        return val  # 默认原样返回
                except Exception as e:
                    raise ValueError(f"环境变量 {key} 格式错误且无法解析为 {cast}: {val}. 错误: {e}")

            raw_val = raw_config.get(key, default)

            if cast == dict:
                # 防御性编程：如果读出来是字符串，尝试自动解析回字典
                if isinstance(raw_val, str):
                    FallbackLogger.warning(
                        f"⚠️ [配置容错] 检测到 {key} 在 app.json 中被错误地存储为字符串类型，正在尝试自动修复..."
                    )
                    try:
                        parsed = json.loads(raw_val)
                        if isinstance(parsed, dict):
                            FallbackLogger.info(f"✅ [配置容错] {key} 修复成功，已转换为字典。")
                            return parsed
                        else:
                            FallbackLogger.error(f"❌ [配置容错] {key} 解析后仍不是字典 ({type(parsed)})，使用默认值。")
                            return default
                    except json.JSONDecodeError:
                        FallbackLogger.error(f"❌ [配置容错] {key} 字符串格式非法，无法解析，使用默认值。原始值: {raw_val}")
                        return default
                elif not isinstance(raw_val, dict):
                    FallbackLogger.error(f"❌ [配置容错] {key} 类型未知 ({type(raw_val)})，使用默认值。")
                    return default

            return raw_val

        # === LLM 配置 ===
        default_vendor = get_config("XINHAI_LLM_DEFAULT_VENDOR", ve.VENDOR_DEEPSEEK, cast=str)
        self.LLM_DEFAULT_VENDOR = str(default_vendor).strip().lower() if default_vendor else ve.VENDOR_DEEPSEEK
        default_model = get_config("XINHAI_LLM_DEFAULT_MODEL", mo.MODEL_DEEPSEEK_CHAT, cast=str)
        self.LLM_DEFAULT_MODEL = str(default_model).strip().lower() if default_model else mo.MODEL_DEEPSEEK_CHAT
        self.LLM_API_TIMEOUT = get_config("XINHAI_LLM_API_TIMEOUT", 120, cast=int)
        self.LLM_PARAMS = get_config("XINHAI_LLM_PARAMS", va.VAL_RECOMMENDED_PARAMS, cast=dict)

        # 具体厂商密钥
        self.LLM_DEEPSEEK_API_KEY = get_config("XINHAI_LLM_DEEPSEEK_API_KEY", va.VAL_API_KEY_DESC, cast=str)
        # 是否开启推理模式
        self.REASONING_AUTO_INJECT = get_config("XINHAI_REASONING_AUTO_INJECT", True, cast=bool)
        # 推理程度等级
        self.REASONING_EFFORT_MAP = get_config("XINHAI_REASONING_EFFORT_MAP", ke.KEY_MEDIUM, cast=str)

        # === LangSmith 配置 ===
        self.LANGSMITH_ENABLED = get_config("XINHAI_LANGSMITH_ENABLED", True, cast=bool)
        self.LANGSMITH_API_KEY = get_config("XINHAI_LANGSMITH_API_KEY", va.VAL_API_KEY_DESC, cast=str)
        self.LANGSMITH_PROJECT = get_config("XINHAI_LANGSMITH_PROJECT", va.VAL_LANGSMITH_PROJECT, cast=str)
        self.LANGSMITH_ENDPOINT = get_config("XINHAI_LANGSMITH_ENDPOINT", va.VAL_LANGSMITH_ENDPOINT, cast=str)

        # 如果启用了 LangSmith，则设置环境变量, 这里的环境变量键值不要改
        if self.LANGSMITH_ENABLED and self.LANGSMITH_API_KEY:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = self.LANGSMITH_API_KEY
            os.environ["LANGCHAIN_PROJECT"] = self.LANGSMITH_PROJECT
            os.environ["LANGCHAIN_ENDPOINT"] = self.LANGSMITH_ENDPOINT
            FallbackLogger.info(f"✅ LangSmith 已启用 | 项目: {self.LANGSMITH_PROJECT}")
        elif self.LANGSMITH_ENABLED:
            FallbackLogger.warning("⚠️ LANGSMITH_ENABLED=true 但未提供有效 API KEY，无法提供服务！")
            self.LANGSMITH_ENABLED = False
        else:
            FallbackLogger.info("ℹ️ LangSmith 未启用")

        # 元认知中枢
        # 元认知总开关，关闭后直接透传上游数据
        self.METACOGNITION_ENABLED = get_config("XINHAI_METACOGNITION_ENABLED", True, cast=bool)
        # 单次元认知任务允许的最大 LLM 调用次数
        self.METACOGNITION_MAX_LLM_CALLS = get_config("XINHAI_METACOGNITION_MAX_LLM_CALLS", 30, cast=int)
        # 最大允许的上帝之眼触发辩论的循环次数
        self.METACOGNITION_MAX_DEBATE_ROUNDS = get_config("XINHAI_METACOGNITION_MAX_DEBATE_ROUNDS", 8, cast=int)
        # 内部任务队列最大长度（用于并发控制）
        self.METACOGNITION_QUEUE_MAXSIZE = get_config("XINHAI_METACOGNITION_QUEUE_MAXSIZE", 30, cast=int)
        # 最大并发执行循环数
        self.METACOGNITION_MAX_WORKER = get_config("XINHAI_METACOGNITION_MAX_WORKER", 3, cast=int)
        # 任务超时时间（秒），超时后强制终止
        self.METACOGNITION_EXPIRES_AT = get_config("XINHAI_METACOGNITION_EXPIRES_AT", 300, cast=int)
        # 单轮发言/报告最大字符数
        self.METACOGNITION_MAX_CHARS_PER_TURN = get_config("XINHAI_METACOGNITION_MAX_CHARS_PER_TURN", 800, cast=int)
        # 辩论记录最大注入轮次（最近 N 轮）
        self.METACOGNITION_MAX_DEBATE_TURNS_TO_INJECT = get_config("XINHAI_METACOGNITION_MAX_DEBATE_TURNS_TO_INJECT", 2, cast=int)
        # 裁决报告中问题清单最大展示条数
        self.METACOGNITION_MAX_ISSUES_TO_DISPLAY = get_config("XINHAI_METACOGNITION_MAX_ISSUES_TO_DISPLAY", 7, cast=int)
        # 默认加载数据层级
        self.METACOGNITION_DATA_LOADER_DEFAULT_LEVEL = get_config("XINHAI_METACOGNITION_DATA_LOADER_DEFAULT_LEVEL", 0, cast=int)
        # 队列监控告警冷却时间（秒），防止连续轰炸
        self.METACOGNITION_MONITOR_ALERT_COOLDOWN = get_config("XINHAI_METACOGNITION_MONITOR_ALERT_COOLDOWN", 600,
                                                               cast=int)
        # 队列高水位告警阈值（使用率百分比）
        self.METACOGNITION_QUEUE_HIGH_WATERMARK = get_config("XINHAI_METACOGNITION_QUEUE_HIGH_WATERMARK", 0.8,
                                                             cast=float)
        # 队列中水位提示阈值（使用率百分比）
        self.METACOGNITION_QUEUE_MID_WATERMARK = get_config("XINHAI_METACOGNITION_QUEUE_MID_WATERMARK", 0.5, cast=float)
        # 队列监控检查间隔（秒）
        self.METACOGNITION_QUEUE_CHECK_INTERVAL = get_config("XINHAI_METACOGNITION_QUEUE_CHECK_INTERVAL", 30, cast=int)
        # 智能合并段落的推荐目标字符数
        self.METACOGNITION_TARGET_CHARS = get_config("XINHAI_METACOGNITION_TARGET_CHARS", 750, cast=int)
        # 智能合并段落的偏移量
        self.METACOGNITION_TOLERANCE = get_config("XINHAI_METACOGNITION_TOLERANCE", 50, cast=int)

        # === 日志配置 ===
        self.LOG_KEEP_DAYS = get_config("XINHAI_LOG_KEEP_DAYS", va.VAL_LOG_KEEP_DAYS, cast=int)
        self.LOG_MAX_BYTES = get_config("XINHAI_LOG_MAX_BYTES", va.VAL_LOG_MAX_BYTES, cast=int)
        self.LOG_BACKUP_COUNT = get_config("XINHAI_LOG_BACKUP_COUNT", va.VAL_LOG_BACKUP_COUNT, cast=int)

        # === 并发 ===
        self.MAX_LLM_STEP_CONCURRENCY = get_config("XINHAI_MAX_LLM_STEP_CONCURRENCY", 30, cast=int)
        self.CURRENT_LLM_STEP_CONCURRENCY = get_config("XINHAI_CURRENT_LLM_STEP_CONCURRENCY", 5, cast=int)
        self.MEDIUM_LLM_STEP_CONCURRENCY = get_config("XINHAI_MEDIUM_LLM_STEP_CONCURRENCY", 20, cast=int)
        self.MAX_BATCH_TASK_CONCURRENCY = get_config("XINHAI_MAX_BATCH_TASK_CONCURRENCY", 15, cast=int)
        self.CURRENT_BATCH_TASK_CONCURRENCY = get_config("XINHAI_CURRENT_BATCH_TASK_CONCURRENCY", 2, cast=int)
        self.MEDIUM_BATCH_TASK_CONCURRENCY = get_config("XINHAI_MEDIUM_BATCH_TASK_CONCURRENCY", 10, cast=int)
        self.MAX_BATCH_TASKS = get_config("XINHAI_MAX_BATCH_TASKS", 50, cast=int)
        self.MAX_BATCH_FILE_SIZE_BYTES = get_config("XINHAI_MAX_BATCH_FILE_SIZE_BYTES", va.VAL_MAX_BATCH_FILE_SIZE_BYTES, cast=int)

        # 默认重试配置
        self.DEFAULT_RETRY_CONFIG = get_config("XINHAI_DEFAULT_RETRY_CONFIG", va.VAL_DEFAULT_RETRY_CONFIG, cast=dict)

        # === 存储配置 ===
        self.STORAGE_BACKEND = get_config("XINHAI_STORAGE_BACKEND", ke.KEY_REDIS, cast=str)
        self.LLM_CACHE_MAX_SIZE = get_config("XINHAI_LLM_CACHE_MAX_SIZE", 4096, cast=int)
        self.LLM_CACHE_TTL = get_config("XINHAI_LLM_CACHE_TTL", 7200, cast=int)
        self.REDIS_HOST = get_config("XINHAI_REDIS_HOST", ke.KEY_REDIS, cast=str)
        self.REDIS_PORT = get_config("XINHAI_REDIS_PORT", 6379, cast=int)
        self.REDIS_DB = get_config("XINHAI_REDIS_DB", 0, cast=int)
        self.REDIS_PASSWORD = get_config("XINHAI_REDIS_PASSWORD", None, cast=str)  # 注意：环境变量中 null 要传空字符串
        self.REDIS_TIMEOUT = get_config("XINHAI_REDIS_TIMEOUT", 5, cast=int)

        # 报告标题
        self.TEXT_REPORT_TITLE = get_config("XINHAI_TEXT_REPORT_TITLE",
                                                     va.VAL_TEXT_REPORT_PREFIX, cast=str)

        # === 水印相关 ===
        self.WATERMARK_ENABLED = get_config("XINHAI_WATERMARK_ENABLED", True, cast=bool)
        self.WATERMARK_TEXT = get_config("XINHAI_WATERMARK_TEXT", va.VAL_WATERMARK_CONTENT, cast=str)
        self.WATERMARK_COLOR = get_config("XINHAI_WATERMARK_COLOR", va.VAL_WATERMARK_COLOR, cast=str)
        self.WATERMARK_OPACITY = get_config("XINHAI_WATERMARK_OPACITY", 0.12, cast=float)
        self.WATERMARK_FONT_SIZE = get_config("XINHAI_WATERMARK_FONT_SIZE", 48, cast=int)
        self.WATERMARK_ANGLE = get_config("XINHAI_WATERMARK_ANGLE", -30, cast=int)
        self.WATERMARK_SPACING_COLS = get_config("XINHAI_WATERMARK_SPACING_COLS", 5, cast=int)
        self.WATERMARK_SPACING_ROWS = get_config("XINHAI_WATERMARK_SPACING_ROWS", 8, cast=int)
        self.WATERMARK_PADDING = get_config("XINHAI_WATERMARK_PADDING", 30, cast=int)

        # 通知配置
        # 是否启用通知功能
        self.NOTIFICATION_ENABLED = get_config("XINHAI_NOTIFICATION_ENABLED", True, cast=bool)
        self.NOTIFICATION_CHANNELS = get_config("XINHAI_NOTIFICATION_CHANNELS", va.VAL_NOTIFICATION_CHANNELS, cast=list)
        self.EMAIL_SMTP_SERVER = get_config("XINHAI_EMAIL_SMTP_SERVER", va.VAL_EMAIL_SMTP_SERVER, cast=str)
        self.EMAIL_PORT = get_config("XINHAI_EMAIL_PORT", va.VAL_EMAIL_PORT, cast=int)
        self.EMAIL_USERNAME = get_config("XINHAI_EMAIL_USERNAME", va.VAL_EMAIL_USERNAME, cast=str)
        self.EMAIL_PASSWORD = get_config("XINHAI_EMAIL_PASSWORD", va.VAL_EMAIL_PASSWORD, cast=str)
        self.EMAIL_TO = get_config("XINHAI_EMAIL_TO", [], cast=list)
        self.FEISHU_WEBHOOK_URL = get_config("XINHAI_FEISHU_WEBHOOK_URL", va.VAL_FEISHU_WEBHOOK_URL, cast=str)
        self.FEISHU_AT_USER_IDS = get_config("XINHAI_FEISHU_AT_USER_IDS", [], cast=list)
        self.WECOM_WEBHOOK_URL = get_config("XINHAI_WECOM_WEBHOOK_URL", va.VAL_WECOM_WEBHOOK_URL, cast=str)
        self.WECOM_AT_USER_IDS = get_config("XINHAI_WECOM_AT_USER_IDS", [], cast=list)
        # 挂起任务默认超时时间（秒），超时后自动按降级策略处理
        self.SUSPEND_TIMEOUT_SECONDS = get_config("XINHAI_SUSPEND_TIMEOUT_SECONDS", 3600, cast=int)

        # 图片平台
        self.UNSPLASH_ACCESS_KEY = get_config("XINHAI_UNSPLASH_ACCESS_KEY", va.VAL_API_KEY_DESC, cast=str)
        self.UNSPLASH_BASIC_PATH = get_config("XINHAI_UNSPLASH_BASIC_PATH", va.VAL_UNSPLASH_BASIC_URL, cast=str)
        self.PEXELS_ACCESS_KEY = get_config("XINHAI_PEXELS_ACCESS_KEY", va.VAL_API_KEY_DESC, cast=str)
        self.PEXELS_BASIC_PATH = get_config("XINHAI_PEXELS_BASIC_PATH", va.VAL_PEXELS_BASIC_URL, cast=str)

        # Ollama
        self.OLLAMA_ENABLED = get_config("XINHAI_OLLAMA_ENABLED", True, cast=bool)
        self.OLLAMA_BASE_URL = get_config("XINHAI_OLLAMA_BASE_URL", va.VAL_OLLAMA_BASE_URL, cast=str)
        self.OLLAMA_MODEL = get_config("XINHAI_OLLAMA_MODEL", va.VAL_OLLAMA_MODEL, cast=str)
        self.OLLAMA_PARAMS = get_config("XINHAI_OLLAMA_PARAMS", va.VAL_OLLAMA_PARAMS, cast=dict)
        self.OLLAMA_TIMEOUT = get_config("XINHAI_OLLAMA_TIMEOUT", 300, cast=int)

        # 全局最大重试次数和超时熔断
        self.GLOBAL_MAX_RETRIES = get_config("XINHAI_GLOBAL_MAX_RETRIES", 10000, cast=int)
        self.GLOBAL_RETRY_TIMEOUT = get_config("XINHAI_GLOBAL_RETRY_TIMEOUT", 600, cast=int)
        self.GLOBAL_ENABLE_METRICS = get_config("XINHAI_GLOBAL_ENABLE_METRICS", True, cast=bool)

        # 串行打磨/修复的辅助报告最多注入条数
        self.POLISH_AUXILIARY_TASK_LIMIT = get_config("XINHAI_POLISH_AUXILIARY_TASK_LIMIT", 7, cast=int)

        # 场景适配步骤控制用户补充信息注入的条数
        self.CHARACTER_PROFILES = get_config("XINHAI_CHARACTER_PROFILES", 8, cast=int)
        self.WORLDVIEW_RULES = get_config("XINHAI_WORLDVIEW_RULES", 8, cast=int)
        self.RELATIONSHIP_MAP = get_config("XINHAI_RELATIONSHIP_MAP", 8, cast=int)
        self.STYLE_PREFERENCE = get_config("XINHAI_STYLE_PREFERENCE", 8, cast=int)

        # SSE 代理后端地址
        self.PROXY_BACKEND_SSE_URL = get_config("XINHAI_PROXY_BACKEND_SSE_URL", "http://127.0.0.1:8000/api/sse", cast=str)
        self.SSE_HEARTBEAT_INTERVAL = get_config("XINHAI_SSE_HEARTBEAT_INTERVAL", 30, cast=int)

        # 字符对应的token输出比率
        self.FULL_TEXT_TOKENS_RATIO = get_config("XINHAI_FULL_TEXT_TOKENS_RATIO", 3.0, cast=float)

        # deepseek v4模型扩容比率
        self.MAX_TOKENS_EXPANSION_FACTOR = get_config("XINHAI_MAX_TOKENS_EXPANSION_FACTOR", 2.5, cast=float)
        # 因最大输出token导致的截断，自动扩容的重试次数
        self.MAX_LENGTH_RETRIES = get_config("XINHAI_MAX_LENGTH_RETRIES", 3, cast=int)
        # 每次重试增加的比率值
        self.FACTOR_INCREMENT = get_config("XINHAI_FACTOR_INCREMENT", 0.5, cast=float)

        # 首页卡片背景图片和刷新频率
        self.IMAGE_COUNT = get_config("XINHAI_IMAGE_COUNT", 218, cast=float)
        self.REFRESH_INTERVAL_MS = get_config("XINHAI_REFRESH_INTERVAL_MS", 300000, cast=float)

    def _setup_paths(self):
        # 输出目录
        self.DATA_ROOT = pa.DATA_ROOT
        self.DYE_VAT_DIR = self.DATA_ROOT / ke.KEY_DYE_VAT
        self.REPORTS_DIR = self.DATA_ROOT / ke.KEY_REPORTS
        self.LOGS_DIR = self.DATA_ROOT / ke.KEY_LOGS
        self.LOGS_FALLBACK_DIR = self.DATA_ROOT / ke.KEY_LOGS_FALLBACK
        self.TEXT_DIR = self.DATA_ROOT / ke.KEY_TEXT
        self.METACOGNITION_DIR = self.DATA_ROOT / ke.KEY_METACOGNITION
        self.SQLITE_DIR = self.DATA_ROOT / ke.KEY_SQLITE
        self.DB_PATH = self.SQLITE_DIR / pa.FILE_PROSE_REFINER_DB
        self.CONFIG_DIR = pa.MOUNT_CONFIG_DIR

        # 创建所有目录
        all_dirs = [
            self.DATA_ROOT,
            self.DYE_VAT_DIR, self.REPORTS_DIR, self.LOGS_DIR,
            self.LOGS_FALLBACK_DIR, self.TEXT_DIR, self.METACOGNITION_DIR,
            self.SQLITE_DIR, self.CONFIG_DIR
        ]
        for d in all_dirs:
            d.mkdir(parents=True, exist_ok=True)

        # 动态赋值所有配置文件路径
        self.PATH_FILE_SETTINGS_JSON = self.get_config_path(pa.FILE_SETTINGS_JSON)
        self.PATH_FILE_THE_WAY_JSON = self.get_config_path(pa.FILE_THE_WAY_JSON)
        self.PATH_FILE_PLUGINS_JSON = self.get_config_path(pa.FILE_PLUGINS_JSON)
        self.PATH_FILE_PROMPTS_JSON = self.get_config_path(pa.FILE_PROMPTS_JSON)
        self.PATH_FILE_PUNCTUATION_RULES_JSON = self.get_config_path(pa.FILE_PUNCTUATION_RULES_JSON)
        self.PATH_FILE_SPELL_RULES_JSON = self.get_config_path(pa.FILE_SPELL_RULES_JSON)
        self.PATH_FILE_ANALYSIS_RULES_JSON = self.get_config_path(pa.FILE_ANALYSIS_RULES_JSON)
        self.PATH_FILE_INDEX_HTML = pa.PATH_FILE_INDEX_HTML
        self.PATH_FILE_REPORT_TEMPLATE_HTML = pa.PATH_FILE_REPORT_TEMPLATE_HTML
        self.PATH_FILE_REPORT_TEMPLATE_HTML_DIR = str(self.PATH_FILE_REPORT_TEMPLATE_HTML.parent)
        self.PATH_FILE_STOPWORDS_TXT = str(pa.PATH_FILE_STOPWORDS_TXT)
        # 检查主配置文件所在目录的可写性
        if not os.access(os.path.dirname(self.PATH_FILE_SETTINGS_JSON), os.W_OK):
            FallbackLogger.warning(f"⚠️ 配置目录不可写！请检查挂载权限: {self.PATH_FILE_SETTINGS_JSON}")

        self.MOUNT_PATH_FILE_SETTINGS_JSON = pa.MOUNT_PATH_FILE_SETTINGS_JSON
        self.MOUNT_PATH_FILE_THE_WAY_JSON = pa.MOUNT_PATH_FILE_THE_WAY_JSON
        self.MOUNT_PATH_FILE_PLUGINS_JSON = pa.MOUNT_PATH_FILE_PLUGINS_JSON
        self.MOUNT_PATH_FILE_PROMPTS_JSON = pa.MOUNT_PATH_FILE_PROMPTS_JSON
        self.MOUNT_PATH_FILE_PUNCTUATION_RULES_JSON = pa.MOUNT_PATH_FILE_PUNCTUATION_RULES_JSON
        self.MOUNT_PATH_FILE_SPELL_RULES_JSON = pa.MOUNT_PATH_FILE_SPELL_RULES_JSON
        self.MOUNT_PATH_FILE_ANALYSIS_RULES_JSON = pa.MOUNT_PATH_FILE_ANALYSIS_RULES_JSON

    @staticmethod
    def get_config_path(filename):
        mount_path = pa.MOUNT_CONFIG_DIR / filename
        if mount_path.exists():
            return str(mount_path)  # 优先返回挂卷路径
        return str(pa.DEFAULT_CONFIG_DIR / filename)  # 兜底返回项目默认路径

    def update_config_file_path(self, target_filename: str) -> str:
        """
        精准更新单个配置文件路径的专用方法。
        Args:
            target_filename (str): 必须传入的特定文件名
        """
        # 定义文件名与实例属性名的映射关系
        config_mapping = {
            pa.FILE_SETTINGS_JSON: 'PATH_FILE_SETTINGS_JSON',
            pa.FILE_THE_WAY_JSON: 'PATH_FILE_THE_WAY_JSON',
            pa.FILE_PLUGINS_JSON: 'PATH_FILE_PLUGINS_JSON',
            pa.FILE_PROMPTS_JSON: 'PATH_FILE_PROMPTS_JSON',
            pa.FILE_PUNCTUATION_RULES_JSON: 'PATH_FILE_PUNCTUATION_RULES_JSON',
            pa.FILE_SPELL_RULES_JSON: 'PATH_FILE_SPELL_RULES_JSON',
            pa.FILE_ANALYSIS_RULES_JSON: 'PATH_FILE_ANALYSIS_RULES_JSON',
        }

        # 直接根据传入的文件名进行精准匹配，无循环，无兜底
        attr_name = config_mapping.get(target_filename)

        if not attr_name:
            FallbackLogger.warning(f"⚠️ 未知的配置文件名，无法更新路径: {target_filename}")
            return ""

        new_path = self.get_config_path(target_filename)
        old_path = getattr(self, attr_name, None)

        # 只有当路径确实发生变化时才更新，避免不必要的日志噪音
        if old_path != new_path:
            setattr(self, attr_name, new_path)
            FallbackLogger.debug(f"🔄 路径已更新 | {attr_name} -> {new_path}")
        else:
            FallbackLogger.debug(f"ℹ️ 路径无变化 | {attr_name}")

        return new_path

    @staticmethod
    def _parse_bool(val: str) -> bool:
        return val.strip().lower() in va.VAL_SUCCESS_FLAG

    def get(self, key: str, default=None):
        return getattr(self, key.upper(), default)

    async def reload(self):
        # 定义一个唯一哨兵对象
        _MISSING = object()
        # 只对比非私有配置字段
        config_keys = {k for k in self.__slots__ if not k.startswith("_")}

        old_config = {k: getattr(self, k, _MISSING) for k in config_keys}
        self._load()  # 重新加载
        new_config = {k: getattr(self, k, _MISSING) for k in config_keys}

        diff_keys = {k for k in config_keys if old_config[k] != new_config[k]}
        if diff_keys:
            FallbackLogger.info(f"配置变更项: {sorted(diff_keys)}")

        if diff_keys & va.VAL_LLM_SENSITIVE_KEYS:
            from app.registry.global_singleton_registry import GlobalSingletonRegistry
            GlobalSingletonRegistry.increment_config_version()
            FallbackLogger.info("📢 配置已重载，已通知注册中心更新指纹")


# 🌊 全局配置实例
config = Config.get_instance()
