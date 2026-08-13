"""
图像生成模型能力元数据（跨前后端 SSOT）。

依据阿里云百炼官方文档（通义万相 / 千问文生图 / Z-Image）梳理：
- 三模型均支持同步调用 multimodal-generation/generation（messages 格式）。
- negative_prompt：除 wan2.7-image-pro / wan2.7-image 外均支持。
- prompt_extend：wan2.7-image-pro / wan2.7-image 不支持（改用 thinking_mode）。
- n（单次 API 生成张数）：wan2.7 支持 1-4（非组图）/ 1-12（组图）；z-image-turbo / qwen-image-plus 仅 1。
- size：z-image-turbo / wan2.7-image 自定义宽高；qwen-image-plus 仅固定预设。
- wan2.7 特有：thinking_mode / enable_sequential / color_palette（互斥见文档）。

字段语义：
- supports_batch_n：非组图时单次 API 是否支持 n>1。
- supports_thinking_mode：是否支持 thinking_mode（仅 wan2.7，组图时不可用）。
- supports_sequential：是否支持 enable_sequential 组图（仅 wan2.7）。
- supports_color_palette：是否支持 color_palette 配色（仅 wan2.7，组图时不可用）。
- max_count：UI 批量上限（enable_sequential=false 时；组图时前端用 sequential_max_count）。
- sequential_max_count：组图模式批量上限（仅 wan2.7）。
"""
from typing import Any, Dict, List

from app.common import model as mo


# 各模型能力描述（供后端参数适配与前端动态渲染共用）
IMAGE_MODEL_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    mo.MODEL_Z_IMAGE_TURBO: {
        "supports_negative_prompt": True,
        "supports_prompt_extend": True,
        "supports_batch_n": False,     # 单次 API 仅 n=1，批量靠循环调用
        "supports_thinking_mode": False,
        "supports_sequential": False,
        "supports_color_palette": False,
        "max_count": 4,
        "default_count": 1,
        "sequential_max_count": 0,
        "default_size": "720*1280",
        "sizes": [
            {"value": "1024*1024", "label": "1024×1024 (1:1)"},
            {"value": "720*1280", "label": "720×1280 (9:16 竖)"},
            {"value": "1280*720", "label": "1280×720 (16:9 横)"},
            {"value": "864*1152", "label": "864×1152 (3:4)"},
            {"value": "1152*864", "label": "1152×864 (4:3)"},
        ],
        "defaults": {
            "thinking_mode": None,
            "enable_sequential": None,
        },
    },
    mo.MODEL_WANX2_7_IMAGE: {
        "supports_negative_prompt": False,
        "supports_prompt_extend": False,   # wan2.7 用 thinking_mode，不走 prompt_extend
        "supports_batch_n": True,          # 单次 API 支持 n=1-4（非组图）
        "supports_thinking_mode": True,
        "supports_sequential": True,
        "supports_color_palette": True,
        "max_count": 4,                    # enable_sequential=false 时 1-4
        "default_count": 2,
        "sequential_max_count": 12,        # enable_sequential=true 时 1-12
        "default_size": "720*1280",
        "sizes": [
            {"value": "1024*1024", "label": "1024×1024 (1:1)"},
            {"value": "720*1280", "label": "720×1280 (9:16 竖)"},
            {"value": "1280*720", "label": "1280×720 (16:9 横)"},
            {"value": "1104*1472", "label": "1104×1472 (3:4)"},
            {"value": "1472*1104", "label": "1472×1104 (4:3)"},
        ],
        "defaults": {
            "thinking_mode": True,         # 默认真（官方默认）
            "enable_sequential": False,    # 默认假（官方默认）
        },
    },
    mo.MODEL_QWEN_IMAGE_PLUS: {
        "supports_negative_prompt": True,
        "supports_prompt_extend": True,
        "supports_batch_n": False,     # 单次 API 仅 n=1，批量靠循环调用
        "supports_thinking_mode": False,
        "supports_sequential": False,
        "supports_color_palette": False,
        "max_count": 4,
        "default_count": 1,
        "sequential_max_count": 0,
        "default_size": "928*1664",    # 9:16 竖（官方默认 1664*928 横，此处统一竖屏适配小说配图）
        "sizes": [                     # 固定预设 5 个
            {"value": "1328*1328", "label": "1328×1328 (1:1)"},
            {"value": "928*1664", "label": "928×1664 (9:16 竖)"},
            {"value": "1664*928", "label": "1664×928 (16:9 横)"},
            {"value": "1104*1472", "label": "1104×1472 (3:4)"},
            {"value": "1472*1104", "label": "1472×1104 (4:3)"},
        ],
        "defaults": {
            "thinking_mode": None,
            "enable_sequential": None,
        },
    },
}


def get_image_capabilities(model: str) -> Dict[str, Any]:
    """获取指定图像模型的能力描述，未知模型返回最小兜底。"""
    cap = IMAGE_MODEL_CAPABILITIES.get(model)
    if cap:
        return {"model": model, **cap}
    return {
        "model": model,
        "supports_negative_prompt": False,
        "supports_prompt_extend": False,
        "supports_batch_n": False,
        "supports_thinking_mode": False,
        "supports_sequential": False,
        "supports_color_palette": False,
        "max_count": 1,
        "default_count": 1,
        "sequential_max_count": 0,
        "default_size": "1024*1024",
        "sizes": [{"value": "1024*1024", "label": "1024×1024 (1:1)"}],
        "defaults": {"thinking_mode": None, "enable_sequential": None},
    }


def get_valid_sizes(model: str) -> List[str]:
    """获取指定模型支持的尺寸值列表（用于后端校验）。"""
    return [s["value"] for s in get_image_capabilities(model).get("sizes", [])]


def is_supports_negative_prompt(model: str) -> bool:
    return bool(get_image_capabilities(model).get("supports_negative_prompt", False))


def is_supports_batch_n(model: str) -> bool:
    """单次 API 是否支持 n>1（True 直接传 n，False 需循环调用）。"""
    return bool(get_image_capabilities(model).get("supports_batch_n", False))


def is_supports_thinking_mode(model: str) -> bool:
    return bool(get_image_capabilities(model).get("supports_thinking_mode", False))


def is_supports_sequential(model: str) -> bool:
    return bool(get_image_capabilities(model).get("supports_sequential", False))


def is_supports_color_palette(model: str) -> bool:
    return bool(get_image_capabilities(model).get("supports_color_palette", False))


def get_default_thinking_mode(model: str) -> bool:
    cap = IMAGE_MODEL_CAPABILITIES.get(model, {})
    defaults = cap.get("defaults", {})
    v = defaults.get("thinking_mode")
    return bool(v) if v is not None else True


def get_default_enable_sequential(model: str) -> bool:
    cap = IMAGE_MODEL_CAPABILITIES.get(model, {})
    defaults = cap.get("defaults", {})
    v = defaults.get("enable_sequential")
    return bool(v) if v is not None else False
