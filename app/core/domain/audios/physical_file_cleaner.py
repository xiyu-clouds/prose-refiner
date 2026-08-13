"""音频物理文件清理 —— 按 SSOT 删除音频本体 + 歌词文件。

从 routers/audios.py 提取，保持行为完全一致。
被 routers/audios.py 和 domain/audios/tts_generator.py 引用。
"""

import os
from typing import Any, Dict

from app.config.config import config


def physically_delete_audio_files(audio: Dict[str, Any]) -> None:
    """按 SSOT（file_path 优先、file_name 兜底）删除音频物理文件 + 歌词文件，静默吞掉 OSError。"""
    if not audio:
        return

    # 1. 音频本体：优先走 file_path（形如 audio/xxx.mp3，相对 DATA_ROOT），兜底用 AUDIO_DIR + file_name
    abs_audio_path = None
    file_path = audio.get("file_path") or ""
    if isinstance(file_path, str) and file_path:
        abs_audio_path = os.path.join(str(config.DATA_ROOT), file_path)
    if not abs_audio_path:
        file_name = audio.get("file_name") or ""
        if isinstance(file_name, str) and file_name:
            abs_audio_path = os.path.join(str(config.AUDIO_DIR), file_name)
    if abs_audio_path and os.path.exists(abs_audio_path):
        try:
            os.remove(abs_audio_path)
        except OSError:
            pass

    # 2. 歌词文件：lyric_path 形如 lyric/xxx.lrc，相对 DATA_ROOT
    lyric_path = audio.get("lyric_path") or ""
    if isinstance(lyric_path, str) and lyric_path:
        abs_lyric_path = os.path.join(str(config.DATA_ROOT), lyric_path)
        if os.path.exists(abs_lyric_path):
            try:
                os.remove(abs_lyric_path)
            except OSError:
                pass
