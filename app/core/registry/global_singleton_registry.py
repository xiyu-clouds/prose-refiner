from __future__ import annotations
import asyncio
import hashlib
import json
import os
import site as _site
import threading
from pathlib import Path
from typing import Any, Dict, Optional, ClassVar
from app.common import keys as ke
from app.common.llm_constants import LLMModelType, LLMVendor, LLMTypeVendorModelMapping
from app.core.engine.executor import LLMExecutor
from app.utils.llm_utils import create_langchain_model
from app.utils.logger import LoggerManager as logger


class GlobalSingletonRegistry:
    """
    全局单例注册中心
    """
    CHINESE_NAME = "全局单例注册中心"

    _instance: Optional['GlobalSingletonRegistry'] = None
    _init_lock: ClassVar[asyncio.Lock] = None

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return

        self._config_version = 0
        self._last_seen_version = 0
        self._executors: Dict[str, LLMExecutor] = {}
        self._executor_lock: Optional[asyncio.Lock] = asyncio.Lock()
        self._cognitive_engine: Optional[Any] = None
        self._initialized = True

    @classmethod
    async def get_instance(cls) -> GlobalSingletonRegistry:
        """获取单例实例（异步版本）"""
        if cls._instance is not None:
            return cls._instance

        if cls._init_lock is None:
            cls._init_lock = asyncio.Lock()

        async with cls._init_lock:
            if cls._instance is None:
                cls._instance = cls()
                logger.info("全局单例注册中心已初始化", module_name=cls.CHINESE_NAME)

        return cls._instance

    @classmethod
    def get_instance_sync(cls) -> GlobalSingletonRegistry:
        """获取单例实例（同步版本，用于非异步上下文）"""
        if cls._instance is not None:
            return cls._instance

        # 使用 threading.Lock 保证同步环境下的线程安全
        if not hasattr(cls, '_sync_init_lock'):
            cls._sync_init_lock = threading.Lock()

        with cls._sync_init_lock:
            if cls._instance is None:
                cls._instance = cls()
                logger.info("全局单例注册中心已初始化（同步路径）", module_name=cls.CHINESE_NAME)

        return cls._instance

    @classmethod
    def increment_config_version(cls):
        """配置中心调用：原子增加版本号"""
        if cls._instance:
            cls._instance._config_version += 1
            logger.info(f"配置版本号已更新: {cls._instance._config_version}")

    # --------------------------------------------------------------------------
    # Rust CognitiveEngine 全局存取 & 集成初始化
    # --------------------------------------------------------------------------
    def _build_cognitive_engine(self):
        """内部构造 CognitiveEngine（同步），失败返回 None 并打日志。
        对齐 Rust 端真实初始化流程：new() 零参创建 → initialize(db, resources) → init_logging(log_dir, days)

        ⚠️ 关键约定（用户要求）：若 DB 文件已存在且非空，则跳过创建 DB 文件和表结构（Rust 层
        内部通过 CREATE TABLE IF NOT EXISTS 保证幂等），只做连接打开；Python 层在调用前做了
        存在性预检查并打日志，保证每次重启不会出现"每次都新建/覆盖"的情况。
        """
        from app.config.config import config
        try:
            import cognitor  # 延迟导入，避免未安装 Rust 包时启动崩溃
        except ModuleNotFoundError:
            logger.warning(
                "Rust 包 cognitor 未安装，引擎不可用（可继续使用 Python 层功能）",
                module_name=self.CHINESE_NAME,
            )
            return None

        try:
            # ---------- 0) 准备路径 ----------
            db_posix = config.DB_PATH.resolve().as_posix()
            db_path: Path = Path(db_posix)
            log_dir_posix = config.LOGS_DIR.resolve().as_posix()
            retention_days = int(config.LOG_KEEP_DAYS)

            # ---------- 1) Python 层先判断：DB 文件是否已存在（幂等控制） ----------
            # 注意：日志中只输出文件名，不输出完整路径，避免暴露明线存储位置。
            db_filename = db_path.name
            existed_before = False
            if db_path.exists():
                if not db_path.is_file():
                    raise RuntimeError(
                        f"DB 路径存在但不是文件（可能是目录或异常对象）: {db_posix}"
                    )
                db_size = db_path.stat().st_size
                if db_size > 0:
                    existed_before = True
                    logger.info(
                        f"检测到已存在的数据库文件：{db_filename}（size={db_size:,} B）"
                        f" → 跳过创建数据库文件 & 跳过 CREATE TABLE（Rust 内部 IF NOT EXISTS 保底）",
                        module_name=self.CHINESE_NAME,
                    )
                else:
                    # 文件存在但 0 字节：通常是上次初始化中途崩溃留下的空壳，允许 recreate，警告一次
                    logger.warning(
                        f"数据库文件存在但大小为 0（{db_filename}），"
                        "视为首次空库，允许 Rust 创建表结构（不会丢失任何数据，因为原文件是空的）",
                        module_name=self.CHINESE_NAME,
                    )
            else:
                # 父目录必须存在（config._setup_paths 已经 mkdir 过），只做兜底检查
                if not db_path.parent.exists():
                    logger.warning(
                        f"DB 父目录不存在，兜底创建：{db_path.parent.name}",
                        module_name=self.CHINESE_NAME,
                    )
                    db_path.parent.mkdir(parents=True, exist_ok=True)
                logger.info(
                    f"首次运行，数据库文件不存在（{db_filename}）→ 允许 Rust 创建 DB 文件和表结构",
                    module_name=self.CHINESE_NAME,
                )

            # ---------- 2) 调 Rust ----------
            engine = cognitor.CognitiveEngine()

            # 资源路径解析：
            # maturin include 将 src/resources/**/* 打包进 wheel，安装后落在 <site-packages>/src/resources/
            # 直接用 site.getsitepackages() 算出 site-packages，拼接即得资源路径
            resources_dir = ""

            # 环境变量优先（支持手动覆盖）
            _env_dir = os.environ.get("COGNITOR_RESOURCES_DIR", "").strip()
            if _env_dir and os.path.isdir(_env_dir):
                resources_dir = _env_dir
                logger.info(f"资源目录(环境变量): {resources_dir}", module_name=self.CHINESE_NAME)
            else:
                # 从 site-packages 拼接（wheel 安装后的确定性位置）
                for _sp in _site.getsitepackages():
                    _candidate = os.path.join(_sp, "src", "resources")
                    if os.path.isdir(_candidate):
                        resources_dir = _candidate
                        logger.info(f"资源目录(site-packages): {resources_dir}", module_name=self.CHINESE_NAME)
                        break

            if not resources_dir:
                # 兜底：cognitor 包同级
                _engine_pkg = os.path.dirname(os.path.abspath(cognitor.__file__))
                _candidate = os.path.join(os.path.dirname(_engine_pkg), "src", "resources")
                if os.path.isdir(_candidate):
                    resources_dir = _candidate
                    logger.info(f"资源目录(包同级兜底): {resources_dir}", module_name=self.CHINESE_NAME)

            if not resources_dir:
                logger.warning(
                    "资源目录未命中任何候选路径，将交由 Rust 端兜底解析",
                    module_name=self.CHINESE_NAME,
                )

            # 解析 Python 后端静态目录（用于设备授权暗线存储）
            # 注意：本文件位于 app/core/registry/ 下，需向上回溯三层才能到 app/ 目录
            _app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            _app_static_dir = os.path.join(_app_dir, "static")
            if not os.path.isdir(_app_static_dir):
                # 兜底：使用默认路径
                _app_static_dir = "/app/static"
            logger.info(f"静态目录(用于暗线): {_app_static_dir}", module_name=self.CHINESE_NAME)

            engine.initialize(db_posix, resources_dir, _app_static_dir)
            engine.init_logging(log_dir_posix, retention_days)

            # ---------- 3) 初始化后做一次最小完整性验证（确认引擎连接成功、能读到东西） ----------
            if existed_before and hasattr(engine, "global_config_get_full"):
                try:
                    _ = engine.global_config_get_full()  # 打一次 DB，确认能读
                    logger.info(
                        "既有数据库已成功打开连接（global_config_get_full 心跳调用 OK）",
                        module_name=self.CHINESE_NAME,
                    )
                except Exception as ping_e:
                    logger.exception(
                        f"既有数据库打开成功，但做 global_config 心跳校验时失败：{ping_e}"
                        "（不影响初始化，若后续报错请排查 DB 兼容性）",
                        module_name=self.CHINESE_NAME,
                    )

            # 最终日志：明确是否"新创建"（只输出文件名，不暴露完整路径）
            if existed_before:
                logger.info(
                    f"Rust CognitiveEngine 初始化成功：复用现有 DB={db_filename}, LOG={retention_days}d",
                    module_name=self.CHINESE_NAME,
                )
            else:
                logger.info(
                    f"Rust CognitiveEngine 初始化成功：新建 DB={db_filename}, LOG={retention_days}d",
                    module_name=self.CHINESE_NAME,
                )

            return engine
        except Exception as e:
            logger.exception(
                f"Rust CognitiveEngine 初始化失败：{e}",
                module_name=self.CHINESE_NAME,
            )
            return None

    def get_or_initialize_cognitive_engine(self, force: bool = False):
        """
        获取 Rust CognitiveEngine 实例，未初始化则立即初始化（幂等）。
        典型调用场景：FastAPI lifespan 启动期、或第一次需要引擎前懒加载。
        force=True 时强制重建实例（一般只用于测试）。
        """
        if self._cognitive_engine is None or force:
            engine = self._build_cognitive_engine()
            self._cognitive_engine = engine
            if engine is not None:
                logger.info(
                    f"Rust CognitiveEngine 已注册到全局单例: {type(engine).__name__}",
                    module_name=self.CHINESE_NAME,
                )
        return self._cognitive_engine

    def set_cognitive_engine(self, engine: Any) -> None:
        """外部设置（保留向后兼容）。推荐用 get_or_initialize_cognitive_engine()。"""
        self._cognitive_engine = engine
        if engine is not None:
            logger.info(
                f"Rust CognitiveEngine 已注册到全局单例: {type(engine).__name__}",
                module_name=self.CHINESE_NAME,
            )

    def get_cognitive_engine(self) -> Optional[Any]:
        """获取 Rust CognitiveEngine 实例（未初始化时返回 None）"""
        return self._cognitive_engine

    # --------------------------------------------------------------------------
    # 核心入口
    # --------------------------------------------------------------------------
    async def get_executor(
            self,
            model_type: str = LLMModelType.TEXT,
            vendor: Optional[str] = None,
            model: Optional[str] = None,
            api_key: Optional[str] = None,
            temperature: Optional[float] = None,
            top_p: Optional[float] = None,
            max_tokens: Optional[int] = None,
            timeout: Optional[int] = None,
            response_format: Any = None,
            use_recommended_params: bool = True,
            **kwargs
    ) -> LLMExecutor:
        from app.config.config import config
        vendor = vendor or config.TEXT_DEFAULT_VENDOR
        model = model or config.TEXT_DEFAULT_MODEL
        timeout = timeout or config.TEXT_API_TIMEOUT

        if not api_key:
            api_key = LLMVendor.get_api_key(vendor)

        if api_key and isinstance(api_key, str) and "请输入" in api_key:
            _preview = f"{api_key[:3]}***{api_key[-3:]}" if len(api_key) > 6 else "*" * len(api_key)
            raise ValueError(
                f"拒绝创建 Executor：API Key 无效（包含 '请输入' 占位值，len={len(api_key)}, preview={_preview}）"
            )

        if not LLMTypeVendorModelMapping.is_valid(model_type, vendor, model):
            raise ValueError(f"模型非法：{ke.KEY_TYPE}={model_type}, {ke.KEY_VENDOR}={vendor}, {ke.KEY_MODEL}={model}")

        params = config.TEXT_PARAMS if use_recommended_params else {}

        temperature = temperature if temperature is not None else params.get(ke.KEY_TEMPERATURE)
        top_p = top_p if top_p is not None else params.get(ke.KEY_TOP_P)
        max_tokens = max_tokens if max_tokens is not None else params.get(ke.KEY_MAX_TOKENS)

        cache_key = self._make_cache_key(
            model_type, vendor, model, api_key, temperature, top_p, max_tokens, timeout, response_format
        )

        # 获取当前全局配置版本
        current_version = self._config_version

        async with self._executor_lock:
            # 双重检查锁模式
            # 如果全局版本号 和 我上次记录的版本号 不一样，说明配置变了！
            if hasattr(self, '_last_seen_version') and self._last_seen_version != current_version:
                logger.info(f"检测到配置版本变更 (v{self._last_seen_version} -> v{current_version})，强制清空缓存")
                self._executors.clear()
                # 更新我看到的最新版本号
                self._last_seen_version = current_version

            if cache_key not in self._executors:
                # 构建标准参数包
                basic_params = {
                    ke.KEY_MODEL: model,
                    ke.KEY_API_KEY: api_key,
                    ke.KEY_TIMEOUT: timeout,
                    ke.KEY_TEMPERATURE: temperature,
                    ke.KEY_TOP_P: top_p,
                    ke.KEY_MAX_TOKENS: max_tokens,
                    **kwargs
                }
                if response_format:
                    basic_params[ke.KEY_RESPONSE_FORMAT] = response_format

                # 调用元数据驱动的工厂方法
                llm = create_langchain_model(vendor, basic_params)
                self._executors[cache_key] = LLMExecutor(vendor=vendor, model=model, chat_model=llm)
            return self._executors[cache_key]

    # --------------------------------------------------------------------------
    # 缓存 KEY
    # --------------------------------------------------------------------------
    @staticmethod
    def _make_cache_key(model_type, vendor, model, api_key, temp, top_p, max_t, timeout, response_format=None):
        d = {
            ke.KEY_T: model_type, ke.KEY_V: vendor, ke.KEY_M: model,
            ke.KEY_K: hashlib.md5(api_key.encode()).hexdigest()[:8],
            ke.KEY_TMP: temp, ke.KEY_TP: top_p, ke.KEY_MT: max_t, ke.KEY_TO: timeout
        }
        if response_format is not None:
            d[ke.KEY_RESPONSE_FORMAT] = json.dumps(response_format, sort_keys=True) if isinstance(response_format,
                                                                                                  dict) else str(
                response_format)
        return hashlib.md5(json.dumps(d, sort_keys=True).encode()).hexdigest()

    # --------------------------------------------------------------------------
    # 清理 & 重载
    # --------------------------------------------------------------------------
    async def async_clear_llm_caches(self):
        async with self._executor_lock:
            self._executors.clear()

    async def reload_all(self):
        await self.async_clear_llm_caches()
        logger.info("全局已重载：LLM / 插件 / 图", module_name=self.CHINESE_NAME)

    # --------------------------------------------------------------------------
    # WAL Checkpoint
    # --------------------------------------------------------------------------
    def force_wal_checkpoint(self, stage: str = "unspecified") -> dict:
        """执行 WAL checkpoint，仅在 WAL 存在待合并页时真正跑 TRUNCATE。

        对齐 Rust 层 `force_checkpoint` 的实际语义：
          - PASSIVE 查询当前 log 页数；log==0 时直接跳过，避免不必要的 fsync
          - log>0 时才执行 TRUNCATE，阻塞并截断 WAL 文件

        Args:
            stage: 调用阶段标识，用于日志定位（如 "startup" / "shutdown" / "manual"）

        Returns:
            dict，字段：
              - success       (bool)  本次调用是否成功（无异常）
              - skipped       (bool)  是否因 WAL 为空而跳过
              - busy          (bool)  是否因并发而繁忙
              - log_pages     (int)   checkpoint 前 WAL 中的页数
              - checkpointed  (int)   实际写回主库的页数
              - reason        (str)   说明性文字（跳过原因 / 成功详情 / 失败原因）
        """
        default_result = {
            "success": True,
            "skipped": True,
            "busy": False,
            "log_pages": 0,
            "checkpointed": 0,
            "reason": "",
        }
        # 只在引擎已初始化时执行，避免在 shutdown 时强制初始化引擎
        engine = self.get_cognitive_engine()
        if engine is None:
            default_result["reason"] = "引擎未初始化，无数据库可 checkpoint"
            logger.info(
                f"[WAL checkpoint][{stage}] 跳过：{default_result['reason']}",
                module_name=self.CHINESE_NAME,
            )
            return default_result

        try:
            result = engine.force_wal_checkpoint()
            skipped = bool(result.get("skipped", False))
            busy = bool(result.get("busy", False))
            log_pages = int(result.get("log_pages", 0))
            checkpointed = int(result.get("checkpointed", 0))

            if skipped:
                reason = "WAL 中无待合并页，跳过 TRUNCATE"
                logger.info(
                    f"[WAL checkpoint][{stage}] {reason}（log_pages=0）",
                    module_name=self.CHINESE_NAME,
                )
            elif busy:
                reason = f"存在并发读写，checkpoint 可能未完全合并（log_pages={log_pages}, checkpointed={checkpointed}）"
                logger.warning(
                    f"[WAL checkpoint][{stage}] {reason}",
                    module_name=self.CHINESE_NAME,
                )
            else:
                reason = f"WAL 数据已合并到主数据库（log_pages={log_pages}, checkpointed={checkpointed}）"
                logger.info(
                    f"[WAL checkpoint][{stage}] {reason}",
                    module_name=self.CHINESE_NAME,
                )

            return {
                "success": True,
                "skipped": skipped,
                "busy": busy,
                "log_pages": log_pages,
                "checkpointed": checkpointed,
                "reason": reason,
            }
        except Exception as e:
            default_result["success"] = False
            default_result["reason"] = f"调用引擎 force_wal_checkpoint 异常：{e}"
            logger.error(
                f"[WAL checkpoint][{stage}] {default_result['reason']}",
                module_name=self.CHINESE_NAME,
            )
            return default_result
