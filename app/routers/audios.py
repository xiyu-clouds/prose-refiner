import json
import os
from typing import Any, Dict, Optional
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from app.common import keys as ke
from app.common.llm_constants import LLMVendor, LLMModelType, LLMTypeVendorModelMapping
from app.config.config import config
from app.common.tts_voices import get_tongyi_voices
from app.core.services.sse_manager import get_sse_manager
from app.routers._common import _get_engine
from app.utils.audio_util import AudioUtils
from app.utils.logger import LoggerManager as logger
from app.core.domain.audios.physical_file_cleaner import physically_delete_audio_files as _physically_delete_audio_files
from app.core.domain.audios.tts_generator import TTSGenerationError, generate_tts
from app.core.domain.media.cascade_cleaner import attach_ownership

audio_utils = AudioUtils()

router = APIRouter(prefix="/api/audios", tags=["音频 (Audios)"])


@router.get("/", summary="查询全部音频资源列表")
async def list_audios(engine=Depends(_get_engine)) -> Any:
    return engine.audio_list()


@router.get("/stat/count", summary="统计音频数量")
async def count_audios(
        file_format: Optional[str] = Query(None, description="可选：按文件格式过滤（mp3/wav 等）"),
        audio_type: Optional[str] = Query(None, description="可选：按音频类型过滤（music/tts/speaker）"),
        engine=Depends(_get_engine),
) -> Any:
    return {ke.KEY_COUNT: engine.audio_count(file_format, audio_type)}


@router.get("/speakers", summary="获取可用音色列表")
async def list_speakers(
        model: Optional[str] = Query(None, description="可选：指定音频模型名，未传则使用全局默认模型"),
) -> Any:
    """按音频模型返回对应音色列表（不同模型支持不同音色，前端切换模型后应重新获取）。"""
    target_model = model if model else config.AUDIO_DEFAULT_MODEL
    speakers = get_tongyi_voices(target_model)
    return {"speakers": speakers, "model": target_model}


@router.get("/capabilities", summary="音频模型能力元数据（供前端按模型动态渲染模型选择器）")
async def get_audio_model_capabilities() -> Any:
    """返回所有可用音频 TTS 模型列表、默认厂商与默认模型。"""
    vendor = config.AUDIO_DEFAULT_VENDOR
    default_model = config.AUDIO_DEFAULT_MODEL
    valid_models = LLMTypeVendorModelMapping.get_models_by_type_vendor(LLMModelType.AUDIO_TTS, vendor)
    return {
        "ok": True,
        "vendor": vendor,
        "default_model": default_model,
        "models": valid_models,
    }


@router.get("/tts/by-chapter", summary="按章节查询 TTS 音频")
async def get_tts_by_chapter(
        session_id: str = Query(..., description="会话ID"),
        volume_index: int = Query(..., description="卷索引"),
        chapter_index: int = Query(..., description="章索引"),
        engine=Depends(_get_engine),
) -> Any:
    """按章节查询已生成的 TTS 音频（一篇正文一条音频）。"""
    title = f"{session_id} 第{volume_index + 1}卷第{chapter_index + 1}章"
    all_audios = engine.audio_list()
    for audio in all_audios:
        if audio.get("audio_type") == "tts" and audio.get("title") == title:
            return {
                "ok": True,
                "audio_url": f"/media/audio/{audio['file_name']}",
                "file_name": audio["file_name"],
                "speaker_id": audio.get("speaker_id", ""),
                "duration": audio.get("duration", 0),
            }
    return {"ok": False}


@router.get("/{id}", summary="查询单个音频资源")
async def get_audio(id: str, engine=Depends(_get_engine)) -> Any:
    return engine.audio_get(id)


@router.post("/", summary="创建音频资源")
async def create_audio(payload: Dict[str, Any] = Body(...), engine=Depends(_get_engine)) -> Any:
    attach_ownership(payload)
    engine.audio_create(json.dumps(payload, ensure_ascii=False))
    return {"ok": True}


@router.put("/{id}", summary="更新音频资源")
async def update_audio(
        id: str,
        patch: Dict[str, Any] = Body(...),
        engine=Depends(_get_engine),
) -> Any:
    engine.audio_update(id, json.dumps(patch, ensure_ascii=False))
    return {"ok": True}


@router.delete("/{id}", summary="删除音频资源及物理文件")
async def delete_audio(id: str, engine=Depends(_get_engine)) -> Any:
    audio = engine.audio_get(id)
    _physically_delete_audio_files(audio)
    engine.audio_delete(id)
    return {"ok": True}


@router.post("/refresh-info", summary="刷新音频时长和歌词关联信息")
async def refresh_audio_info(engine=Depends(_get_engine)) -> Any:
    audio_list_result = engine.audio_list()
    audio_list = json.loads(audio_list_result) if isinstance(audio_list_result, str) else audio_list_result

    updated_count = 0
    for audio in audio_list:
        audio_id = audio.get("id")
        file_path = audio.get("file_path", "")

        if not audio_id or not file_path:
            continue

        full_path = os.path.join(str(config.DATA_ROOT), file_path)

        if os.path.exists(full_path):
            duration = audio_utils.get_audio_duration(full_path)
            if duration is not None and audio.get("duration") != duration:
                audio["duration"] = duration
                updated_count += 1

        audio_base_name = os.path.splitext(audio.get("file_name", ""))[0]
        lyric_filename = audio_base_name + ".lrc"
        lyric_full_path = os.path.join(str(config.LYRIC_DIR), lyric_filename)

        if os.path.exists(lyric_full_path):
            expected_lyric_path = f"lyric/{lyric_filename}"
            if audio.get("lyric_path") != expected_lyric_path:
                audio["lyric_path"] = expected_lyric_path
                updated_count += 1

        engine.audio_update(str(audio_id), json.dumps(audio, ensure_ascii=False))

    return {"ok": True, "updated_count": updated_count, "total_count": len(audio_list)}


@router.post("/upload", summary="上传音频文件")
async def upload_audio(
        files: list[UploadFile] = File(...),
        title: Optional[str] = Query(None, description="曲目标题"),
        artist: Optional[str] = Query(None, description="艺术家"),
        album: Optional[str] = Query(None, description="专辑"),
        engine=Depends(_get_engine),
) -> Any:
    sse = get_sse_manager()

    music_exts = {".mp3"}

    audio_files = []

    for f in files:
        filename = f.filename or ""
        ext = os.path.splitext(filename)[1].lower()
        if ext in music_exts:
            audio_files.append(f)
        else:
            await sse.broadcast("upload_progress", {
                ke.KEY_TITLE: "音频上传",
                ke.KEY_CONTENT: f"不支持的格式: {filename}（仅支持 mp3）",
                ke.KEY_META: {"progress": 100, "success": False, "file_name": filename}
            })
            raise HTTPException(status_code=400, detail=f"不支持的文件格式: {filename}（仅支持 mp3 音乐文件）")

    total_files = len(audio_files)
    results = []

    for idx, audio_file in enumerate(audio_files):
        filename = audio_file.filename or ""
        ext = os.path.splitext(filename)[1].lower()

        await sse.broadcast("upload_progress", {
            ke.KEY_TITLE: "音频上传",
            ke.KEY_CONTENT: f"开始上传: {filename} ({idx + 1}/{total_files})",
            ke.KEY_META: {"progress": 0, "file_name": filename, "current": idx + 1, "total": total_files}
        })

        content = await audio_file.read()

        storage_dir = config.AUDIO_DIR
        file_path_prefix = "audio"
        audio_type = "music"

        await sse.broadcast("upload_progress", {
            ke.KEY_TITLE: "音频上传",
            ke.KEY_CONTENT: f"保存文件: {filename}",
            ke.KEY_META: {"progress": 40, "file_name": filename, "current": idx + 1, "total": total_files}
        })

        audio_path = os.path.join(str(storage_dir), filename)
        with open(audio_path, "wb") as f:
            f.write(content)

        await sse.broadcast("upload_progress", {
            ke.KEY_TITLE: "音频上传",
            ke.KEY_CONTENT: f"分析时长: {filename}",
            ke.KEY_META: {"progress": 60, "file_name": filename, "current": idx + 1, "total": total_files}
        })

        duration = audio_utils.get_audio_duration(audio_path)

        lyric_path = ""
        audio_base_name = os.path.splitext(filename)[0]
        lyric_filename = audio_base_name + ".lrc"
        lyric_full_path = os.path.join(str(config.LYRIC_DIR), lyric_filename)
        if os.path.exists(lyric_full_path):
            lyric_path = f"lyric/{lyric_filename}"

        await sse.broadcast("upload_progress", {
            ke.KEY_TITLE: "音频上传",
            ke.KEY_CONTENT: f"写入数据库: {filename}",
            ke.KEY_META: {"progress": 80, "file_name": filename, "current": idx + 1, "total": total_files}
        })

        payload = {
            "file_name": filename,
            "file_path": f"{file_path_prefix}/{filename}",
            "file_size": len(content),
            "file_format": ext[1:],
            "audio_type": audio_type,
            "title": title or filename,
            "artist": artist,
            "album": album,
            "lyric_path": lyric_path,
            "duration": duration,
        }
        attach_ownership(payload)
        engine.audio_create(json.dumps(payload, ensure_ascii=False))

        await sse.broadcast("upload_progress", {
            ke.KEY_TITLE: "音频上传",
            ke.KEY_CONTENT: f"上传成功: {filename} ({duration}s)",
            ke.KEY_META: {"progress": 100, "success": True, "file_name": filename, "current": idx + 1,
                          "total": total_files, "duration": duration}
        })

        results.append({
            "ok": True,
            "file_name": filename,
            "file_path": f"/media/{file_path_prefix}/{filename}",
            "lyric_path": f"/media/{lyric_path}" if lyric_path else "",
        })

    return {"ok": True, "results": results}


@router.delete("/{id}/file", summary="删除音频资源及物理文件")
async def delete_audio_file(id: str, engine=Depends(_get_engine)) -> Any:
    audio = engine.audio_get(id)
    if not audio:
        raise HTTPException(status_code=404, detail="音频不存在")
    _physically_delete_audio_files(audio)
    engine.audio_delete(id)
    return {"ok": True}


@router.post("/tts-generate", summary="生成 TTS 音频")
async def tts_generate(
        payload: Dict[str, Any] = Body(...),
        engine=Depends(_get_engine),
) -> Any:
    """
    使用通义 TTS（CosyVoice/Sambert 系列）将文本转换为音频。

    请求体:
        - session_id: 会话ID
        - volume_index: 卷索引
        - chapter_index: 章索引
        - text: 要转换的文本内容
        - speaker_id: 可选，音色ID（从 /api/audios/speakers 获取）
        - model: 可选，音频模型名（空则使用全局默认模型）
    """
    session_id = payload.get("session_id", "")
    volume_index = payload.get("volume_index", 0)
    chapter_index = payload.get("chapter_index", 0)
    text = payload.get("text", "").strip()
    speaker_id = payload.get("speaker_id", "")

    if not text:
        raise HTTPException(status_code=400, detail="文本内容不能为空")

    if len(text) > 10000:
        raise HTTPException(status_code=400, detail="文本内容过长，最大支持10000字符")

    vendor = config.AUDIO_DEFAULT_VENDOR
    model = str(payload.get("model", "")).strip() or config.AUDIO_DEFAULT_MODEL
    if not LLMTypeVendorModelMapping.is_valid(LLMModelType.AUDIO_TTS, vendor, model):
        raise HTTPException(status_code=400, detail=f"不支持的音频模型: {vendor}/{model}")

    try:
        return await generate_tts(
            engine=engine,
            session_id=session_id,
            volume_index=volume_index,
            chapter_index=chapter_index,
            text=text,
            speaker_id=speaker_id,
            model=model,
        )
    except TTSGenerationError as e:
        raise HTTPException(status_code=500, detail=f"音频生成失败: {e}")
