from functools import wraps
from typing import Callable, Dict, Any, Optional
import time
from app.common import keys as ke
from app.utils.logger import LoggerManager as logger

_task_registry: Dict[str, Dict[str, Any]] = {}


def register_task(
        id: str,
        trigger: str,
        name: Optional[str] = None,
        **trigger_args
):
    def decorator(func: Callable) -> Callable:
        if id in _task_registry:
            logger.warning(
                f"任务ID重复: {id}，将被覆盖",
                module_name="任务注册中心"
            )

        task_name = name or func.__name__

        _task_registry[id] = {
            ke.KEY_FUNC: func,
            ke.KEY_TRIGGER: trigger,
            ke.KEY_NAME: task_name,
            ke.KEY_TRIGGER_ARGS: trigger_args
        }
        logger.info(
            f"任务已注册: {id} | {task_name} ({trigger})",
            module_name="任务注册中心"
        )

        @wraps(func)
        def wrapper(*args, **kwargs):
            logger.info(
                f"开始执行: {task_name}",
                module_name="任务执行"
            )
            start = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start
                logger.info(
                    f"成功 | {task_name} 耗时 {duration:.2f}s",
                    module_name="任务执行"
                )
                return result
            except Exception as e:
                duration = time.time() - start
                logger.error(
                    f"失败 | {task_name} 耗时 {duration:.2f}s | {str(e)}",
                    module_name="任务执行",
                    exc_info=True
                )
                raise

        return wrapper

    return decorator


def get_all_tasks():
    return _task_registry.copy()


def clear_registry():
    _task_registry.clear()
