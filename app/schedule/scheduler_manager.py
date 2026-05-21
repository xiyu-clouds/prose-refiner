import importlib
import pkgutil
from .registry import get_all_tasks
from .task_scheduler import TaskScheduler
from app.common import keys as ke
from app.common import values as va
from app.utils.logger import LoggerManager as logger


class SchedulerManager:
    """
    调度管理器：单例 + 自动发现 + 自动注册
    """
    CHINESE_NAME = "调度管理器"

    _instance = None
    _scheduler: TaskScheduler = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._scheduler = TaskScheduler()
        return cls._instance

    @staticmethod
    def _discover_tasks():
        """
        自动发现并导入所有任务模块
        扫描 state_of_mind/tasks/ 下的所有 .py 文件
        """
        try:
            tasks_module = importlib.import_module(va.VAL_TASKS_PACKAGE)
            package_path = tasks_module.__path__

            logger.info(
                f"🔍 开始扫描任务模块: {va.VAL_TASKS_PACKAGE}",
                module_name=SchedulerManager.CHINESE_NAME
            )

            for _, module_name, _ in pkgutil.iter_modules(package_path):
                module_full_name = f"{va.VAL_TASKS_PACKAGE}.{module_name}"
                try:
                    importlib.import_module(module_full_name)
                    logger.info(
                        f"✅ 加载任务模块: {module_full_name}",
                        module_name=SchedulerManager.CHINESE_NAME
                    )
                except Exception as e:
                    logger.error(
                        f"❌ 加载任务模块失败: {module_full_name}, 错误: {str(e)}",
                        module_name=SchedulerManager.CHINESE_NAME,
                        exc_info=True
                    )
        except Exception as e:
            logger.error(
                f"❌ 扫描任务模块时出错: {str(e)}",
                module_name=SchedulerManager.CHINESE_NAME,
                exc_info=True
            )

    def start(self):
        """启动调度器：自动发现 -> 注册 -> 启动"""
        logger.info(
            "🚀 开始启动通用定时任务系统...",
            module_name=self.CHINESE_NAME
        )

        # 1. 自动发现所有任务模块（触发装饰器注册）
        self._discover_tasks()

        # 2. 从注册中心获取所有任务并添加到调度器
        all_tasks = get_all_tasks()
        if not all_tasks:
            logger.warning(
                "⚠️ 未发现任何任务，请检查任务模块是否正确注册",
                module_name=self.CHINESE_NAME
            )
            return

        logger.info(
            f"🎉 共发现 {len(all_tasks)} 个任务，正在注册...",
            module_name=self.CHINESE_NAME
        )

        for task_id, task_config in all_tasks.items():
            try:
                self._scheduler.add_job(
                    func=task_config[ke.KEY_FUNC],
                    trigger=task_config[ke.KEY_TRIGGER],
                    id=task_id,
                    name=task_config[ke.KEY_NAME],
                    **task_config[ke.KEY_TRIGGER_ARGS]
                )
            except Exception as e:
                logger.error(
                    f"❌ 注册任务失败: {task_id}, 错误: {str(e)}",
                    module_name=self.CHINESE_NAME,
                    exc_info=True
                )

        # 3. 启动调度器
        logger.info(
            "✅ 所有任务注册完成，准备启动调度器...",
            module_name=self.CHINESE_NAME
        )
        self._scheduler.start()

    def shutdown(self):
        """关闭调度器"""
        self._scheduler.shutdown()

    def list_jobs(self):
        """列出当前运行的任务"""
        return self._scheduler.list_jobs()

    def pause_job(self, job_id: str):
        self._scheduler.pause_job(job_id)

    def resume_job(self, job_id: str):
        self._scheduler.resume_job(job_id)

    def remove_job(self, job_id: str):
        self._scheduler.remove_job(job_id)
