import time
from typing import Optional, Callable, Dict, Awaitable, Any, Tuple, List
import httpx
from app.cache.llm_cache import LLMCache
from app.cache.redis import RedisLLMCache
from app.common.enums import StorageType
from app.common.llm_constants import LLMVendor, LLMModel
from app.common.llm_response import LLMResponse
from app.config.config import config
from app.cache.base import BaseCache
from app.core.tracer.langsmith_wrapper import with_langsmith_trace
from app.core.tracer.token_tracker import TokenUsageTracker
from app.utils.async_decorators import async_performance_guard
from app.utils.llm_utils import extract_content_from_response, map_params_to_vendor, remove_check, extract_json_safely
from app.utils.retry_util import retry_decorator
from langchain_core.language_models import BaseChatModel
from app.common import keys as ke
from app.utils.logger import LoggerManager as logger
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage


class LLMExecutor:
    """
    生产级 LLM 执行器
    核心逻辑：
    1. retry_decorator：熔断、重试
    2. async_performance_guard：超时、耗时
    3. LLMExecutor：业务适配、Token统计、结果封装
    """

    CHINESE_NAME = "心海推理网关"

    # JSON 模式系统提示词
    _JSON_SYSTEM_PROMPT = (
        "你必须输出一个严格的 JSON 对象。不要有任何额外文字解释、前缀、后缀或 "
        "Markdown 代码块。确保输出是有效的 json 格式。"
    )

    def __init__(
            self,
            vendor: str,
            model: str,
            chat_model: BaseChatModel,
            timeout: float = 120.0
    ):
        self.vendor = vendor
        self.model = model
        self.chat_model = chat_model
        self.timeout = config.TEXT_API_TIMEOUT or timeout
        self._retry_wrapper = retry_decorator(
            max_retries=config.DEFAULT_RETRY_CONFIG.get(ke.KEY_MAX_RETRIES) or 3,
            enable_exp_backoff=config.DEFAULT_RETRY_CONFIG.get(ke.KEY_ENABLE_EXP_BACKOFF) or True,
            exp_multiplier=config.DEFAULT_RETRY_CONFIG.get(ke.KEY_EXP_MULTIPLIER) or 1.0,
            exp_max_wait=config.DEFAULT_RETRY_CONFIG.get(ke.KEY_EXP_MAX_WAIT) or 10.0,
            min_wait=config.DEFAULT_RETRY_CONFIG.get(ke.KEY_MIN_WAIT) or 0.1,
            reraise=config.DEFAULT_RETRY_CONFIG.get(ke.KEY_RERAISE) or True,
            module_name=self.CHINESE_NAME,
            location=f"{vendor}.{model}"
        )
        # 获取厂商的参数映射表，用于运行时参数映射
        vendor_meta = LLMVendor.get_metadata(vendor)
        self._params_map = vendor_meta.get(ke.KEY_PARAMS_MAP, {})
        self.llm_cache = self._create_cache_backend(config)

        self._invoke = self._build_invoke()
        self.reasoning_auto_inject = config.REASONING_AUTO_INJECT
        self.reasoning_effort_map = config.REASONING_EFFORT_MAP

    async def _build_messages(
            self,
            prompt: str,
            is_json: bool,
    ) -> List[BaseMessage]:
        """
        构建消息列表（仅拼接 system + user）

        Returns:
            messages: LangChain 消息列表（可直接传给 ainvoke）
        """
        if is_json:
            messages: List[BaseMessage] = [
                SystemMessage(content=self._JSON_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        else:
            messages = [HumanMessage(content=prompt)]

        return messages

    def _build_callbacks(self, **kwargs) -> Tuple[TokenUsageTracker, list]:
        """构建回调列表，返回 (tracker, all_callbacks)"""
        tracker = TokenUsageTracker(vendor=self.vendor)
        existing = kwargs.pop(ke.KEY_CALLBACKS, []) or []
        if not isinstance(existing, list):
            existing = [existing]
        all_callbacks = [tracker] + existing
        return tracker, all_callbacks

    @staticmethod
    def _assemble_cost(
            tracker: TokenUsageTracker,
    ) -> Dict[str, Any]:
        """
        组装最终 cost 字典：API 用量（扁平化、语义清晰）
        """
        cost = tracker.to_dict()  # {prompt, completion, total, cached_tokens, ...}
        return cost

    # --------------------------------------------------------------------------
    # 内部构建
    # --------------------------------------------------------------------------
    def _build_invoke(self):
        @self._retry_wrapper
        @async_performance_guard(timeout=self.timeout)
        async def _inner(prompt: str, **kwargs):
            # ---- 1. 提取控制参数 ----
            is_json = kwargs.pop(ke.KEY__IS_JSON, False)
            prompt_id = kwargs.pop(ke.KEY_PROMPT_ID, "未知步骤ID")
            type_str = kwargs.pop(ke.KEY_TYPE_STR, "未知能力ID")

            # 提取 max_tokens 覆盖值（扩容重试时动态调整）。
            # 必须用 bind() 覆盖：LangChain ChatDeepSeek 实例化时已绑定 max_tokens，
            # 通过 ainvoke(**kwargs) 传递的 max_tokens 会被模型级参数忽略，导致扩容无效。
            max_tokens_override = kwargs.pop(ke.KEY_MAX_TOKENS, None)

            start_time = time.time()

            # ---- 2. 构建回调 ----
            tracker, all_callbacks = self._build_callbacks(**kwargs)
            chat_model = self.chat_model
            if max_tokens_override is not None:
                chat_model = chat_model.bind(max_tokens=max_tokens_override)
            chat_model = chat_model.with_config(
                run_name=ke.KEY_UP_LLM_CALL,
                callbacks=all_callbacks,
            )

            try:
                # ---- 3. 构建消息 ----
                messages = await self._build_messages(
                    prompt, is_json
                )

                # ---- 4. 调用模型（统一接口，messages 一定是 List[BaseMessage]）----
                resp = await chat_model.ainvoke(messages, **kwargs)

                elapsed_ms = (time.time() - start_time) * 1000

                # ---- 5. 提取响应内容 ----
                content = self._extract_response_content(resp)

                # ---- 6. 组装 cost + 日志 ----
                cost = self._assemble_cost(tracker)
                self._log_success(prompt_id, type_str, cost, elapsed_ms)

                return LLMResponse.ok_content(
                    content=content,
                    raw=str(resp),  # 转换为字符串存储
                    vendor=self.vendor,
                    model=self.model,
                    elapsed_ms=elapsed_ms,
                    cost=cost
                )
            except httpx.HTTPStatusError as e:
                return self._handle_api_error(e, prompt_id, type_str, start_time)
            except Exception as e:
                return self._handle_sys_error(e, prompt_id, type_str, start_time)

        return _inner

    def _extract_response_content(self, resp) -> str:
        """从 LLM 响应中提取文本内容"""
        get_dict = getattr(resp, ke.KEY_MODEL_DUMP, None) or getattr(resp, ke.KEY_DICT, None)
        raw_dict = get_dict() if get_dict else {}

        content = extract_content_from_response(raw_dict, self.vendor)
        if not content:
            content = resp.content if hasattr(resp, ke.KEY_CONTENT) else str(resp)
        return content

    def _log_success(
            self,
            prompt_id: str,
            type_str: str,
            cost: Dict,
            elapsed_ms: float,
    ):
        """统一的成功日志"""
        logger.info(
            f"LLM调用成功 | id={prompt_id} | type={type_str} | "
            f"模型={self.vendor}/{self.model} | "
            f"输入={cost.get(ke.KEY_PROMPT, 0)} | "
            f"输出={cost.get(ke.KEY_COMPLETION, 0)} | "
            f"推理={cost.get(ke.KEY_REASONING_TOKENS, 0)} | "
            f"总计={cost.get(ke.KEY_TOTAL, 0)} | "
            f"耗时={elapsed_ms:.2f}ms | "
            f"缓存命中={cost.get(ke.KEY_CACHED_TOKENS, 0)}",
            module_name=self.CHINESE_NAME,
            location=f"{self.vendor}.{self.model}"
        )

    def _handle_api_error(
            self, e: httpx.HTTPStatusError, prompt_id: str, type_str: str, start_time: float
    ) -> LLMResponse:
        status_code = e.response.status_code if e.response else 0
        elapsed_ms = (time.time() - start_time) * 1000
        logger.warning(
            f"API错误 | id={prompt_id} | type={type_str} | "
            f"模型={self.vendor}/{self.model} | 状态码={status_code} | {e}",
            module_name=self.CHINESE_NAME, location=f"{self.vendor}.{self.model}"
        )
        return LLMResponse.api_fail(
            msg=f"API Error [{status_code}]: {e}",
            vendor=self.vendor, model=self.model, elapsed_ms=elapsed_ms
        )

    def _handle_sys_error(
            self, e: Exception, prompt_id: str, type_str: str, start_time: float
    ) -> LLMResponse:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.warning(
            f"调用异常 | id={prompt_id} | type={type_str} | "
            f"模型={self.vendor}/{self.model} | 耗时={elapsed_ms:.2f}ms | {e}",
            module_name=self.CHINESE_NAME, location=f"{self.vendor}.{self.model}"
        )
        return LLMResponse.sys_fail(str(e), self.vendor, self.model, with_stack=True)

    @staticmethod
    def _create_cache_backend(cfg) -> BaseCache:
        storage = cfg.STORAGE_BACKEND
        if storage == StorageType.LOCAL:
            return LLMCache(
                max_size=cfg.LLM_CACHE_MAX_SIZE,
                ttl_seconds=cfg.LLM_CACHE_TTL
            )
        elif storage == StorageType.REDIS:
            return RedisLLMCache(config=cfg, default_ttl=cfg.LLM_CACHE_TTL)
        else:
            raise ValueError(f"不支持的存储后端: {storage}，请配置为 '{ke.KEY_LOCAL}' 或 '{ke.KEY_REDIS}'")

    @staticmethod
    def _merge_runtime_params(base_kwargs: dict, runtime_params: Optional[dict] = None) -> dict:
        """合并基础参数和运行时参数，运行时参数优先级更高"""
        merged = base_kwargs.copy()
        if runtime_params:
            merged.update(runtime_params)
        return merged

    def _apply_runtime_param_mapping(self, params: dict) -> dict:
        """对运行时参数进行厂商映射"""
        return map_params_to_vendor(params, self._params_map)

    async def _resolve_cache(
            self,
            cache_key: str,
            on_miss: Callable[[], Awaitable[LLMResponse]]
    ) -> LLMResponse:
        """
        缓存解析器：命中则返回缓存，未命中则执行 on_miss 并写缓存。
        on_miss 是一个异步函数，返回 LLMResponse。
        """
        # 1. 尝试读缓存
        if cache_key:
            cache_response = await self.llm_cache.get(cache_key)
            success = cache_response.get(ke.KEY_SUCCESS)
            data = cache_response.get(ke.KEY_DATA)
            if success and data is not None:
                if isinstance(data, dict):
                    try:
                        llm_response = LLMResponse(**data)
                        content = getattr(llm_response, ke.KEY_CONTENT, '')
                        logger.info(f"缓存命中 | key={cache_key} | 内容长度={len(content)}", module_name=self.CHINESE_NAME)
                        return llm_response
                    except Exception as e:
                        logger.warning(
                            f"缓存反序列化失败，重新调用LLM | key={cache_key} | {e}",
                            module_name=self.CHINESE_NAME
                        )
                else:
                    logger.warning(f"缓存数据非dict，跳过 | key={cache_key}", module_name=self.CHINESE_NAME)

        # 2. 未命中，执行实际调用
        response = await on_miss()

        # 3. 写缓存
        if cache_key and response.ok:
            set_result = await self.llm_cache.set(cache_key, response.to_dict())
            if not set_result.get(ke.KEY_SUCCESS):
                logger.error(
                    f"缓存写入失败 | key={cache_key} | {set_result.get(ke.KEY_ERROR)}",
                    module_name=self.CHINESE_NAME
                )

        return response

    # --------------------------------------------------------------------------
    # 公共执行骨架
    # --------------------------------------------------------------------------
    async def _execute(
            self,
            prompt: str,
            type_str: str,
            prompt_id: str,
            is_json: bool = False,
            params: Optional[dict] = None,
            cache_key: str = None,
            on_retry: Optional[Callable[[int, float], Awaitable[None]]] = None,
            **kwargs
    ) -> LLMResponse:
        """
        公共执行链路：参数合并 → 厂商映射 → 缓存 → 调用 → 响应校验。
        text/json 各自在此基础上做后处理。
        """
        invoke_kwargs = self._merge_runtime_params(kwargs, params)
        mapped = self._apply_runtime_param_mapping(invoke_kwargs)

        # ---------- 自动注入推理模式（仅支持推理的模型，且配置开启）----------
        if self.reasoning_auto_inject and LLMModel.is_reasoning_model(self.model):
            effort = self.reasoning_effort_map.get(type_str)  # 根据当前能力 ID 获取强度
            if effort:  # 只有配置中存在的能力才注入
                if self.vendor == LLMVendor.DEEPSEEK:
                    # DeepSeek: reasoning_effort + thinking.type=enabled
                    mapped[ke.KEY_REASONING_EFFORT] = effort
                    mapped[ke.KEY_EXTRA_BODY] = {ke.KEY_THINKING: {ke.KEY_TYPE: ke.KEY_ENABLED}}
                elif self.vendor == LLMVendor.TONGYI:
                    # 通义 qwen3: enable_thinking（DashScope OpenAI 兼容端点）
                    mapped[ke.KEY_EXTRA_BODY] = {ke.KEY_ENABLE_THINKING: True}
                logger.debug(f"注入推理模式: vendor={self.vendor}, capability={type_str}, effort={effort}", module_name=self.CHINESE_NAME)
            else:
                logger.debug(f"能力 {type_str} 未配置推理强度，跳过推理注入", module_name=self.CHINESE_NAME)

        # ---------- 自适应重试配置 ----------
        base_max_tokens = mapped.get(ke.KEY_MAX_TOKENS)
        # 当前扩容比率
        if self.model.startswith(ke.KEY_DEEPSEEK_V4):
            current_factor = config.MAX_TOKENS_EXPANSION_FACTOR
        else:
            current_factor = 1.0

        # 重试配置
        max_retries = config.MAX_LENGTH_RETRIES
        factor_increment = config.FACTOR_INCREMENT

        # ---------- 自动生成缓存键（如果调用方未提供）----------
        if cache_key is None:
            if prompt and isinstance(prompt, str):
                cache_data = {
                    ke.KEY_VENDOR: self.vendor,
                    ke.KEY_MODEL: self.model,
                    ke.KEY_JSON if is_json else ke.KEY_TEXT: 1,
                    ke.KEY_PROMPT: prompt,
                }
                for param_name in (ke.KEY_TEMPERATURE, ke.KEY_MAX_TOKENS, ke.KEY_TOP_P, ke.KEY_PRESENCE_PENALTY, ke.KEY_FREQUENCY_PENALTY, ke.KEY_STOP, ke.KEY_RESPONSE_FORMAT, ke.KEY_EXTRA_BODY, ke.KEY_REASONING_EFFORT):
                    if param_name in mapped:
                        cache_data[param_name] = mapped[param_name]
                cache_key = BaseCache.make_key(ke.KEY_LLM, **cache_data)
            else:
                logger.warning("自动生成缓存键失败：缺少 prompt", module_name=self.CHINESE_NAME)

        # 清理运行时注入的临时键（防止污染实际模型参数）
        mapped.pop(ke.KEY_CURRENT_TEXT, None)

        # ---------- 带自适应重试的调用闭包 ----------
        async def _call_llm():
            nonlocal current_factor
            res = None
            for attempt in range(max_retries + 1):
                if base_max_tokens and base_max_tokens > 0:
                    cur_max_tokens = int(base_max_tokens * current_factor)
                else:
                    cur_max_tokens = None

                # 准备调用参数
                call_kwargs = mapped.copy()
                if cur_max_tokens is not None:
                    call_kwargs[ke.KEY_MAX_TOKENS] = cur_max_tokens
                call_kwargs[ke.KEY_TYPE_STR] = type_str
                call_kwargs[ke.KEY_PROMPT_ID] = prompt_id
                if is_json:
                    call_kwargs[ke.KEY__IS_JSON] = True

                res = await self._invoke(prompt, **call_kwargs)
                if res.ok:
                    return res

                # 判断是否为长度截断错误
                err_msg = getattr(res, ke.KEY_MSG, '') or ''
                if 'length limit' not in err_msg.lower():
                    return res  # 其他错误直接返回

                if attempt < max_retries:
                    current_factor += factor_increment
                    if on_retry:
                        await on_retry(attempt + 1, current_factor)
                    logger.warning(f"输出长度截断，自动增加扩容比率至 {current_factor} (重试 {attempt + 1}/{max_retries})", module_name=self.CHINESE_NAME)
                    continue
                else:
                    logger.error(f"长度截断重试失败，已达最大重试次数 {max_retries}。建议增大扩容比率或检查输入。", module_name=self.CHINESE_NAME)
                    return res

            return res

        response = await self._resolve_cache(cache_key, _call_llm)

        # 响应类型校验
        if isinstance(response, dict) and response.get(ke.KEY_OK) is False:
            return LLMResponse(**response)
        if not isinstance(response, LLMResponse):
            logger.error(
                f"_invoke 返回了非 LLMResponse 类型: {type(response)} | "
                f"id={prompt_id} | {ke.KEY_TYPE}= {type_str} | 模型={self.vendor}/{self.model}",
                module_name=self.CHINESE_NAME
            )
            return LLMResponse.sys_fail(
                msg=f"内部错误：期望 LLMResponse 对象，得到 {type(response)}",
                vendor=self.vendor,
                model=self.model
            )

        return response

    # --------------------------------------------------------------------------
    # 业务接口
    # --------------------------------------------------------------------------
    @with_langsmith_trace(name=ke.KEY_LLM_TEXT_CALL, run_type=ke.KEY_LLM)
    async def text(self, prompt: str, type_str: str, prompt_id: str, params: Optional[dict] = None,
                   cache_key: str = None,
                   on_retry=None,
                   **kwargs) -> LLMResponse:
        try:
            response = await self._execute(
                prompt, type_str, prompt_id,
                is_json=False, params=params, cache_key=cache_key, on_retry=on_retry, **kwargs
            )

            if not response.ok:
                return response

            content = response.content or ""
            cleaned_content = remove_check(content.strip())

            return LLMResponse.ok_content(
                content=cleaned_content,
                raw=response.raw,
                vendor=self.vendor,
                model=self.model,
                elapsed_ms=response.elapsed_ms,
                cost=response.cost
            )
        except Exception as e:
            logger.warning(f"执行链路异常 | 模型={self.vendor}/{self.model} | 错误={str(e)}", module_name=self.CHINESE_NAME)
            return LLMResponse.sys_fail(str(e), self.vendor, self.model)

    @with_langsmith_trace(name=ke.KEY_LLM_JSON_CALL, run_type=ke.KEY_LLM)
    async def json(self, prompt: str, type_str: str, prompt_id: str, params: Optional[dict] = None,
                   cache_key: str = None,
                   on_retry=None,
                   validator_func: Optional[Callable[[Dict, str], Dict]] = None, **kwargs) -> LLMResponse:
        try:
            response = await self._execute(
                prompt, type_str, prompt_id,
                is_json=True, params=params, cache_key=cache_key, on_retry=on_retry, **kwargs
            )

            if not response.ok:
                return response

            content = response.content
            if isinstance(content, dict):
                parsed = content
            elif isinstance(content, str):
                parsed = extract_json_safely(content.strip())
            else:
                parsed = extract_json_safely(str(content).strip())

            if ke.KEY__ERROR in parsed:
                return LLMResponse.invalid(
                    [parsed[ke.KEY__ERROR]], content,
                    self.vendor, self.model, "内容格式校验失败"
                )

            # 二次校验
            cleaned_data = parsed
            if validator_func:
                validation_result = validator_func(parsed, prompt_id)
                if isinstance(validation_result, dict):
                    is_valid = validation_result.get(ke.KEY_IS_VALID, False)
                    errors = validation_result.get(ke.KEY_ERRORS, [])
                    cleaned_data = validation_result.get(ke.KEY_CLEANED_DATA, parsed)
                else:
                    logger.warning(f"验证器函数返回了意外的类型 {type(validation_result)}: {validation_result}", module_name=self.CHINESE_NAME)
                    is_valid = False
                    errors = ["验证函数返回格式不正确"]

                if not is_valid:
                    return LLMResponse.invalid(errors, cleaned_data, self.vendor, self.model, "内容格式校验失败")

            return LLMResponse.ok_content(
                content=cleaned_data,
                raw=response.raw,
                vendor=self.vendor,
                model=self.model,
                elapsed_ms=response.elapsed_ms,
                cost=response.cost
            )
        except Exception as e:
            logger.warning(f"执行链路异常 | 模型={self.vendor}/{self.model} | 错误={str(e)}", module_name=self.CHINESE_NAME)
            return LLMResponse.sys_fail(str(e), self.vendor, self.model)
