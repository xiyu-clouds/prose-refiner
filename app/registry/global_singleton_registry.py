from __future__ import annotations
import asyncio
import hashlib
import json
import threading
from typing import Dict, Optional, ClassVar, Any
from app.common import keys as ke
from app.common.llm_constants import LLMModelType, LLMVendor, LLMTypeVendorModelMapping
from app.core.collector.execution_context import ExecutionCollector
from app.core.engine.executor import LLMExecutor
from app.core.meta.graphs.main import build_and_compile_metacognition_graph
from app.core.prompt.prompt_builder import PromptBuilder
from app.utils.llm_utils import create_langchain_model
from app.utils.logger import LoggerManager as logger


class GlobalSingletonRegistry:
    """
    全局单例注册中心
    """
    CHINESE_NAME = "全局单例注册中心"

    _instance: Optional['GlobalSingletonRegistry'] = None
    _init_lock: ClassVar[asyncio.Lock] = None

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return

        self._config_version = 0
        self._last_seen_version = 0
        self._executors: Dict[str, LLMExecutor] = {}
        self._metacognition_graph: Optional[Any] = None
        self._executor_lock: Optional[asyncio.Lock] = asyncio.Lock()
        self._graph_lock: threading.Lock = threading.Lock()
        builder = PromptBuilder()
        self.builder = builder
        self._initialized = True

    @classmethod
    async def get_instance(cls) -> GlobalSingletonRegistry:
        """获取单例实例"""
        if cls._instance is not None:
            return cls._instance

        if cls._init_lock is None:
            cls._init_lock = asyncio.Lock()

        async with cls._init_lock:
            if cls._instance is None:
                cls._instance = cls()
                logger.info("🟢 全局单例注册中心已初始化", module_name=cls.CHINESE_NAME)

        return cls._instance

    @classmethod
    def increment_config_version(cls):
        """配置中心调用：原子增加版本号"""
        if cls._instance:
            cls._instance._config_version += 1
            logger.info(f"🆙 配置版本号已更新: {cls._instance._config_version}")

    # --------------------------------------------------------------------------
    # 核心入口
    # --------------------------------------------------------------------------
    async def get_executor(
            self,
            model_type: str = LLMModelType.TEXT,
            vendor: Optional[str] = None,
            model: Optional[str] = None,
            api_key: Optional[str] = None,
            temperature: Optional[float] = None,
            top_p: Optional[float] = None,
            max_tokens: Optional[int] = None,
            timeout: Optional[int] = None,
            response_format: dict = None,
            use_recommended_params: bool = True,  # 是否使用推荐参数
            **kwargs
    ) -> LLMExecutor:
        from app.config.config import config
        vendor = vendor or config.LLM_DEFAULT_VENDOR
        model = model or config.LLM_DEFAULT_MODEL
        timeout = timeout or config.LLM_API_TIMEOUT

        if not api_key:
            api_key = LLMVendor.get_api_key(vendor)

        if api_key and isinstance(api_key, str) and "请输入" in api_key:
            raise ValueError(f"🚨 拒绝创建 Executor：API Key 无效，包含 '请输入'。当前值: {api_key}")

        # 三级校验
        if not LLMTypeVendorModelMapping.is_valid(model_type, vendor, model):
            raise ValueError(f"模型非法：{ke.KEY_TYPE}={model_type}, {ke.KEY_VENDOR}={vendor}, {ke.KEY_MODEL}={model}")

        # 如果启用推荐参数，优先使用推荐值（但不会覆盖已明确传入的值）
        params = config.LLM_PARAMS if use_recommended_params else {}

        # 优先级：明确传入 > 推荐参数 > 默认值
        temperature = temperature if temperature is not None else params.get(ke.KEY_TEMPERATURE)
        top_p = top_p if top_p is not None else params.get(ke.KEY_TOP_P)
        max_tokens = max_tokens if max_tokens is not None else params.get(ke.KEY_MAX_TOKENS)
        response_format = response_format if response_format is not None else params.get(ke.KEY_RESPONSE_FORMAT)

        cache_key = self._make_cache_key(
            model_type, vendor, model, api_key, temperature, top_p, max_tokens, timeout
        )

        # 获取当前全局配置版本
        current_version = self._config_version

        async with self._executor_lock:
            # 双重检查锁模式
            # 如果全局版本号 和 我上次记录的版本号 不一样，说明配置变了！
            if hasattr(self, '_last_seen_version') and self._last_seen_version != current_version:
                logger.info(f"⚡ 检测到配置版本变更 (v{self._last_seen_version} -> v{current_version})，强制清空缓存")
                self._executors.clear()
                # 更新我看到的最新版本号
                self._last_seen_version = current_version

            if cache_key not in self._executors:
                # 构建标准参数包
                basic_params = {
                    ke.KEY_MODEL: model,
                    ke.KEY_API_KEY: api_key,
                    ke.KEY_TIMEOUT: timeout,
                    ke.KEY_TEMPERATURE: temperature,
                    ke.KEY_TOP_P: top_p,
                    ke.KEY_MAX_TOKENS: max_tokens,
                    **kwargs
                }
                if response_format:
                    basic_params[ke.KEY_RESPONSE_FORMAT] = response_format

                # 调用元数据驱动的工厂方法
                llm = create_langchain_model(vendor, basic_params)
                self._executors[cache_key] = LLMExecutor(vendor=vendor, model=model, chat_model=llm)
            return self._executors[cache_key]

    # --------------------------------------------------------------------------
    # 缓存 KEY
    # --------------------------------------------------------------------------
    @staticmethod
    def _make_cache_key(model_type, vendor, model, api_key, temp, top_p, max_t, timeout):
        d = {
            ke.KEY_T: model_type, ke.KEY_V: vendor, ke.KEY_M: model,
            ke.KEY_K: hashlib.md5(api_key.encode()).hexdigest()[:8],
            ke.KEY_TMP: temp, ke.KEY_TP: top_p, ke.KEY_MT: max_t, ke.KEY_TO: timeout
        }
        return hashlib.md5(json.dumps(d, sort_keys=True).encode()).hexdigest()

    # --------------------------------------------------------------------------
    # 清理 & 重载
    # --------------------------------------------------------------------------
    async def async_clear_llm_caches(self):
        async with self._executor_lock:
            self._executors.clear()

    async def get_metacognition_graph(self, model_type=LLMModelType.TEXT):
        if self._metacognition_graph is None:
            with self._graph_lock:
                if self._metacognition_graph is None:  # double-check
                    collector = await ExecutionCollector.get_instance()
                    # 清空一下，避免数据污染
                    await collector.clear()
                    executor = await self.get_executor(model_type=model_type)
                    self._metacognition_graph = build_and_compile_metacognition_graph(executor, collector)
        return self._metacognition_graph

    async def reload_all(self):
        await self.async_clear_llm_caches()
        with self._graph_lock:
            self._metacognition_graph = None
        self.builder.reload_dao()
        logger.info("♻️ 全局已重载：LLM / 插件 / 图", module_name=self.CHINESE_NAME)
