"""设备授权状态探测（domain 层）。

设计说明：
- 启动时检查：`init_device_auth_on_startup()` 在 FastAPI lifespan 中调用，
  触发 Rust 引擎明暗双线校验，并将结果缓存到内存。
- 健康检查读取：`probe_device_auth()` 只读取已缓存的结果，不再触发新的授权检查。
- 真正的授权校验在 Rust 引擎层（src/util/device_auth.rs 的 ensure_authorized），
  于 CognitiveEngine.initialize 时完成；本模块仅负责桥接状态到 Python 层。
"""

import time
from typing import Optional, Tuple, Dict, Any
from app.utils.logger import LoggerManager as logger
from app.core.registry.global_singleton_registry import GlobalSingletonRegistry

CHINESE_NAME = "设备授权探测"

# 启动期检查结果：(timestamp, payload)，启动后永久有效
_STARTUP_RESULT: Optional[Tuple[float, Dict[str, Any]]] = None

# 健康检查读取的 30s 缓存：避免前端高频轮询反复触发 Rust 调用
_CACHE_TTL = 30.0
_cache: Optional[Tuple[float, object]] = None


def init_device_auth_on_startup() -> Optional[Dict[str, Any]]:
    """启动期执行设备授权检查（仅执行一次）。

    在 FastAPI lifespan 中调用，触发 Rust 引擎明暗双线校验。
    如果超限，抛出 RuntimeError 阻止启动。
    结果缓存到 _STARTUP_RESULT，后续健康检查直接读取。

    返回：设备授权状态字典，失败返回 None。
    异常：如果设备授权超限，抛出 RuntimeError。
    """
    global _STARTUP_RESULT
    now = time.monotonic()

    try:
        registry = GlobalSingletonRegistry.get_instance_sync()
        engine = registry.get_cognitive_engine()
        if engine is None:
            logger.warning("设备授权检查跳过：Rust 引擎未就绪", module_name=CHINESE_NAME)
            return None

        # 调用引擎桥接的 device_auth_status()，获取完整授权状态
        result = engine.device_auth_status()
        _STARTUP_RESULT = (now, result)

        # 日志记录授权结果
        verdict = result.get("verdict", "unknown")
        total = result.get("total_unique_devices", 0)
        max_devices = result.get("max_devices", 0)

        # 双重检查：即使 verdict 不是 over_limit，也要检查总数是否超限
        # 防止 Rust 引擎返回错误 verdict
        is_over_limit = verdict == "over_limit" or total > max_devices

        if is_over_limit:
            logger.error(
                f"设备授权超限：已登记 {total} / {max_devices} 台设备。",
                module_name=CHINESE_NAME,
            )
            raise RuntimeError(
                f"设备授权超限（{total}/{max_devices}），服务启动被拒绝。"
            )
        elif verdict in ("registered", "just_registered"):
            logger.info(
                f"设备授权校验通过：{verdict}，当前 {total} / {max_devices} 台",
                module_name=CHINESE_NAME,
            )
        else:
            logger.info(
                f"设备授权状态：{verdict}",
                module_name=CHINESE_NAME,
            )

        return result
    except RuntimeError:
        # 超限异常直接抛出，让 FastAPI 启动失败
        raise
    except Exception as e:
        logger.error(
            f"启动期设备授权检查异常：{e}",
            module_name=CHINESE_NAME,
        )
        return None


def probe_device_auth():
    """读取设备授权状态（30s 内存缓存）。

    优先返回启动期已缓存的结果（_STARTUP_RESULT），
    若启动期未执行则降级为懒获取（并缓存 30s）。

    返回：设备授权状态字典；失败返回 None，不影响健康检查主流程。
    """
    global _cache, _STARTUP_RESULT

    # 1. 优先返回启动期缓存结果（永久有效，不需要 TTL）
    if _STARTUP_RESULT is not None:
        return _STARTUP_RESULT[1]

    # 2. 降级：30s 内存缓存（兼容未走 lifespan 的场景）
    now = time.monotonic()
    cached = _cache
    if cached is not None and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    try:
        registry = GlobalSingletonRegistry.get_instance_sync()
        engine = registry.get_cognitive_engine()
        if engine is None:
            return None  # 引擎未就绪不缓存，下次请求重试
        result = engine.device_auth_status()
        _cache = (now, result)  # 只缓存成功结果
        return result
    except Exception:
        # 吞掉所有异常：健康检查接口永远不能因为设备授权挂 5xx；异常不缓存
        return None


def force_refresh_device_auth() -> Optional[Dict[str, Any]]:
    """强制刷新设备授权状态（用于删除设备后立即刷新）。

    清空所有缓存并重新调用引擎获取状态。
    """
    global _cache, _STARTUP_RESULT

    try:
        registry = GlobalSingletonRegistry.get_instance_sync()
        engine = registry.get_cognitive_engine()
        if engine is None:
            return None

        result = engine.device_auth_status()
        now = time.monotonic()
        _cache = (now, result)
        _STARTUP_RESULT = (now, result)  # 同步更新启动期缓存
        return result
    except Exception:
        return None
