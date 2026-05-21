import asyncio
import time
from contextlib import AbstractAsyncContextManager
from typing import Optional
from .decorator_utils import log_function_event
from app.common import keys as ke


class AsyncTimer:
    """异步性能计时上下文管理器（用于 async/await 环境）"""

    def __init__(self, name: str, module: str = "性能统计"):
        self.name = name
        self.module = module
        self.start_time: Optional[float] = None
        self.duration: Optional[float] = None

    async def __aenter__(self):
        self.start_time = time.perf_counter()
        log_function_event(
            action=ke.KEY_START,
            func_name=self.name,
            module_name=self.module,
            start_timestamp=self.start_time
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.duration = time.perf_counter() - self.start_time

        if exc_type is None:
            log_function_event(
                action=ke.KEY_SUCCESS,
                func_name=self.name,
                module_name=self.module,
                duration=self.duration
            )
        else:
            log_function_event(
                action=ke.KEY_FAILURE,
                func_name=self.name,
                module_name=self.module,
                duration=self.duration,
                exception=f"{exc_type.__name__}: {str(exc_val)}"
            )
        return False


class AsyncTimeout(AbstractAsyncContextManager):
    """异步超时上下文管理器（Python 3.10 兼容）"""

    def __init__(self, timeout: float, name: str, module: str = "超时控制"):
        self.timeout = timeout
        self.name = name
        self.module = module
        self._task: Optional[asyncio.Task] = None

    async def __aenter__(self):
        log_function_event(
            action=ke.KEY_START,
            func_name=self.name,
            module_name=self.module,
            timeout=self.timeout
        )
        # 注意：不在此处启动超时，而是在 __aexit__ 中配合 wait_for 使用
        # 实际超时逻辑由装饰器或外部协程控制
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # 此类不直接管理超时，仅用于日志。
        # 超时由 asyncio.wait_for 在装饰器中处理。
        # 所以这里只记录结果。
        if isinstance(exc_val, asyncio.TimeoutError):
            log_function_event(
                action=ke.KEY_TIMEOUT,
                func_name=self.name,
                module_name=self.module,
                timeout=self.timeout
            )
        elif exc_type is None:
            log_function_event(
                action=ke.KEY_SUCCESS,
                func_name=self.name,
                module_name=self.module
            )
        else:
            log_function_event(
                action=ke.KEY_EXCEPTION,
                func_name=self.name,
                module_name=self.module,
                exception=f"{exc_type.__name__}: {str(exc_val)}"
            )
        return False
