import asyncio
from typing import List, Callable, Any, Awaitable


class ConcurrencyManager:
    """通用并发控制器，用于限制同时执行的异步任务数量"""
    CHINESE_NAME = "通用并发控制器"

    def __init__(self, max_concurrent: int):
        if max_concurrent <= 0:
            raise ValueError("最大并发数必须为正数")
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def run_tasks(self, tasks: List[Callable[[], Awaitable[Any]]]) -> List[Any]:
        """
        并发执行一组无参异步任务，受内部信号量限制。
        注意：每个 task 必须是 **无参可调用对象**（如 lambda 或 partial），
              且返回一个 awaitable（通常是协程）。
        """
        if not tasks:
            return []

        async def _limited_task(task: Callable[[], Awaitable[Any]]) -> Any:
            async with self.semaphore:
                return await task()

        results = await asyncio.gather(*[_limited_task(t) for t in tasks], return_exceptions=False)
        return list(results)

    async def run_tasks_with_exceptions(
            self,
            tasks: List[Callable[[], Awaitable[Any]]]
    ) -> List[Any]:
        """
        与 run_tasks 类似，但允许任务失败，返回结果中可能包含 Exception。
        适用于批量场景需要部分成功的场景。
        """
        if not tasks:
            return []

        async def _limited_task(task: Callable[[], Awaitable[Any]]) -> Any:
            async with self.semaphore:
                return await task()

        results = await asyncio.gather(
            *[_limited_task(t) for t in tasks],
            return_exceptions=True
        )
        return list(results)
