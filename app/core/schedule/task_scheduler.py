from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.job import Job
from typing import Callable, Dict, Optional
import atexit
import signal
from app.common import keys as ke
from app.common import values as va
from app.utils.logger import LoggerManager as logger


class TaskScheduler:
    """
    通用定时任务调度器
    支持 cron、interval、date 三种触发方式
    """
    CHINESE_NAME = "定时任务调度器"

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self._jobs: Dict[str, Job] = {}  # 任务ID -> Job 映射
        self._setup_shutdown_hook()

    def _setup_shutdown_hook(self):
        """注册优雅关闭钩子"""
        atexit.register(self.shutdown)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        sig_name = va.VAL_SIGNAL_CONFIG_DICT.get(signum, signum)
        logger.info(
            f"收到退出信号 {sig_name}，准备关闭调度器...",
            module_name=self.CHINESE_NAME
        )
        self.shutdown()

    def add_job(
            self,
            func: Callable,
            trigger: str,
            id: str,
            name: Optional[str] = None,
            **trigger_args
    ):
        """
        添加定时任务

        :param func: 任务函数
        :param trigger: 触发器类型 'cron' | 'interval' | 'date'
        :param id: 任务唯一ID（用于管理）
        :param name: 任务名称（日志显示）
        :param trigger_args: 触发器参数，如 hour=8, minute=0
        """
        if id in self._jobs:
            logger.warning(
                f"任务已存在，将被替换: {id}",
                module_name=self.CHINESE_NAME
            )
            self.remove_job(id)

        # 构建触发器
        try:
            if trigger == ke.KEY_CRON:
                trigger_instance = CronTrigger(**trigger_args)
            elif trigger == ke.KEY_INTERVAL:
                trigger_instance = IntervalTrigger(**trigger_args)
            elif trigger == ke.KEY_DATE:
                trigger_instance = DateTrigger(**trigger_args)
            else:
                raise ValueError(f"不支持的触发器类型: {trigger}")

            job = self.scheduler.add_job(
                func=func,
                trigger=trigger_instance,
                id=id,
                name=name or func.__name__,
                misfire_grace_time=60,  # 任务错过执行时间后，最多延迟60秒执行
                max_instances=1,  # 防止并发执行
                coalesce=True  # 合并多次错过的执行
            )
            self._jobs[id] = job
            logger.info(
                f"任务已注册: ID={id}, 名称='{job.name}', 触发器={trigger.upper()}",
                module_name=self.CHINESE_NAME
            )
            logger.info(
                f"任务详情: {job}",
                module_name=self.CHINESE_NAME
            )

        except Exception as e:
            logger.error(
                f"注册任务失败: ID={id}, 错误={str(e)}",
                module_name=self.CHINESE_NAME,
                exc_info=True
            )
            raise

    def remove_job(self, job_id: str):
        """移除任务"""
        if job_id in self._jobs:
            self.scheduler.remove_job(job_id)
            del self._jobs[job_id]
            logger.info(
                f"任务已移除: {job_id}",
                module_name=self.CHINESE_NAME
            )
        else:
            logger.warning(
                f"尝试移除不存在的任务: {job_id}",
                module_name=self.CHINESE_NAME
            )

    def pause_job(self, job_id: str):
        """暂停任务"""
        if job_id in self._jobs:
            self.scheduler.pause_job(job_id)
            logger.info(
                f"任务已暂停: {job_id}",
                module_name=self.CHINESE_NAME
            )
        else:
            logger.warning(
                f"无法暂停，任务不存在: {job_id}",
                module_name=self.CHINESE_NAME
            )

    def resume_job(self, job_id: str):
        """恢复任务"""
        if job_id in self._jobs:
            self.scheduler.resume_job(job_id)
            logger.info(
                f"任务已恢复: {job_id}",  # 修正：原代码写成了“已暂停”，应为“已恢复”
                module_name=self.CHINESE_NAME
            )
        else:
            logger.warning(
                f"无法恢复，任务不存在: {job_id}",
                module_name=self.CHINESE_NAME
            )

    def list_jobs(self):
        """列出所有任务"""
        jobs = self.scheduler.get_jobs()
        logger.info(
            f"当前共有 {len(jobs)} 个任务:",
            module_name=self.CHINESE_NAME
        )
        for job in jobs:
            logger.info(
                f"   [{job.id}] {job.name} - 下次执行: {job.next_run_time}",
                module_name=self.CHINESE_NAME
            )
        return jobs

    def start(self):
        """启动调度器"""
        if self.scheduler.running:
            logger.warning(
                "调度器已在运行中",
                module_name=self.CHINESE_NAME
            )
            return

        logger.info(
            "开始启动通用任务调度器...",
            module_name=self.CHINESE_NAME
        )
        try:
            self.scheduler.start()
            logger.info(
                "调度器已启动，等待任务触发...",
                module_name=self.CHINESE_NAME
            )
            self.list_jobs()
        except Exception as e:
            logger.error(
                f"调度器运行异常: {str(e)}",
                module_name=self.CHINESE_NAME,
                exc_info=True
            )
            raise

    def shutdown(self):
        """关闭调度器"""
        if self.scheduler.running:
            logger.info(
                "正在关闭调度器...",
                module_name=self.CHINESE_NAME
            )
            self.scheduler.shutdown()
            self._jobs.clear()
            logger.info(
                "调度器已安全关闭",
                module_name=self.CHINESE_NAME
            )
        else:
            logger.info(
                "调度器未运行，无需关闭",
                module_name=self.CHINESE_NAME
            )
