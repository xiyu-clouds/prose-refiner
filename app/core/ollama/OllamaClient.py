import asyncio
import hashlib
import json
from typing import Dict, Optional, List, Any
import aiohttp
from app.common import keys as ke
from app.config.config import config
from app.utils.async_decorators import async_performance_guard
from app.utils.logger import LoggerManager as logger
from app.utils.retry_util import retry_decorator


class OllamaClient:
    """
    基于全局架构的 Ollama 客户端
    """
    _instance: Optional["OllamaClient"] = None
    _lock = asyncio.Lock()  # 异步锁：用于保护 Session 的初始化
    CHINESE_NAME = "Ollama客户端"

    def __new__(cls):
        # 第一次检查：快速失败，避免不必要的锁竞争
        if cls._instance is None:
            # 注意：在纯异步环境中，严格的双重检查锁需要配合异步锁使用
            # 但由于 __new__ 是同步方法，我们无法在这里 await lock
            # 因此，这里保留经典的同步双重检查，主要防止多线程启动协程的情况
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._base_url = config.OLLAMA_BASE_URL.rstrip("/")
        self._model = config.OLLAMA_MODEL
        self._timeout = aiohttp.ClientTimeout(total=config.OLLAMA_TIMEOUT)
        self._cache: Dict[str, str] = {}
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """异步安全的 Session 单例获取 (使用双重检查锁)"""
        # 第一次检查：如果 Session 已存在且未关闭，直接返回 (无锁，高性能)
        if self._session is not None and not self._session.closed:
            return self._session

        # 加锁：防止多个协程同时创建 Session
        async with self._lock:
            # 第二次检查：进入锁后，再次确认 Session 状态
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(timeout=self._timeout)
                logger.info("🆕 创建 Ollama HTTP Session", module_name=self.CHINESE_NAME)

            return self._session

    @retry_decorator(
        max_retries=config.DEFAULT_RETRY_CONFIG.get("max_retries"),
        enable_exp_backoff=config.DEFAULT_RETRY_CONFIG.get("enable_exp_backoff"),
        exp_multiplier=config.DEFAULT_RETRY_CONFIG.get("exp_multiplier"),
        exp_max_wait=config.DEFAULT_RETRY_CONFIG.get("exp_max_wait"),
        min_wait=config.DEFAULT_RETRY_CONFIG.get("min_wait"),
        reraise=config.DEFAULT_RETRY_CONFIG.get("reraise"),
        module_name=CHINESE_NAME,
        location="OllamaClient._make_request"
    )
    @async_performance_guard(timeout=config.OLLAMA_TIMEOUT + 10, module=CHINESE_NAME)
    async def _make_request(self, endpoint: str, payload: Dict) -> Dict:
        """
        核心网络请求
        逻辑: 仅负责发请求和拿结果，异常交给装饰器处理
        """
        session = await self._get_session()

        logger.debug(f"📤 请求: {endpoint} | 模型: {self._model}", module_name=self.CHINESE_NAME)

        async with session.post(f"{self._base_url}{endpoint}", json=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()
            if data.get(ke.KEY_ERROR):
                raise Exception(f"Ollama Error: {data[ke.KEY_ERROR]}")

            return data

    async def chat(self, messages: List[Dict[str, str]], options: Optional[dict], **kwargs) -> str:
        """
        普通对话接口
        返回: str (原始文本)
        """
        result = await self._chat_internal(messages, response_format=None, options=options, **kwargs)
        return result if isinstance(result, str) else ""

    async def chat_json(self, messages: List[Dict[str, str]], options: Optional[dict], **kwargs) -> Dict:
        """
        JSON 专用接口
        返回: Dict (解析后的字典)
        """
        result = await self._chat_internal(messages, response_format="json", options=options, **kwargs)
        return result if isinstance(result, dict) else {}

    async def _chat_internal(self, messages: List[Dict[str, str]], response_format: Optional[str], options: Optional[dict], **kwargs) -> Any:
        """
        内部核心实现
        """
        if not config.OLLAMA_ENABLED:
            return "" if response_format is None else {}

        options = options if options else config.OLLAMA_PARAMS.copy()
        options.update(kwargs)
        payload = {
            ke.KEY_MODEL: self._model,
            ke.KEY_MESSAGES: messages,
            ke.KEY_STREAM: False,
            ke.KEY_OPTIONS: options
        }

        # 只有当需要 JSON 时才添加该参数
        if response_format == "json":
            payload[ke.KEY_FORMAT] = "json"

        cache_key = self._generate_cache_key(payload)
        if cache_key in self._cache:
            logger.debug(f"💾 缓存命中: {cache_key[:8]}", module_name=self.CHINESE_NAME)
            return self._cache[cache_key]

        try:
            result = await self._make_request("/api/chat", payload)

            if not result or ke.KEY_MESSAGE not in result:
                logger.error("❌ 响应数据缺失 'message' 字段", module_name=self.CHINESE_NAME)
                return "" if response_format is None else {}

            raw_content = result[ke.KEY_MESSAGE][ke.KEY_CONTENT]
            final_data: Any

            if response_format == "json":
                # JSON 模式：尝试解析
                try:
                    final_data = json.loads(raw_content)
                except json.JSONDecodeError as e:
                    logger.error(f"❌ JSON解析失败: {e}", module_name=self.CHINESE_NAME)
                    final_data = {}
            else:
                # 普通模式：直接返回文本
                final_data = raw_content.strip()

            # 缓存结果
            if cache_key:
                self._cache[cache_key] = final_data

            return final_data

        except Exception as e:
            logger.error(f"❌ 对话失败: {e}", module_name=self.CHINESE_NAME)
            return "" if response_format is None else {}

    @staticmethod
    def _generate_cache_key(payload: Dict) -> str:
        """生成缓存 Key"""
        cache_input = {
            ke.KEY_MODEL: payload[ke.KEY_MODEL],
            ke.KEY_MESSAGES: payload[ke.KEY_MESSAGES],
            ke.KEY_OPTIONS: payload[ke.KEY_OPTIONS]
        }
        raw_str = json.dumps(cache_input, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(raw_str.encode(ke.KEY_UTF_8)).hexdigest()
