import threading
from typing import Optional
from langsmith.run_helpers import traceable
from app.common import keys as ke
from app.common import values as va
from app.utils.logger import LoggerManager as logger


class LangSmithConfig:
    _instance: Optional['LangSmithConfig'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'LangSmithConfig':
        """确保只有一个实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化配置 - 仅在首次创建实例时执行"""
        # 防止重复初始化
        if hasattr(self, ke.KEY__INITIALIZED):
            return

        # 初始化默认值
        self.enabled = False
        self.api_key = ''
        self.project_name = va.VAL_LANGSMITH_PROJECT
        self.endpoint = va.VAL_LANGSMITH_ENDPOINT
        self._initialized = True

    @classmethod
    def get_instance(cls) -> 'LangSmithConfig':
        """获取单例实例 - 同步版本"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance.__init__()
        return cls._instance

    async def setup_from_config(self, config) -> None:
        """从全局配置设置 LangSmith 参数"""
        if not hasattr(self, ke.KEY__INITIALIZED):
            raise RuntimeError("LangSmithConfig 未正确初始化")

        self.enabled = getattr(config, 'LANGSMITH_ENABLED', False)
        self.api_key = getattr(config, 'LANGSMITH_API_KEY', '')
        self.project_name = getattr(config, 'LANGSMITH_PROJECT', va.VAL_LANGSMITH_PROJECT)
        self.endpoint = getattr(config, 'LANGSMITH_ENDPOINT', va.VAL_LANGSMITH_ENDPOINT)

        # 设置 LangChain 环境变量
        if self.enabled and self.api_key:
            import os
            os.environ[va.VAL_LANGCHAIN_TRACING_V2] = ke.KEY_TRUE
            os.environ[va.VAL_LANGCHAIN_API_KEY] = self.api_key
            os.environ[va.VAL_LANGCHAIN_PROJECT] = self.project_name
            os.environ[va.VAL_LANGCHAIN_ENDPOINT] = self.endpoint
            logger.info(f"LangSmith 已启用 | 项目: {self.project_name}")
        elif self.enabled:
            logger.warning("LANGSMITH_ENABLED=true 但未提供 API KEY，LangSmith 将不会启用")
            self.enabled = False
        else:
            logger.info("LangSmith 未启用")

    @classmethod
    async def initialize_with_config(cls, config) -> None:
        """异步初始化并配置 LangSmith"""
        instance = cls.get_instance()  # 使用同步方法
        await instance.setup_from_config(config)

    def get_trace_decorator(self, name: str, run_type: str = ke.KEY_CHAIN) -> callable:
        """获取 trace 装饰器"""
        if self.enabled:
            return traceable(name=name, run_type=run_type)  # type: ignore
        else:
            def no_op_decorator(func):
                return func

            return no_op_decorator

    def is_enabled(self) -> bool:
        """检查是否启用"""
        return self.enabled


def with_langsmith_trace(name: str, run_type: str = ke.KEY_CHAIN) -> callable:
    """装饰器：为函数添加 LangSmith 追踪"""
    config = LangSmithConfig.get_instance()
    return config.get_trace_decorator(name, run_type)
