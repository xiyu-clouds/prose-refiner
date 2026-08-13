from __future__ import annotations
from typing import Set, Dict, List, Any, Callable
from app.common import keys as ke
from app.common import model as mo
from app.common import vendor as ve
from app.common import values as va
from app.common.enums import build_literal_from_class
from app.config.config import config


# ==============================================================================
# 【1】模型类型常量（核心：区分文本/多模态/音频/图像/视频）
# ==============================================================================
class LLMModelType:
    """模型类型：全局唯一分类，适配文本/图片/音频/视频全场景"""
    TEXT = ke.KEY_TEXT  # 纯文本处理
    MULTIMODAL = ke.KEY_MULTIMODAL  # 多模态（文本+图片/视频）
    AUDIO_TTS = ke.KEY_AUDIO_TTS  # 文本转语音
    AUDIO_SPEECH = ke.KEY_AUDIO_SPEECH  # 语音生成/理解
    IMAGE = ke.KEY_IMAGE  # 图像生成
    VIDEO = ke.KEY_VIDEO  # 视频生成
    EMBEDDING = ke.KEY_EMBEDDING  # 向量模型

    @classmethod
    def all(cls) -> Set[str]:
        return {v for k, v in cls.__dict__.items() if not k.startswith("_") and isinstance(v, str)}


# ==============================================================================
# 【2】LLM厂商（LangChain标准映射名 + 厂商级密钥 + 文本执行器元数据）
# ==============================================================================
class LLMVendor:
    """
    LLM服务商标识（LangChain标准映射名）
    全局唯一来源，覆盖文本/多模态/音频/图像/视频全场景

    架构要点：
    · API_KEYS 是厂商级密钥 SSOT（账号级，一个厂商一把 key，跨域通用）
    · METADATA 是文本 LangChain 执行器元数据（仅服务文本域）
    · 音频/图像走独立 Provider，不经 LangChain，不进 METADATA
    """
    DEEPSEEK = ve.VENDOR_DEEPSEEK  # 深度求索
    TONGYI = ve.VENDOR_TONGYI  # 通义（DashScope 账号级密钥通用）

    # 厂商级密钥（账号级，一个厂商一把 key，跨域通用）
    # 文本路径与音频/图像 Provider 都调 get_api_key(vendor) 取 key，统一入口
    API_KEYS: Dict[str, Callable[[], str]] = {
        DEEPSEEK: lambda: config.DEEPSEEK_API_KEY,
        TONGYI: lambda: config.TONGYI_API_KEY,
    }

    # 文本 LangChain 执行器元数据（仅服务文本域，音频/图像走独立 Provider 不进 METADATA）
    METADATA: Dict[str, Dict[str, Any]] = {
        DEEPSEEK: {
            ke.KEY_PACKAGE: ke.KEY_LANGCHAIN_DEEPSEEK,
            ke.KEY_CLASS: ke.KEY_CHAT_DEEPSEEK,
            # 参数映射：标准参数名 → 厂商SDK需要的参数名
            # ChatDeepSeek 需要 model_name 而非 model
            ke.KEY_PARAMS_MAP: {
                ke.KEY_MODEL: ke.KEY_MODEL_NAME,
                ke.KEY_API_KEY: ke.KEY_API_KEY,
                ke.KEY_TEMPERATURE: ke.KEY_TEMPERATURE,
                ke.KEY_TOP_P: ke.KEY_TOP_P,
                ke.KEY_MAX_TOKENS: ke.KEY_MAX_TOKENS,
                ke.KEY_TIMEOUT: ke.KEY_TIMEOUT,
            },
            ke.KEY_RESPONSE_PATH: [
                {
                    ke.KEY_CONTENT: [ke.KEY_CONTENT],
                    ke.KEY_USAGE: [ke.KEY_RESPONSE_METADATA, ke.KEY_TOKEN_USAGE]
                },
            ],
            # usage字段映射：定义如何从API响应中提取token用量
            # fields: 顶层字段名候选列表（按优先级排序）
            # nested_paths: 嵌套路径候选列表（用于output_token_details.reasoning等结构）
            ke.KEY_USAGE_FIELD_MAP: {
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
            },
        },
        TONGYI: {
            ke.KEY_PACKAGE: ke.KEY_LANGCHAIN_OPENAI,
            ke.KEY_CLASS: ke.KEY_CHAT_OPENAI,
            # ChatOpenAI 参数名与标准名一致，identity 映射
            ke.KEY_PARAMS_MAP: {
                ke.KEY_MODEL: ke.KEY_MODEL,
                ke.KEY_API_KEY: ke.KEY_API_KEY,
                ke.KEY_TEMPERATURE: ke.KEY_TEMPERATURE,
                ke.KEY_TOP_P: ke.KEY_TOP_P,
                ke.KEY_MAX_TOKENS: ke.KEY_MAX_TOKENS,
                ke.KEY_TIMEOUT: ke.KEY_TIMEOUT,
            },
            # DashScope OpenAI 兼容端点（create_langchain_model 透传给 ChatOpenAI）
            ke.KEY_BASE_URL: va.VAL_DASHSCOPE_BASE_URL,
            ke.KEY_RESPONSE_PATH: [
                {
                    ke.KEY_CONTENT: [ke.KEY_CONTENT],
                    ke.KEY_USAGE: [ke.KEY_RESPONSE_METADATA, ke.KEY_TOKEN_USAGE]
                },
            ],
            ke.KEY_USAGE_FIELD_MAP: {
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
                    'nested_paths': [],
                },
                'cache_miss_tokens': {
                    'fields': ['cache_miss_tokens', 'prompt_cache_miss_tokens'],
                    'nested_paths': [],
                },
            },
        },
    }

    @classmethod
    def get_metadata(cls, vendor: str) -> Dict[str, Any]:
        """获取厂商配置元数据"""
        if vendor not in cls.METADATA:
            raise ValueError(f"未找到厂商配置: {vendor}")
        return cls.METADATA[vendor]

    @classmethod
    def get_api_key(cls, vendor: str) -> str:
        """统一获取 Key 的入口（厂商级密钥，跨域通用）"""
        fn = cls.API_KEYS.get(vendor)
        if not fn:
            raise ValueError(f"未找到厂商密钥配置: {vendor}")
        return fn() if callable(fn) else fn

    @classmethod
    def get_usage_field_map(cls, vendor: str) -> Dict[str, Any]:
        """获取厂商的usage字段映射配置"""
        meta = cls.get_metadata(vendor)
        return meta.get(ke.KEY_USAGE_FIELD_MAP, {})

    @classmethod
    def all(cls) -> Set[str]:
        return {v for k, v in cls.__dict__.items() if not k.startswith("_") and isinstance(v, str)}


# ==============================================================================
# 【3】全量模型（覆盖文本/音频/图像，含DeepSeek与通义系列）
# ==============================================================================
class LLMModel:
    """全量模型列表"""

    # -------------------- DeepSeek（文本，LangChain 执行器）--------------------
    DEEPSEEK_V4_FLASH = mo.MODEL_DEEPSEEK_V4_FLASH   # 轻量快速，段落级主力
    DEEPSEEK_V4_PRO = mo.MODEL_DEEPSEEK_V4_PRO       # 最强能力，全文级与元认知

    # -------------------- 通义千问（文本，DashScope OpenAI 兼容端点）--------------------
    QWEN3_7_MAX = mo.MODEL_QWEN3_7_MAX
    QWEN3_7_PLUS = mo.MODEL_QWEN3_7_PLUS
    QWEN3_7_FLASH = mo.MODEL_QWEN3_7_FLASH
    QWEN3_8_MAX = mo.MODEL_QWEN3_8_MAX

    # -------------------- 通义 CosyVoice（语音合成系列，DashScope 原生 API）--------------------
    COSYVOICE_V1 = mo.MODEL_COSYVOICE_V1
    COSYVOICE_V2 = mo.MODEL_COSYVOICE_V2
    COSYVOICE_V3_PLUS = mo.MODEL_COSYVOICE_V3_PLUS
    COSYVOICE_V3_FLASH = mo.MODEL_COSYVOICE_V3_FLASH

    # -------------------- 通义 Sambert（早期语音合成系列，稳定可靠）--------------------
    SAMBERT = mo.MODEL_SAMBERT

    # -------------------- 通义万相（文生图系列，DashScope 异步任务 API）--------------------
    Z_IMAGE_TURBO = mo.MODEL_Z_IMAGE_TURBO
    WANX2_7_IMAGE = mo.MODEL_WANX2_7_IMAGE
    QWEN_IMAGE_PLUS = mo.MODEL_QWEN_IMAGE_PLUS

    # 支持推理模式的模型前缀列表（is_reasoning_model 仅作门控，真正注入还需 REASONING_AUTO_INJECT + EFFORT_MAP 命中）
    REASONING_MODEL_PREFIXES = (ke.KEY_DEEPSEEK_V4, ke.KEY_QWEN)

    @classmethod
    def is_reasoning_model(cls, model_name: str) -> bool:
        """判断模型是否支持推理模式"""
        if not model_name:
            return False
        return any(model_name.startswith(prefix) for prefix in cls.REASONING_MODEL_PREFIXES)

    @classmethod
    def all(cls) -> Set[str]:
        return {v for k, v in cls.__dict__.items() if not k.startswith("_") and isinstance(v, str)}


# ==============================================================================
# 【4】三级映射：类型 → 厂商 → 模型（全局唯一校验，适配全场景）
# ==============================================================================
class LLMTypeVendorModelMapping:
    """
    三级映射：模型类型 → 厂商 → 支持的模型列表
    全局唯一真值来源，解决文本/多模态/音频/图像的匹配与校验
    """
    MAPPING: Dict[str, Dict[str, List[str]]] = {
        # 纯文本（DeepSeek + 通义千问）
        LLMModelType.TEXT: {
            LLMVendor.DEEPSEEK: [
                LLMModel.DEEPSEEK_V4_FLASH,
                LLMModel.DEEPSEEK_V4_PRO,
            ],
            LLMVendor.TONGYI: [
                LLMModel.QWEN3_7_MAX,
                LLMModel.QWEN3_7_PLUS,
                LLMModel.QWEN3_7_FLASH,
                LLMModel.QWEN3_8_MAX,
            ],
        },
        # 语音合成（通义 CosyVoice + Sambert）
        LLMModelType.AUDIO_TTS: {
            LLMVendor.TONGYI: [
                LLMModel.COSYVOICE_V1,
                LLMModel.COSYVOICE_V2,
                LLMModel.COSYVOICE_V3_PLUS,
                LLMModel.COSYVOICE_V3_FLASH,
                LLMModel.SAMBERT,
            ],
        },
        # 图像生成（通义万相）
        LLMModelType.IMAGE: {
            LLMVendor.TONGYI: [
                LLMModel.Z_IMAGE_TURBO,
                LLMModel.WANX2_7_IMAGE,
                LLMModel.QWEN_IMAGE_PLUS,
            ],
        },
        # 视频生成（占位，暂无模型）
        LLMModelType.VIDEO: {},
    }

    @classmethod
    def get_vendors_by_type(cls, model_type: str) -> List[str]:
        """按模型类型获取支持的厂商"""
        return list(cls.MAPPING.get(model_type, {}).keys())

    @classmethod
    def get_models_by_type_vendor(cls, model_type: str, vendor: str) -> List[str]:
        """按类型+厂商获取支持的模型"""
        return cls.MAPPING.get(model_type, {}).get(vendor, [])

    @classmethod
    def is_valid(cls, model_type: str, vendor: str, model: str) -> bool:
        """三级校验：类型+厂商+模型是否合法（全局唯一校验入口）"""
        return model in cls.get_models_by_type_vendor(model_type, vendor)


# -------------------- 生成全局可直接使用的Literal类型（三级校验）--------------------
LLMModelTypeLiteral = build_literal_from_class(LLMModelType)
LLMVendorLiteral = build_literal_from_class(LLMVendor)
LLMModelLiteral = build_literal_from_class(LLMModel)
