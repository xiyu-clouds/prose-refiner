import time
from typing import Any, Dict, Optional
from langchain_core.callbacks import AsyncCallbackHandler
from app.common import keys as ke
from app.common.llm_constants import LLMVendor
from app.utils.llm_utils import extract_by_path
from app.utils.logger import LoggerManager as logger


# 默认字段映射（兼容未配置的厂商或通用情况）
_DEFAULT_FIELD_MAP: Dict[str, Dict[str, Any]] = {
    'input_tokens': {
        'fields': ['input_tokens', 'prompt_tokens', 'prompt_token_count'],
        'nested_paths': [],
    },
    'output_tokens': {
        'fields': ['output_tokens', 'completion_tokens', 'generated_tokens', 'output_tokens_count'],
        'nested_paths': [],
    },
    'total_tokens': {
        'fields': ['total_tokens', 'total_token_count'],
        'nested_paths': [],
    },
    'reasoning_tokens': {
        'fields': ['reasoning_tokens', 'thinking_tokens'],
        'nested_paths': [
            ['output_token_details', 'reasoning'],
            ['output_token_details', 'reasoning_tokens'],
            ['completion_tokens_details', 'reasoning'],
            ['completion_tokens_details', 'reasoning_tokens'],
        ],
    },
    'cached_tokens': {
        'fields': ['cached_tokens', 'cache_read', 'prompt_cache_hit_tokens'],
        'nested_paths': [
            ['input_token_details', 'cache_read'],
            ['input_token_details', 'cached_tokens'],
            ['prompt_tokens_details', 'cache_read'],
            ['prompt_tokens_details', 'cached_tokens'],
        ],
    },
    'cache_miss_tokens': {
        'fields': ['cache_miss_tokens', 'prompt_cache_miss_tokens'],
        'nested_paths': [],
    },
}


class TokenUsageTracker(AsyncCallbackHandler):
    """
    Token 用量追踪器 —— 纯被动观察者

    职责：仅从 LangChain 回调中提取 API 返回的 token 用量。
    通过 vendor 参数支持不同厂商的 usage 结构差异。
    """

    CHINESE_NAME = "Token用量追踪器"

    def __init__(self, vendor: Optional[str] = None):
        self.vendor = vendor
        self._field_map = self._load_field_map(vendor)

        # ========== API 实际消耗的 Token ==========
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0

        # ========== 推理过程 Token ==========
        self.reasoning_tokens = 0

        # ========== 缓存相关 ==========
        self.cached_tokens = 0
        self.cache_hit_tokens = 0
        self.cache_miss_tokens = 0

        # ========== 时间追踪 ==========
        self.start_time = time.time()

    @staticmethod
    def _load_field_map(vendor: Optional[str]) -> Dict[str, Dict[str, Any]]:
        """加载厂商的字段映射配置，未配置则使用默认"""
        if vendor:
            try:
                vendor_map = LLMVendor.get_usage_field_map(vendor)
                if vendor_map:
                    # 合并：默认映射为基础，厂商配置可覆盖
                    merged = _DEFAULT_FIELD_MAP.copy()
                    for key, value in vendor_map.items():
                        if key in merged:
                            # 厂商配置的 fields/nested_paths 追加到默认列表
                            default_entry = merged[key]
                            merged[key] = {
                                'fields': list(dict.fromkeys(
                                    default_entry['fields'] + value.get('fields', [])
                                )),
                                'nested_paths': list(dict.fromkeys(
                                    default_entry['nested_paths'] + value.get('nested_paths', [])
                                )),
                            }
                        else:
                            merged[key] = value
                    return merged
            except Exception:
                pass
        return _DEFAULT_FIELD_MAP

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
                elif isinstance(obj, dict) and field in obj:
                    return int(obj[field]) if obj[field] is not None else 0
            except (AttributeError, TypeError, ValueError):
                continue
        return 0

    @staticmethod
    def _get_nested_value(obj: Any, path: list) -> int:
        """沿嵌套路径获取值，如 ['output_token_details', 'reasoning']"""
        try:
            current = obj
            for key in path:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                elif hasattr(current, key):
                    current = getattr(current, key)
                else:
                    return 0
            return int(current) if current is not None else 0
        except (TypeError, ValueError, AttributeError):
            return 0

    def _extract_field(self, usage: Any, field_key: str) -> int:
        """根据字段映射配置提取单个字段值"""
        entry = self._field_map.get(field_key, {})
        fields = entry.get('fields', [])
        nested_paths = entry.get('nested_paths', [])

        # 先尝试顶层字段
        val = self._safe_get_attr(usage, fields)
        if val > 0:
            return val

        # 再尝试嵌套路径
        for path in nested_paths:
            nested_val = self._get_nested_value(usage, path)
            if nested_val > 0:
                logger.debug(
                    f"[TokenTracker] 从路径 {'.'.join(path)} 提取到 {field_key}={nested_val}",
                    module_name=self.CHINESE_NAME
                )
                return nested_val

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
                        if hasattr(message, ke.KEY_USAGE_METADATA):
                            usage = message.usage_metadata
                            if usage:
                                self._extract_usage_from_metadata(usage)

            # 如果上面没提取到，尝试从 response 本身提取
            if self.input_tokens == 0 and hasattr(response, ke.KEY_LLM_OUTPUT):
                llm_output = response.llm_output
                if llm_output and isinstance(llm_output, dict):
                    token_usage = extract_by_path(llm_output, [ke.KEY_TOKEN_USAGE]) or extract_by_path(llm_output, [ke.KEY_USAGE])
                    if token_usage:
                        self._extract_usage_from_metadata(token_usage)

            # 如果还是没提取到，尝试从 response_metadata 提取
            if self.input_tokens == 0 and hasattr(response, ke.KEY_RESPONSE_METADATA):
                response_metadata = getattr(response, ke.KEY_RESPONSE_METADATA)
                if isinstance(response_metadata, dict):
                    token_usage = extract_by_path(response_metadata, [ke.KEY_TOKEN_USAGE])
                    if token_usage:
                        self._extract_usage_from_metadata(token_usage)

            # 最终汇总日志
            logger.info(
                f"[TokenTracker] Token统计 | 输入={self.input_tokens} | 输出={self.output_tokens} | "
                f"总计={self.total_tokens} | 推理={self.reasoning_tokens} | 缓存命中={self.cached_tokens}",
                module_name=self.CHINESE_NAME
            )

        except Exception as e:
            logger.warning(f"Token提取异常: {e}", module_name=self.CHINESE_NAME)

    def _extract_usage_from_metadata(self, usage: Any):
        """从用量元数据中提取各种token信息（使用配置驱动）"""
        # 提取基础token信息
        self.input_tokens = max(self.input_tokens, self._extract_field(usage, 'input_tokens'))
        self.output_tokens = max(self.output_tokens, self._extract_field(usage, 'output_tokens'))

        # 计算总数
        total_from_response = self._extract_field(usage, 'total_tokens')
        if total_from_response > 0:
            self.total_tokens = total_from_response
        else:
            self.total_tokens = self.input_tokens + self.output_tokens

        # 提取推理token
        self.reasoning_tokens = max(self.reasoning_tokens, self._extract_field(usage, 'reasoning_tokens'))

        # 提取缓存相关token
        self.cached_tokens = max(self.cached_tokens, self._extract_field(usage, 'cached_tokens'))
        self.cache_miss_tokens = max(self.cache_miss_tokens, self._extract_field(usage, 'cache_miss_tokens'))

        # 计算缓存命中
        if self.cached_tokens > 0:
            self.cache_hit_tokens = self.cached_tokens
        else:
            miss = self.cache_miss_tokens
            if 0 < miss <= self.input_tokens:
                self.cache_hit_tokens = self.input_tokens - miss

    def to_dict(self) -> Dict[str, any]:
        """返回纯净的 API 用量字典"""
        return {
            ke.KEY_PROMPT: self.input_tokens,
            ke.KEY_COMPLETION: self.output_tokens,
            ke.KEY_TOTAL: self.total_tokens,
            ke.KEY_REASONING_TOKENS: self.reasoning_tokens,
            ke.KEY_CACHED_TOKENS: self.cached_tokens,
            ke.KEY_CACHE_HIT_TOKENS: self.cache_hit_tokens,
            ke.KEY_CACHE_MISS_TOKENS: self.cache_miss_tokens,
        }