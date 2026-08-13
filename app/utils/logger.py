"""
日志管理器模块
"""
import contextvars
import atexit
import inspect
import logging
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any
from pathlib import Path
import colorlog
_trace_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("_trace_id", default=None)

_SENSITIVE_KEY_PATTERNS = [
    # ============== 通用后缀（配合 _ 前缀分隔符自动命中 XXXX_API_KEY / XXXX_SECRET_ID） ==============
    'api_key', 'apikey', 'api-key',
    'access_key', 'accesskey', 'access-key',
    'secret_id', 'secretid', 'secret-id',
    'secret_key', 'secretkey', 'secret-key',
    'access_token', 'accesstoken', 'access-token',
    'refresh_token', 'refreshtoken', 'refresh-token',
    'session_key', 'sessionkey', 'session-key',
    'private_key', 'privatekey', 'private-key',
    'client_secret', 'clientsecret', 'client-secret',
    'auth_token', 'authtoken', 'auth-token',
    'password', 'passwd', 'pwd',
    'authorization',

    # ============== 具体供应商 / 业务键（精确匹配，冗余但保险） ==============
    'deepseek_api_key',
    'tongyi_api_key',
    'langsmith_api_key',
    'langchain_api_key',
    'tencent_tmt_secret_id',
    'tencent_tmt_secret_key',
    'unsplash_access_key',
    'pexels_access_key',
    'redis_password',
    'smtp_password',
    'email_password',
    'wecom_webhook_url',
    'feishu_webhook_url',
    'webhook_url',

    # ============== 业界常见供应商（预防性覆盖） ==============
    'openai_api_key',
    'dashscope_api_key',
    'zhipu_api_key',
    'moonshot_api_key',
    'claude_api_key',
    'anthropic_api_key',
    'gemini_api_key',
    'qwen_api_key',
    'glm_api_key',
]


def _mask_value(value: str) -> str:
    if value is None:
        return ''
    s = str(value)
    if not s:
        return ''
    if len(s) <= 6:
        return '*' * len(s)
    return s[:3] + '****' + s[-3:]


def mask_secrets_in_message(msg: Any) -> Any:
    if msg is None:
        return msg
    if not isinstance(msg, str):
        try:
            from json import dumps, loads
            raw = dumps(msg, ensure_ascii=False, default=str)
            masked_str = mask_secrets_in_message(raw)
            try:
                return loads(masked_str)
            except Exception:
                return masked_str
        except Exception:
            return msg

    result = msg

    def _kv_masker(match):
        prefix = match.group(1)
        key = match.group(2)
        sep = match.group(3)
        if match.group(4) is not None:
            quoted_value = match.group(4)
            return f"{prefix}{key}{sep}\"{_mask_value(quoted_value)}\""
        if match.group(5) is not None:
            quoted_value = match.group(5)
            return f"{prefix}{key}{sep}'{_mask_value(quoted_value)}'"
        bare_value = match.group(6) or ''
        return f"{prefix}{key}{sep}{_mask_value(bare_value)}"

    for key_name in _SENSITIVE_KEY_PATTERNS:
        pattern = re.compile(
            r'([\s{"\',;\n&=:]|^)' +
            r'(' + re.escape(key_name) + r')' +
            r'(\s*(?::|=|=>|: )\s*)' +
            r'(?:"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'|([^\s"\',;})\]]+))',
            re.IGNORECASE
        )
        result = pattern.sub(_kv_masker, result)

        bare_pattern = re.compile(
            r'(^|[\s{"\',;\n&=:])(' + re.escape(key_name) + r')[\s]*[:=][\s]*([^\s,;})\]"\']+)',
            re.IGNORECASE
        )
        result = bare_pattern.sub(
            lambda m: f"{m.group(1)}{m.group(2)}:{_mask_value(m.group(3))}",
            result
        )

    # ---- 兜底：对常见的 Bearer / Basic / Token 前置空格 token 单独脱敏 ----
    # （不依赖前面的 authorization key，纯语义检测，对日志中任何类似 HTTP Header 的格式都生效）
    result = re.sub(
        r'(?i)\b(Bearer|Basic|Token)\s+([A-Za-z0-9\-._~+/]{8,}=*)',
        lambda m: f"{m.group(1)} {_mask_value(m.group(2))}",
        result
    )

    # ---- 兜底：异常信息中 "当前值: xxx" / "当前密钥: xxx" / "current_value: xxx" 模式 ----
    # 仅匹配 8+ 字符的密钥样值，避免误伤 "当前值: 100" 等短数值
    result = re.sub(
        r'(?i)(当前(?:值|密钥)|current(?:_value|_key))\s*[:：]\s*([A-Za-z0-9\-._~+/]{8,})',
        lambda m: f"{m.group(1)}: {_mask_value(m.group(2))}",
        result
    )

    return result


class FallbackLogger:
    _logger = None
    _lock = threading.Lock()

    @classmethod
    def _init_logger(cls):
        logger = logging.getLogger("fallback.minimal")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        if not logger.handlers:
            console = logging.StreamHandler(sys.stderr)
            console.setFormatter(logging.Formatter(
                "[FALLBACK] %(asctime)s | %(levelname)-8s | %(message)s",
                datefmt='%Y-%m-%d %H:%M:%S'
            ))
            console.setLevel(logging.DEBUG)
            logger.addHandler(console)

            try:
                current_date = datetime.now().strftime("%Y-%m-%d")
                log_dir = PATH_ROOT_LOGS_FALLBACK / current_date
                log_dir.mkdir(parents=True, exist_ok=True)
                log_file = log_dir / "fallback.log"

                file_handler = logging.FileHandler(log_file, encoding='utf-8')
                file_handler.setFormatter(logging.Formatter(
                    "%(asctime)s | %(levelname)-8s | %(message)s",
                    datefmt='%Y-%m-%d %H:%M:%S'
                ))
                file_handler.setLevel(logging.DEBUG)  # 全量记录，便于诊断
                logger.addHandler(file_handler)
            except Exception:
                raise

        return logger

    @classmethod
    def _get_logger(cls):
        if cls._logger is None:
            with cls._lock:
                if cls._logger is None:
                    cls._logger = cls._init_logger()
        return cls._logger

    @classmethod
    def debug(cls, msg, *args, **kwargs):
        cls._get_logger().debug(msg, *args, **kwargs)

    @classmethod
    def info(cls, msg, *args, **kwargs):
        cls._get_logger().info(msg, *args, **kwargs)

    @classmethod
    def warning(cls, msg, *args, **kwargs):
        cls._get_logger().warning(msg, *args, **kwargs)

    @classmethod
    def error(cls, msg, *args, **kwargs):
        cls._get_logger().error(msg, *args, **kwargs)

    @classmethod
    def critical(cls, msg, *args, **kwargs):
        cls._get_logger().critical(msg, *args, **kwargs)


# --- 自定义 TRACE 级别 ---
TRACE = 5
logging.addLevelName(TRACE, "TRACE")


def trace(self: logging.Logger, message, *args, **kwargs):
    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, args, **kwargs)


logging.Logger.trace = trace

# --- 全局状态 ---
_logger_dict: Dict[str, logging.Logger] = {}
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="LogCleanup-")
_cleanup_submitted = False  # 简化清理触发标志

_config_instance = None  # 由主程序注入

PATH_DATA = Path("/data")
LOG_KEEP_DAYS = 7
LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 10
PATH_ROOT_LOGS = PATH_DATA / "logs"
PATH_ROOT_LOGS_FALLBACK = PATH_DATA / "logs_fallback"


def _get_config() -> Dict[str, Any]:
    """获取日志配置：优先使用注入的 config，否则用默认值"""
    if _config_instance is not None:
        try:
            return {
                "keep_days": int(getattr(_config_instance, "LOG_KEEP_DAYS", LOG_KEEP_DAYS)),
                "max_bytes": int(getattr(_config_instance, "LOG_MAX_BYTES", LOG_MAX_BYTES)),
                "backup_count": int(getattr(_config_instance, "LOG_BACKUP_COUNT", LOG_BACKUP_COUNT)),
                "logs_dir": Path(getattr(_config_instance, "LOGS_DIR", PATH_ROOT_LOGS)),
                "logs_fallback_dir": Path(getattr(_config_instance, "LOGS_FALLBACK_DIR", PATH_ROOT_LOGS_FALLBACK)),
            }
        except Exception as e:
            FallbackLogger.warning(f"从注入的 config 读取日志参数失败，使用默认值: {e}")

    return {
        "keep_days": LOG_KEEP_DAYS,
        "max_bytes": LOG_MAX_BYTES,
        "backup_count": LOG_BACKUP_COUNT,
        "logs_dir": PATH_ROOT_LOGS,
        "logs_fallback_dir": PATH_ROOT_LOGS_FALLBACK
    }


def _create_console_handler() -> logging.Handler:
    """创建统一的彩色控制台 handler（格式与文件 handler 对齐，仅多颜色包裹）"""
    handler = logging.StreamHandler(sys.stdout)
    formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s | %(levelname)-8s | %(name)s | %(trace_id)s | %(custom_module)s | %(custom_location)s | %(message)s | %(pathname)s:%(lineno)d%(reset)s",
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
            'TRACE': 'blue',
        }
    )
    handler.setFormatter(formatter)
    handler.setLevel(logging.DEBUG)
    return handler


# 统一文件日志格式（info 与 error handler 共用）
_FILE_LOG_FORMAT = (
    '%(asctime)s | %(levelname)-8s | %(name)s | %(trace_id)s | '
    '%(custom_module)s | %(custom_location)s | %(message)s | %(pathname)s:%(lineno)d'
)
_FILE_LOG_DATEFMT = '%Y-%m-%d %H:%M:%S'


class LoggerManager:
    """日志管理器"""

    CHINESE_NAME = "日志管理"

    _level_map = {
        'trace': TRACE,
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'critical': logging.CRITICAL,
    }

    @classmethod
    def inject_config(cls, config_obj):
        """注入配置对象（应在应用启动早期调用一次）"""
        global _config_instance
        _config_instance = config_obj
        FallbackLogger.info("日志配置已注入")

    @classmethod
    def get_logger(cls, name: str = '心海') -> logging.Logger:
        """获取或创建 logger（线程安全）"""
        name = name or "default"
        if name in _logger_dict:
            return _logger_dict[name]

        with threading.Lock():
            if name in _logger_dict:
                return _logger_dict[name]

            logger = logging.getLogger(name)
            logger.setLevel(logging.DEBUG)
            logger.propagate = False

            # 控制台 handler（始终存在）
            logger.addHandler(_create_console_handler())

            # 标记 handlers 已添加（只初始化一次）
            logger._handlers_added = True

            _logger_dict[name] = logger
            return logger

    @classmethod
    def _ensure_handlers(cls, logger: logging.Logger):
        """确保 logger 拥有正确的文件 handler（只执行一次）"""
        if getattr(logger, "_file_handlers_added", False):
            return

        with threading.Lock():
            if getattr(logger, "_file_handlers_added", False):
                return

            config = _get_config()
            current_date = datetime.now().strftime("%Y-%m-%d")
            candidates = [config["logs_dir"], config["logs_fallback_dir"]]

            log_directory = None
            for candidate in candidates:
                try:
                    full_path = candidate / current_date
                    full_path.mkdir(parents=True, exist_ok=True)
                    log_directory = full_path
                    break
                except Exception as e:
                    FallbackLogger.debug(f"路径创建失败: {candidate} -> {e}")
                    continue

            if not log_directory:
                FallbackLogger.error("所有日志路径均创建失败，仅使用控制台输出")
                logger._file_handlers_added = True
                return

            # Info handler（INFO 及以上）
            info_file = log_directory / "info.log"
            try:
                handler = RotatingFileHandler(
                    info_file, maxBytes=config["max_bytes"],
                    backupCount=config["backup_count"], encoding='utf-8'
                )
                handler.setFormatter(logging.Formatter(_FILE_LOG_FORMAT, datefmt=_FILE_LOG_DATEFMT))
                handler.setLevel(logging.INFO)
                logger.addHandler(handler)
            except Exception as e:
                FallbackLogger.warning(f"创建 info handler 失败: {e}")

            # Error handler（ERROR 及以上，CRITICAL 也会进入；级别字段反映真实级别）
            error_file = log_directory / "error.log"
            try:
                handler = RotatingFileHandler(
                    error_file, maxBytes=config["max_bytes"],
                    backupCount=config["backup_count"], encoding='utf-8'
                )
                handler.setFormatter(logging.Formatter(_FILE_LOG_FORMAT, datefmt=_FILE_LOG_DATEFMT))
                handler.setLevel(logging.ERROR)
                logger.addHandler(handler)
            except Exception as e:
                FallbackLogger.warning(f"创建 error handler 失败: {e}")

            logger._file_handlers_added = True

    @classmethod
    def _async_cleanup(cls):
        """异步清理过期日志目录"""
        config = _get_config()
        cutoff = datetime.now() - timedelta(days=config["keep_days"])

        for root_path in [config["logs_dir"], config["logs_fallback_dir"]]:
            if not root_path.exists():
                continue

            for item in root_path.iterdir():
                if not item.is_dir():
                    continue
                try:
                    dir_date = datetime.strptime(item.name, "%Y-%m-%d")
                    if dir_date < cutoff:
                        for file in item.rglob("*"):
                            if file.is_file():
                                try:
                                    file.unlink()
                                except Exception as e:
                                    FallbackLogger.warning(f"删除文件失败: {file} -> {e}")
                                try:
                                    item.rmdir()
                                    FallbackLogger.info(f"已删除过期日志目录: {item}")
                                except Exception as e:
                                    FallbackLogger.error(f"删除目录失败: {item} -> {e}")
                except ValueError:
                    continue

    @classmethod
    def set_trace_id(cls, trace_id: str):
        """显式设置当前上下文的 trace_id（通常在入口处调用）"""
        _trace_id_var.set(trace_id)

    @classmethod
    def get_trace_id(cls) -> Optional[str]:
        """获取当前 trace_id"""
        return _trace_id_var.get()

    @classmethod
    def _log(
            cls,
            level: str,
            msg: str,
            *args,
            module_name: Optional[str] = None,
            location: Optional[str] = None,
            **kwargs
    ):
        """统一日志入口"""
        global _cleanup_submitted
        if not _cleanup_submitted:
            _executor.submit(cls._async_cleanup)
            _cleanup_submitted = True

        logger = cls.get_logger()
        cls._ensure_handlers(logger)
        current_trace_id = _trace_id_var.get() or "-"

        # === 安全获取调用上下文 ===
        try:
            stack = inspect.stack(context=0)
            if len(stack) < 3:
                raise ValueError("Stack too shallow")

            frame = stack[2].frame
            f_locals = frame.f_locals
            func_name = frame.f_code.co_name or "<module>"
            class_name = None
            chinese_name = module_name or "未知模块"

            if 'self' in f_locals:
                instance = f_locals['self']
                cls_type = instance.__class__
                class_name = cls_type.__name__
                chinese_name = getattr(cls_type, 'CHINESE_NAME', chinese_name)
            elif 'cls' in f_locals and isinstance(f_locals['cls'], type):
                cls_type = f_locals['cls']
                class_name = cls_type.__name__
                chinese_name = getattr(cls_type, 'CHINESE_NAME', chinese_name)

            final_location = location or (f"{class_name}.{func_name}" if class_name else func_name)

            user_extra = kwargs.get('extra', {}).copy()
            fixed_extra = {
                'custom_module': chinese_name,
                'custom_location': final_location,
                'trace_id': current_trace_id,
            }

            dynamic_extra = {k: v for k, v in user_extra.items() if k not in fixed_extra}

            final_msg = msg
            if dynamic_extra:
                try:
                    from json import dumps
                    extra_str = dumps(dynamic_extra, ensure_ascii=False, separators=(',', ':'), default=str)
                    final_msg = f"{msg} | extra:{extra_str}"
                except Exception:
                    final_msg = f"{msg} | extra:<serialize failed>"

            final_msg = mask_secrets_in_message(final_msg)

            # === 对 args 参数（%s 格式化的变量）也做脱敏 ===
            # 避免调用方使用 logger.info("foo: %s", secret_value) 绕过 msg 脱敏
            if args:
                args = tuple(mask_secrets_in_message(a) if isinstance(a, str) else a for a in args)

            final_extra = {**fixed_extra, **{k: v for k, v in user_extra.items() if k in fixed_extra}}
            supported_keys = {'exc_info', 'stack_info', 'stacklevel', 'extra'}
            filtered_kwargs = {k: v for k, v in kwargs.items() if k in supported_keys}
            filtered_kwargs['extra'] = final_extra

            log_func = getattr(logger, level, logger.info)
            log_func(final_msg, *args, **filtered_kwargs)

        except Exception as e:
            FallbackLogger.error(f"日志记录失败: {e} | msg='{msg}'")

    # === 公共日志接口 ===
    @classmethod
    def trace(cls, msg: str, *args, module_name: str = None, location: str = None, **kwargs):
        cls._log('trace', msg, *args, module_name=module_name, location=location, **kwargs)

    @classmethod
    def debug(cls, msg: str, *args, module_name: str = None, location: str = None, **kwargs):
        cls._log('debug', msg, *args, module_name=module_name, location=location, **kwargs)

    @classmethod
    def info(cls, msg: str, *args, module_name: str = None, location: str = None, **kwargs):
        cls._log('info', msg, *args, module_name=module_name, location=location, **kwargs)

    @classmethod
    def warning(cls, msg: str, *args, module_name: str = None, location: str = None, **kwargs):
        cls._log('warning', msg, *args, module_name=module_name, location=location, **kwargs)

    @classmethod
    def error(cls, msg: str, *args, module_name: str = None, location: str = None, **kwargs):
        cls._log('error', msg, *args, module_name=module_name, location=location, **kwargs)

    @classmethod
    def critical(cls, msg: str, *args, module_name: str = None, location: str = None, **kwargs):
        cls._log('critical', msg, *args, module_name=module_name, location=location, **kwargs)

    @classmethod
    def exception(cls, msg: str, *args, module_name: str = None, location: str = None, **kwargs):
        kwargs['exc_info'] = True
        cls.error(msg, *args, module_name=module_name, location=location, **kwargs)


@atexit.register
def _cleanup_resources():
    """程序退出时清理资源"""
    FallbackLogger.info("正在关闭日志系统...")
    _executor.shutdown(wait=True)
    FallbackLogger.info("日志系统已关闭")
