"""图片物理文件清理 —— 与 audios/physical_file_cleaner.py 保持对称。

从 routers/images.py 提取单条删除时的文件清理逻辑，统一作为 SSOT 被：
- routers/images.py 单条删除
- media/cascade_cleaner.py 批量级联删除
共同调用，避免逻辑分叉。
"""

import os
from typing import Any, Dict

from app.config.config import config


def physically_delete_image_files(image: Dict[str, Any]) -> None:
    """按 SSOT（file_path 优先）删除图片物理文件，静默吞掉 OSError。"""
    if not image:
        return
    file_path = image.get("file_path") or ""
    if not isinstance(file_path, str) or not file_path:
        return
    abs_path = os.path.join(str(config.DATA_ROOT), file_path)
    if os.path.exists(abs_path) and os.path.isfile(abs_path):
        try:
            os.remove(abs_path)
        except OSError:
            pass
