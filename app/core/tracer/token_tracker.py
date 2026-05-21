import time
from typing import Any, Dict
from langchain_core.callbacks import AsyncCallbackHandler
from app.common import keys as ke
from app.utils.llm_utils import extract_by_path
from app.utils.logger import LoggerManager as logger


class TokenUsageTracker(AsyncCallbackHandler):
    """Token用量追踪器，支持多种响应格式"""

    CHINESE_NAME = "Token用量追踪器"

    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.cached_tokens = 0
        self.cache_hit_tokens = 0
        self.cache_miss_tokens = 0
        self.start_time = time.time()

    @property
    def total_time(self):
        return time.time() - self.start_time

    @staticmethod
    def _safe_get_attr(obj: Any, fields: list) -> int:
        """安全获取对象属性，支持多种命名格式"""
        for field in fields:
            try:
                if hasattr(obj, field):
                    value = getattr(obj, field, 0)
                    return int(value) if value is not None else 0
                # 尝试字典访问 - 使用工具函数
                elif isinstance(obj, dict) and field in obj:
                    return int(obj[field]) if obj[field] is not None else 0
            except (AttributeError, TypeError, ValueError):
                continue
        return 0

    async def on_llm_start(self, serialized, prompts, **kwargs):
        """记录开始时间"""
        self.start_time = time.time()

    async def on_llm_end(self, response, **kwargs):
        """从响应中提取用量信息"""
        try:
            # 优先从 response.generations 提取
            generations = getattr(response, ke.KEY_GENERATIONS, [])
            for gen_list in generations:
                for generation in gen_list:
                    if hasattr(generation, ke.KEY_MESSAGE):
                        message = generation.message
                        # 检查 message 是否有 usage_metadata
                        if hasattr(message, ke.KEY_USAGE_METADATA):
                            usage = message.usage_metadata
                            if usage:
                                self._extract_usage_from_metadata(usage)

            # 如果上面没提取到，尝试从 response 本身提取
            if self.input_tokens == 0 and hasattr(response, ke.KEY_LLM_OUTPUT):
                llm_output = response.llm_output
                if llm_output and isinstance(llm_output, dict):
                    # 检查是否有 token_usage 信息 - 使用工具函数
                    token_usage = extract_by_path(llm_output, [ke.KEY_TOKEN_USAGE]) or extract_by_path(llm_output,
                                                                                                       [ke.KEY_USAGE])
                    if token_usage:
                        self._extract_usage_from_metadata(token_usage)

            # 如果还是没提取到，尝试从 response_metadata.token_usage 提取
            if self.input_tokens == 0 and hasattr(response, ke.KEY_RESPONSE_METADATA):
                response_metadata = getattr(response, ke.KEY_RESPONSE_METADATA)
                if isinstance(response_metadata, dict):
                    token_usage = extract_by_path(response_metadata, [ke.KEY_TOKEN_USAGE])
                    if token_usage:
                        self._extract_usage_from_metadata(token_usage)

        except Exception as e:
            logger.warning(f"Token提取异常: {e}", module_name=self.CHINESE_NAME)

    def _extract_usage_from_metadata(self, usage: Any):
        """从用量元数据中提取各种token信息"""
        # 输入token字段列表（按优先级排序）
        input_fields = [
            ke.KEY_INPUT_TOKENS, ke.KEY_INPUT_TOKENS,
            ke.KEY_PROMPT_TOKENS, ke.KEY_PROMPT_TOKENS,
            ke.KEY_PROMPT_TOKEN_COUNT, ke.KEY_PROMPT_TOKEN_COUNT
        ]
        output_fields = [
            ke.KEY_OUTPUT_TOKENS, ke.KEY_OUTPUT_TOKENS,
            ke.KEY_COMPLETION_TOKENS, ke.KEY_COMPLETION_TOKENS,
            ke.KEY_GENERATED_TOKENS, ke.KEY_OUTPUT_TOKENS_COUNT
        ]
        total_fields = [
            ke.KEY_TOTAL_TOKENS, ke.KEY_TOTAL_TOKENS,
            ke.KEY_TOTAL_TOKEN_COUNT
        ]

        # 详细缓存相关字段
        cached_fields = [
            ke.KEY_CACHED_TOKENS, ke.KEY_CACHE_READ, ke.KEY_PROMPT_CACHE_HIT_TOKENS
        ]
        cache_miss_fields = [
            ke.KEY_CACHE_MISS_TOKENS, ke.KEY_PROMPT_CACHE_MISS_TOKENS
        ]

        # 提取基础token信息
        self.input_tokens = max(self.input_tokens, self._safe_get_attr(usage, input_fields))
        self.output_tokens = max(self.output_tokens, self._safe_get_attr(usage, output_fields))

        # 计算总数
        total_from_response = self._safe_get_attr(usage, total_fields)
        if total_from_response > 0:
            self.total_tokens = total_from_response
        else:
            self.total_tokens = self.input_tokens + self.output_tokens

        # 提取缓存相关token信息
        self.cached_tokens = max(self.cached_tokens, self._safe_get_attr(usage, cached_fields))
        self.cache_miss_tokens = max(self.cache_miss_tokens, self._safe_get_attr(usage, cache_miss_fields))

        # 如果缓存命中token没有单独提供，则通过计算得出
        if self.cache_miss_tokens <= self.input_tokens:
            self.cache_hit_tokens = self.input_tokens - self.cache_miss_tokens
        else:
            # 如果缓存未命中超过输入token，说明数据有问题，重置
            self.cache_miss_tokens = min(self.cache_miss_tokens, self.input_tokens)
            self.cache_hit_tokens = self.input_tokens - self.cache_miss_tokens

    def to_usage_dict(self) -> Dict[str, Any]:
        """转换为用量字典格式"""
        return {
            ke.KEY_PROMPT: self.input_tokens,
            ke.KEY_COMPLETION: self.output_tokens,
            ke.KEY_TOTAL: self.total_tokens,
            ke.KEY_CACHED_TOKENS: self.cached_tokens,
            ke.KEY_CACHE_HIT_TOKENS: self.cache_hit_tokens,
            ke.KEY_CACHE_MISS_TOKENS: self.cache_miss_tokens,
            ke.KEY_CACHE_HIT_RATE_PERCENT: round(self.cache_hit_tokens / self.input_tokens * 100,
                                                 2) if self.input_tokens > 0 else 0
        }
