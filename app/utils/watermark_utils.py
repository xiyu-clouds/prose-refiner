from typing import Dict, Any
from app.common import keys as ke
from app.config.config import config


def inject_watermark_into_result(result: Dict[str, Any]) -> Any:
    """
    将水印配置注入到 result 中，供前端模板渲染使用。
    """
    if not config.WATERMARK_ENABLED:
        return

    # 组装水印配置字典
    watermark_config = {
        ke.KEY_ENABLED: True,
        ke.KEY_TEXT: config.WATERMARK_TEXT,
        ke.KEY_COLOR: config.WATERMARK_COLOR,
        ke.KEY_OPACITY: config.WATERMARK_OPACITY,
        ke.KEY_FONTSIZE: config.WATERMARK_FONT_SIZE,
        ke.KEY_ANGLE: config.WATERMARK_ANGLE,
        ke.KEY_COLS: config.WATERMARK_SPACING_COLS,
        ke.KEY_ROWS: config.WATERMARK_SPACING_ROWS,
        ke.KEY_PADDING: config.WATERMARK_PADDING,
    }
    result[ke.KEY_WATERMARK] = watermark_config
