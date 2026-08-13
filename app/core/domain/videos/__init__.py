"""视频物理文件清理 —— 与 audios/images physical_file_cleaner 保持对称。

从 routers/videos.py 提取单条删除时的文件清理逻辑，统一作为 SSOT。
"""

import os
from typing import Any, Dict

from app.config.config import config


def physically_delete_video_files(video: Dict[str, Any]) -> None:
    """按 SSOT（file_path）删除视频物理文件，静默吞掉 OSError。"""
    if not video:
        return
    file_path = video.get("file_path") or ""
    if not isinstance(file_path, str) or not file_path:
        return
    abs_path = os.path.join(str(config.DATA_ROOT), file_path)
    if os.path.exists(abs_path) and os.path.isfile(abs_path):
        try:
            os.remove(abs_path)
        except OSError:
            pass
