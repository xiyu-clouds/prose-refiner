"""TTS 生成编排 —— 旧音频清理、分段合成、重试、文件落盘、DB 持久化、SSE 推送。

从 routers/audios.py 的 tts_generate 提取，保持行为完全一致。
路由层负责参数校验（空文本/超长文本/无效模型），本模块假定入参已通过校验。
"""

import asyncio
import json
import os
import random
import time
from typing import Any, Dict, Optional

from app.common import keys as ke
from app.common.llm_constants import LLMVendor
from app.common.tts_voices import resolve_tongyi_voice
from app.config.config import config
from app.core.domain.audios.physical_file_cleaner import physically_delete_audio_files
from app.core.domain.audios.tongyi_tts import TTSResultError, synthesize_tongyi_tts
from app.core.domain.media.cascade_cleaner import attach_ownership
from app.core.services.sse_manager import get_sse_manager
from app.utils.audio_util import AudioUtils
from app.utils.logger import LoggerManager as logger
from app.utils.paragraph_splitter import ParagraphSplitter
from app.utils.retry_util import is_retryable_exception

_audio_utils = AudioUtils()

LOG_MODULE = "音频路由"


class TTSGenerationError(Exception):
    """TTS 生成失败异常，携带可读消息，供路由层转换为 HTTPException。"""

    pass


async def generate_tts(
    engine: Any,
    session_id: str,
    volume_index: int,
    chapter_index: int,
    text: str,
    speaker_id: str,
    model: str,
) -> Dict[str, Any]:
    """
    完整 TTS 生成流程：
    1. 解析音色 + 设置 DashScope 密钥
    2. 覆盖旧音频（同 session/vol/chap 的所有 TTS 版本）
    3. 段落拆分
    4. 逐段合成（指数退避重试）
    5. 落盘 + 解析时长 + DB 持久化
    6. SSE 推送全程进度

    失败时清理临时文件并通过 SSE 推送错误进度，然后抛 TTSGenerationError。
    """
    sse = get_sse_manager()
    vendor = config.AUDIO_DEFAULT_VENDOR
    voice = resolve_tongyi_voice(model, speaker_id)

    logger.info(
        f"开始通义 TTS 生成: session={session_id}, volume={volume_index}, "
        f"chapter={chapter_index}, text_length={len(text)}, model={model}, voice={voice}",
        module_name=LOG_MODULE
    )

    # 设置 DashScope API 密钥
    import dashscope
    dashscope.api_key = LLMVendor.get_api_key(vendor)

    # 2. 覆盖旧音频
    title = f"{session_id} 第{volume_index + 1}卷第{chapter_index + 1}章"
    _old_prefix = f"{session_id}_v{volume_index}_c{chapter_index}_"
    all_audios = engine.audio_list()
    _deleted_count = 0
    for audio in all_audios:
        if audio.get("audio_type") != "tts":
            continue
        _by_title = (audio.get("title") == title)
        _by_fname = isinstance(audio.get("file_name"), str) and audio["file_name"].startswith(_old_prefix)
        if not (_by_title or _by_fname):
            continue
        _fid = audio.get("id")
        _fname = audio.get("file_name") or ""
        physically_delete_audio_files(audio)
        if _fid is not None:
            try:
                engine.audio_delete(str(_fid))
            except Exception:
                pass
        _deleted_count += 1
        logger.info(f"已覆盖旧音频: id={_fid}, file={_fname}", module_name=LOG_MODULE)
    if _deleted_count:
        logger.info(f"共清理 {_deleted_count} 条旧 TTS 音频（session={session_id}, v={volume_index}, c={chapter_index}）", module_name=LOG_MODULE)

    # 3. 段落拆分
    splitter = ParagraphSplitter()
    segments = splitter.split(text)
    if not segments:
        raise TTSGenerationError("文本内容不能为空")

    total_segments = len(segments)

    def _sse_meta(progress, **extra):
        m = {"progress": int(progress), "volume_index": int(volume_index), "chapter_index": int(chapter_index)}
        m.update(extra)
        return m

    await sse.broadcast("task_progress", {
        "title": "音频生成",
        "content": f"开始合成（模型: {model}, 音色: {voice}, 共 {total_segments} 段）",
        "meta": _sse_meta(10)
    })

    # 4. 逐段合成
    MAX_RETRIES = 3
    BACKOFF_BASE = 3.0
    timestamp = int(time.time())
    output_filename = f"{session_id}_v{volume_index}_c{chapter_index}_{voice}_{timestamp}.mp3"
    output_path = os.path.join(str(config.AUDIO_DIR), output_filename)

    last_error: Optional[Exception] = None
    try:
        with open(output_path, "wb") as f:
            for idx, segment in enumerate(segments):
                progress = int(10 + (idx / max(total_segments, 1)) * 70)
                await sse.broadcast("task_progress", {
                    "title": "音频生成",
                    "content": f"正在合成第 {idx + 1}/{total_segments} 段...",
                    "meta": _sse_meta(progress)
                })

                segment_ok = False
                for attempt in range(MAX_RETRIES):
                    try:
                        audio_data = await asyncio.to_thread(
                            synthesize_tongyi_tts, model, voice, segment
                        )
                        if not audio_data:
                            raise TTSResultError("通义 TTS 返回空音频数据")
                        f.write(audio_data)
                        segment_ok = True
                        break
                    except Exception as e:
                        last_error = e
                        if attempt + 1 >= MAX_RETRIES or not (is_retryable_exception(e) or isinstance(e, TTSResultError)):
                            break
                        wait_time = BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 3)
                        await sse.broadcast("task_progress", {
                            "title": "音频生成",
                            "content": f"第 {idx + 1}/{total_segments} 段合成失败，{wait_time:.0f}秒后重试（第 {attempt + 2}/{MAX_RETRIES} 次）",
                            "meta": _sse_meta(progress, is_retrying=True)
                        })
                        logger.warning(
                            f"通义 TTS 第 {idx + 1} 段合成失败，{wait_time:.0f}s 后重试: {type(e).__name__}: {e}",
                            module_name=LOG_MODULE
                        )
                        await asyncio.sleep(wait_time)
                if not segment_ok:
                    if last_error is not None:
                        raise last_error
                    raise RuntimeError(f"第 {idx + 1}/{total_segments} 段合成失败（未知错误）")

        file_size = os.path.getsize(output_path)
        if file_size == 0:
            raise RuntimeError("通义 TTS 返回空音频")

        await sse.broadcast("task_progress", {
            "title": "音频生成",
            "content": "音频合成完成，正在解析时长...",
            "meta": _sse_meta(80)
        })

        duration = _audio_utils.get_audio_duration(output_path)
        if not duration:
            duration = 0.0

        # 5. DB 持久化
        payload_data = {
            "file_name": output_filename,
            "file_path": f"audio/{output_filename}",
            "audio_type": "tts",
            "title": title,
            "artist": None,
            "album": None,
            "file_size": file_size,
            "duration": duration,
            "file_format": "mp3",
            "lyric_path": "",
            "speaker_id": voice,
        }
        attach_ownership(payload_data, session_id=session_id)
        engine.audio_create(json.dumps(payload_data, ensure_ascii=False))

        # 6. 完成
        audio_url = f"/media/audio/{output_filename}"

        await sse.broadcast("task_progress", {
            "title": "音频生成",
            "content": "音频生成完成",
            "meta": _sse_meta(100, success=True, audio_url=audio_url)
        })

        logger.info(
            f"通义 TTS 生成完成: {output_path}, duration={duration}s, size={file_size}bytes",
            module_name=LOG_MODULE
        )

        return {
            "ok": True,
            ke.KEY_AUDIO_URL: audio_url,
            "file_name": output_filename,
            "duration": duration,
            "file_size": file_size,
            "speaker_id": voice,
        }

    except Exception as e:
        err_msg = str(e) if e else "未知错误"
        logger.error(f"TTS 生成失败: {e}", module_name=LOG_MODULE, exc_info=True)
        # 失败兜底：清理不完整的临时文件
        try:
            if 'output_path' in locals() and output_path and os.path.exists(output_path):
                sz = os.path.getsize(output_path)
                _duration_val = locals().get('duration', None)
                if sz < 10240 or not _duration_val:
                    try:
                        os.remove(output_path)
                        logger.info(f"已清理不完整的 TTS 临时文件: {output_path} (size={sz})", module_name=LOG_MODULE)
                    except OSError:
                        pass
        except Exception:
            pass
        # SSE 发送最终失败进度
        try:
            await sse.broadcast("task_progress", {
                "title": "音频生成",
                "content": f"失败: {err_msg}",
                "meta": {
                    "progress": 100, "success": False, "error": err_msg,
                    "volume_index": int(volume_index) if isinstance(volume_index, (int, float, str)) else 0,
                    "chapter_index": int(chapter_index) if isinstance(chapter_index, (int, float, str)) else 0,
                }
            })
        except Exception:
            pass
        raise TTSGenerationError(err_msg) from e
