from app.utils.logger import LoggerManager as logger
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .scheduler_manager import SchedulerManager

CHINESE_NAME = "定时任务启动器"


def start_scheduled_tasks() -> 'SchedulerManager':
    """统一入口：启动所有注册的定时任务"""
    try:
        # 延迟导入，避免顶层副作用
        from .scheduler_manager import SchedulerManager

        scheduler = SchedulerManager()
        scheduler.start()
        logger.info(
            "定时任务调度器已在后台启动。",
            module_name=CHINESE_NAME
        )
        return scheduler
    except Exception as e:
        logger.exception(
            f"启动定时任务调度器失败: {str(e)}",
            module_name=CHINESE_NAME,
            exc_info=True
        )
        raise
