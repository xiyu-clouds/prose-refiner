import asyncio
import functools
import threading
import time
import uuid
from typing import Any, Dict, Callable, Optional
import contextvars
import aiohttp
import httpcore
import httpx
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
    wait_fixed,
    RetryCallState
)
from app.common import keys as ke
from app.config.config import config
from app.utils.logger import LoggerManager as logger

# 线程安全锁
_GLOBAL_LOCK = threading.Lock()

# 全局状态
RETRY_COUNTER: Dict[str, int] = {}  # 按函数名计数
RETRY_ABORT_FLAG = {ke.KEY_ABORT: False}  # 全局中止标志
LAST_RESET_TIME = [time.time()]  # 用于周期性清零或限流
METRICS: Dict[str, int] = {
    ke.KEY_SUCCESS_AFTER_RETRY: 0,
    ke.KEY_FAILED_AFTER_RETRY: 0,
    ke.KEY_TOTAL_RETRIES: 0,
}

# 创建一个 contextvar 来保存当前 trace_id
current_trace_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(ke.KEY_CURRENT_TRACE_ID, default=None)


# ==================== 可重试异常判断 ====================
def is_retryable_exception(exc: BaseException) -> bool:
    """
    判断是否为可重试异常（仅网络层/服务端错误）
    """
    # 1. 原有的 requests/aiohttp/os 错误
    if isinstance(exc, (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.ChunkedEncodingError,
        asyncio.TimeoutError,
        aiohttp.ClientError,
        aiohttp.ClientOSError,
        aiohttp.ServerDisconnectedError,
        OSError,
        ConnectionResetError,
        BrokenPipeError
    )):
        return True

    # 🔥 2. httpx 及其底层 httpcore 的网络错误
    if isinstance(exc, (
        httpx.ReadError,
        httpx.ConnectError,
        httpx.TimeoutException,
        httpx.NetworkError,
        httpx.RemoteProtocolError,
        httpcore.ReadError,
        httpcore.ConnectError,
        httpcore.ReadTimeout,
        httpcore.ConnectTimeout,
        httpcore.NetworkError,
        httpcore.RemoteProtocolError
    )):
        return True

    if isinstance(exc, requests.exceptions.HTTPError):
        status_code = exc.response.status_code
        return status_code >= 500 or status_code == 429  # 只重试 5xx 和 429
    if isinstance(exc, aiohttp.ClientResponseError):
        return exc.status >= 500 or exc.status == 429
    return False


# ==================== 重试前回调 ====================
def before_retry_callback(retry_state: RetryCallState, func_name: str = "", module_name: str = None,
                          location: str = None):
    # 获取原始函数
    func_name = func_name or retry_state.fn.__name__

    # 如果 retry_state 没有 trace_id，生成一个并绑定到 context
    if not hasattr(retry_state, ke.KEY_TRACE_ID):
        trace_id = f"{uuid.uuid4().hex[:8]}"
        retry_state.trace_id = trace_id
    else:
        trace_id = retry_state.trace_id

    current_trace_id.set(trace_id)  # 绑定到当前 context

    with _GLOBAL_LOCK:
        # 更新该函数的重试计数
        current = RETRY_COUNTER.get(func_name, 0) + 1
        RETRY_COUNTER[func_name] = current

        # 检查全局总次数
        total_retry_count = sum(RETRY_COUNTER.values())
        METRICS[ke.KEY_TOTAL_RETRIES] = total_retry_count

        if total_retry_count >= config.GLOBAL_MAX_RETRIES:
            RETRY_ABORT_FLAG[ke.KEY_ABORT] = True
            logger.error(f"全局重试已达上限 {config.GLOBAL_MAX_RETRIES}，已中止所有重试 | {ke.KEY_TRACE_ID}={trace_id}", module_name=module_name or "重试机制（前置）",
                         # 可传入业务模块名
                         location=location or f"Retry.{func_name}")
            raise RuntimeError("全局重试已达上限，终止所有重试")

        if RETRY_ABORT_FLAG[ke.KEY_ABORT]:
            raise RuntimeError("全局重试已被手动中止")

    # 日志输出
    attempt = retry_state.attempt_number
    exc = retry_state.outcome.exception()
    logger.info(
        f"[{func_name}] 第 {attempt} 次重试 | "
        f"{ke.KEY_TRACE_ID}={trace_id} | "
        f"累计重试: {current} | "
        f"全局总计: {total_retry_count} | "
        f"错误类型: {type(exc).__name__} | "
        f"错误详情: {str(exc)}",
        module_name=module_name or "重试机制（前置）",
        location=f"Retry:{location or func_name}"
    )


# ==================== 调用后回调（用于指标统计）====================
def after_call_callback(func_name: str, success: bool, module_name: Optional[str] = None,
                        location: Optional[str] = None):
    """记录调用结果，可用于后续监控告警"""
    if not config.GLOBAL_ENABLE_METRICS:
        return

    # 从 context 获取当前 trace_id
    trace_id = current_trace_id.get()

    key = ke.KEY_SUCCESS_AFTER_RETRY if success else ke.KEY_FAILED_AFTER_RETRY
    with _GLOBAL_LOCK:
        METRICS[key] += 1

    logger.info(
        f"调用完成: {func_name} | 成功={success} | "
        f"{ke.KEY_TRACE_ID}={trace_id} | "
        f"重试成功累计={METRICS[ke.KEY_SUCCESS_AFTER_RETRY]} | "
        f"重试失败累计={METRICS[ke.KEY_FAILED_AFTER_RETRY]}",
        module_name=module_name or "重试机制（统计）",
        location=f"Retry:{location or func_name}"
    )


# ==================== 核心装饰器工厂 ====================
def retry_decorator(
        max_retries: int = 3,
        enable_exp_backoff: bool = True,
        exp_multiplier: float = 1.0,
        exp_max_wait: float = 10.0,
        min_wait: float = 0.1,
        reraise: bool = True,
        module_name: Optional[str] = None,
        location: Optional[str] = None
):
    """
    生产级可配置重试装饰器（支持 async/sync）

    参数:
        max_retries: 最大尝试次数
        enable_exp_backoff: 是否启用指数退避
        exp_multiplier: 指数退避乘数
        exp_max_wait: 最大等待秒数
        min_wait: 最小等待时间
        reraise: 是否最终抛出异常
        module_name: 中文模块名（用于日志）
        location: 自定义位置，如 "Downloader.fetch_data"
    """

    def decorator(func: Callable) -> Callable:
        # 构建等待策略
        wait_strategy = (
            wait_exponential(multiplier=exp_multiplier, max=exp_max_wait, min=min_wait)
            if enable_exp_backoff
            else wait_fixed(min_wait)
        )

        # 构造重试回调（带上下文）
        before_sleep = functools.partial(
            before_retry_callback,
            func_name=func.__name__,
            module_name=module_name,
            location=location or f"{func.__qualname__}"  # 自动带类名
        )

        # 异步处理
        if asyncio.iscoroutinefunction(func):
            @retry(
                stop=stop_after_attempt(max_retries),
                wait=wait_strategy,
                retry=retry_if_exception(is_retryable_exception),
                before_sleep=before_sleep,
                reraise=reraise,
            )
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                # 入口生成 trace_id 绑定到当前上下文
                trace_id = f"{uuid.uuid4().hex[:8]}"
                token = current_trace_id.set(trace_id)
                try:
                    result = await func(*args, **kwargs)
                    after_call_callback(
                        func.__name__,
                        success=True,
                        module_name=module_name,
                        location=location or func.__qualname__
                    )
                    return result
                except Exception:
                    after_call_callback(
                        func.__name__,
                        success=False,
                        module_name=module_name,
                        location=location or func.__qualname__
                    )
                    raise
                finally:
                    # ✅ 清理 contextvar，防止泄漏
                    current_trace_id.reset(token)  # 🌟 必须 reset

            return async_wrapper

        # 同步处理
        else:
            @retry(
                stop=stop_after_attempt(max_retries),
                wait=wait_strategy,
                retry=retry_if_exception(is_retryable_exception),
                before_sleep=before_sleep,
                reraise=reraise,
            )
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                # ✅ 同步函数也生成 trace_id 并绑定
                trace_id = f"{uuid.uuid4().hex[:8]}"
                token = current_trace_id.set(trace_id)
                try:
                    result = func(*args, **kwargs)
                    after_call_callback(
                        func.__name__,
                        success=True,
                        module_name=module_name,
                        location=location or func.__qualname__
                    )
                    return result
                except Exception:
                    after_call_callback(
                        func.__name__,
                        success=False,
                        module_name=module_name,
                        location=location or func.__qualname__
                    )
                    raise
                finally:
                    current_trace_id.reset(token)  # ✅ 清理

            return sync_wrapper

    return decorator


# ==================== 辅助工具：查看当前状态 ====================
def get_retry_status() -> Dict[str, Any]:
    """获取当前重试系统的运行状态（可用于健康检查或监控接口）"""
    with _GLOBAL_LOCK:
        return {
            ke.KEY_GLOBAL_ABORT_FLAG: RETRY_ABORT_FLAG[ke.KEY_ABORT],
            ke.KEY_TOTAL_RETRY_COUNT: sum(RETRY_COUNTER.values()),
            ke.KEY_PER_FUNCTION_RETRIES: dict(RETRY_COUNTER),
            ke.KEY_METRICS: dict(METRICS),
            ke.KEY_TIMESTAMP: time.time(),
        }


def reset_retry_counters(
    module_name: Optional[str] = None,
    location: Optional[str] = None,
    func_name: Optional[str] = None
):
    """
    重置重试计数器（可用于每日清零、手动恢复等场景）

    Args:
        module_name: 日志模块名
        location: 日志位置
        func_name: 如果指定，则只重置该函数的计数；否则重置全部
    """
    with _GLOBAL_LOCK:
        if func_name is None:
            # 全局重置
            RETRY_COUNTER.clear()
            RETRY_ABORT_FLAG[ke.KEY_ABORT] = False
            LAST_RESET_TIME[0] = time.time()
            logger.info(
                "全局重试系统已重置 | 熔断标志已恢复",
                module_name=module_name,
                location=location or "Retry.reset_counters"
            )
        else:
            # 局部重置某个函数
            if func_name in RETRY_COUNTER:
                count = RETRY_COUNTER.pop(func_name)
                logger.info(
                    f"已清除函数 [{func_name}] 的重试计数（原值: {count}）",
                    module_name=module_name,
                    location=location or f"Retry.reset_counter:{func_name}"
                )
            else:
                logger.debug(
                    f"函数 [{func_name}] 无重试记录，无需重置",
                    module_name=module_name,
                    location=location or f"Retry.reset_counter:{func_name}"
                )

            # 检查是否需要恢复全局中止标志（如果其他函数也没超限）
            if RETRY_ABORT_FLAG[ke.KEY_ABORT]:
                total = sum(RETRY_COUNTER.values())
                if total < config.GLOBAL_MAX_RETRIES:
                    RETRY_ABORT_FLAG[ke.KEY_ABORT] = False
                    logger.warning(
                        f"全局重试已恢复：当前总计 {total} < {config.GLOBAL_MAX_RETRIES}",
                        module_name=module_name,
                        location=location
                    )
