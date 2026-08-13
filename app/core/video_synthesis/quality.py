"""质量档位预设（QUALITY_PRESETS）与 resolve_quality 解析函数。

统一使用 CPU libx264 编码，不再依赖 GPU 资源。
铅笔画效果通过 OpenCV 预处理完成，视频编码仅需 CPU。
"""
from typing import Any, Dict, Tuple

# 质量档位预设
QUALITY_PRESETS: Dict[str, Dict[str, Any]] = {
    "low":    {"crf": 28, "preset": "ultrafast", "audio_bitrate": "128k"},
    "medium": {"crf": 23, "preset": "fast",      "audio_bitrate": "192k"},
    "high":   {"crf": 20, "preset": "medium",    "audio_bitrate": "256k"},
    "ultra":  {"crf": 18, "preset": "slow",      "audio_bitrate": "320k"},
}


def resolve_quality(config: Dict[str, Any]) -> Tuple[int, str, str, str]:
    """从 quality 档位解析编码参数。

    统一使用 libx264 CPU 编码，不再检测 GPU。

    Returns:
        (crf, preset, audio_bitrate, encoder)
        encoder 固定为 'libx264'
    """
    q = config.get("quality", "medium")
    preset_data = QUALITY_PRESETS.get(q, QUALITY_PRESETS["medium"])
    crf = config.get("crf")
    if crf is None:
        crf = preset_data["crf"]
    enc_preset = config.get("preset")
    if enc_preset is None:
        enc_preset = preset_data["preset"]
    audio_bitrate = preset_data["audio_bitrate"]

    return int(crf), str(enc_preset), str(audio_bitrate), "libx264"
