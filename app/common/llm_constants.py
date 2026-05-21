from __future__ import annotations
from typing import Set, Dict, List, Any
from app.common import keys as ke
from app.common import model as mo
from app.common import vendor as ve
from app.common.enums import build_literal_from_class
from app.config.config import config


# ==============================================================================
# 【1】模型类型常量（核心：区分文本/多模态/音频，解决你后续拓展）
# ==============================================================================
class LLMModelType:
    """模型类型：全局唯一分类，适配文本/图片/音频全场景"""
    TEXT = ke.KEY_TEXT  # 纯文本处理（你当前主力）
    MULTIMODAL = ke.KEY_MULTIMODAL  # 多模态（文本+图片/视频）
    AUDIO_TTS = ke.KEY_AUDIO_TTS  # 文本转语音
    AUDIO_SPEECH = ke.KEY_AUDIO_SPEECH  # 语音生成/理解
    EMBEDDING = ke.KEY_EMBEDDING  # 向量模型

    @classmethod
    def all(cls) -> Set[str]:
        return {v for k, v in cls.__dict__.items() if not k.startswith("_") and isinstance(v, str)}


# ==============================================================================
# 【2】LLM厂商后端（LangChain标准映射名，补全+最新）
# ==============================================================================
class LLMVendor:
    """
    LLM服务商标识（LangChain标准映射名）
    全局唯一来源，覆盖文本/多模态/音频全场景
    """
    DEEPSEEK = ve.VENDOR_DEEPSEEK  # 深度求索

    # 厂商配置元数据（用于 GlobalSingletonRegistry 动态加载）
    # 结构：Vendor标识 -> {包路径, 类名, 参数映射表}
    METADATA: Dict[str, Dict[str, Any]] = {
        DEEPSEEK: {
            ke.KEY_PACKAGE: ke.KEY_LANGCHAIN_DEEPSEEK,
            ke.KEY_CLASS: ke.KEY_CHAT_DEEPSEEK,
            # 核心：参数映射。key是标准参数名，value是厂商SDK需要的参数名
            # 比如：我们的标准是 'model'，但 ChatDeepSeek 需要 'model_name'
            ke.KEY_PARAMS_MAP: {
                ke.KEY_MODEL: ke.KEY_MODEL_NAME,
                ke.KEY_API_KEY: ke.KEY_API_KEY,
                ke.KEY_TEMPERATURE: ke.KEY_TEMPERATURE,
                ke.KEY_TOP_P: ke.KEY_TOP_P,
                ke.KEY_MAX_TOKENS: ke.KEY_MAX_TOKENS,
                ke.KEY_TIMEOUT: ke.KEY_TIMEOUT,
            },
            ke.KEY_API_KEY: lambda: config.LLM_DEEPSEEK_API_KEY,
            ke.KEY_RESPONSE_PATH: [
                {
                    ke.KEY_CONTENT: [ke.KEY_CONTENT],
                    ke.KEY_USAGE: [ke.KEY_RESPONSE_METADATA, ke.KEY_TOKEN_USAGE]
                },
            ]
        }
    }

    @classmethod
    def get_metadata(cls, vendor: str) -> Dict[str, Any]:
        """获取厂商配置元数据"""
        if vendor not in cls.METADATA:
            raise ValueError(f"未找到厂商配置: {vendor}")
        return cls.METADATA[vendor]

    @classmethod
    def get_api_key(cls, vendor: str) -> str:
        """统一获取 Key 的入口"""
        meta = cls.get_metadata(vendor)
        key = meta.get(ke.KEY_API_KEY)
        # 如果是可调用对象（lambda），就执行它；否则直接返回
        return key() if callable(key) else key

    @classmethod
    def all(cls) -> Set[str]:
        return {v for k, v in cls.__dict__.items() if not k.startswith("_") and isinstance(v, str)}


# ==============================================================================
# 【3】全量最新模型（2026年4月，覆盖文本/多模态/音频，含DeepSeek最强版）
# ==============================================================================
class LLMModel:
    """
    全量模型列表
    """
    # -------------------- DeepSeek--------------------
    # DEEPSEEK_CHAT = mo.MODEL_DEEPSEEK_CHAT  # 旧版通用
    DEEPSEEK_V4_FLASH = mo.MODEL_DEEPSEEK_V4_FLASH   # 轻量快速，段落级主力
    DEEPSEEK_V4_PRO = mo.MODEL_DEEPSEEK_V4_PRO       # 最强能力，全文级与元认知

    # 支持推理模式的模型前缀列表
    REASONING_MODEL_PREFIXES = (ke.KEY_DEEPSEEK_V4,)

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
    全局唯一真值来源，解决文本/多模态/音频的匹配与校验
    """
    MAPPING: Dict[str, Dict[str, List[str]]] = {
        # 纯文本（你当前主力）
        LLMModelType.TEXT: {
            LLMVendor.DEEPSEEK: [
                LLMModel.DEEPSEEK_V4_FLASH,
                LLMModel.DEEPSEEK_V4_PRO
            ],
        },
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
