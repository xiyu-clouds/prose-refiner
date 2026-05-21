import asyncio
import time
from functools import wraps
from typing import Callable, Any
from .async_context_manager import AsyncTimer
from app.common import keys as ke


def async_performance_guard(timeout: float = 120.0, module: str = "服务监控"):
    """
    异步装饰器：为 async 函数添加性能统计 + 超时保护（Python 3.10 兼容）

    Usage:
        @async_performance_guard(timeout=10, module="LLM调用")
        async def call_llm(prompt: str) -> str:
            await asyncio.sleep(5)
            return "response"
    """

    def decorator(func: Callable) -> Callable:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError(f"函数 {func.__name__} 不是 async 函数，不能使用 async_performance_guard")

        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            func_name = func.__name__
            start = time.perf_counter()

            # 记录开始
            from .decorator_utils import log_function_event
            log_function_event(
                action=ke.KEY_START,
                func_name=func_name,
                module_name=module,
                start_timestamp=start,
                timeout=timeout
            )

            try:
                # 使用 asyncio.wait_for 实现超时（Python 3.10 标准方式）
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
                duration = time.perf_counter() - start
                log_function_event(
                    action=ke.KEY_SUCCESS,
                    func_name=func_name,
                    module_name=module,
                    duration=duration
                )
                return result

            except asyncio.TimeoutError:
                duration = time.perf_counter() - start
                log_function_event(
                    action=ke.KEY_TIMEOUT,
                    func_name=func_name,
                    module_name=module,
                    duration=duration,
                    timeout=timeout
                )
                # 抛出标准 TimeoutError（或保留 asyncio.TimeoutError）
                raise TimeoutError(f"函数 {func_name} 执行超时，超过 {timeout} 秒")

            except Exception as e:
                duration = time.perf_counter() - start
                log_function_event(
                    action=ke.KEY_FAILURE,
                    func_name=func_name,
                    module_name=module,
                    duration=duration,
                    exception=f"{type(e).__name__}: {e}"
                )
                raise

        return wrapper

    return decorator


# 单独的 async timed 装饰器
def async_timed(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        async with AsyncTimer(func.__name__, module="性能统计"):
            return await func(*args, **kwargs)

    return wrapper


# 单独的 async timeout 装饰器
def async_with_timeout(timeout=60):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)

        return wrapper

    return decorator
