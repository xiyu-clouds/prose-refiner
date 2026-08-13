import json
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.common import keys as ke
from app.config.config import config
from app.core.services.sse_manager import get_sse_manager
from app.routers._common import _get_engine
from app.utils.logger import LoggerManager as logger

router = APIRouter(prefix="/api/lyrics", tags=["歌词管理"])
CHINESE_NAME = "歌词管理"


@router.post("/upload", summary="上传歌词文件")
async def upload_lyric(
        files: list[UploadFile] = File(...),
) -> Any:
    sse = get_sse_manager()
    results = []
    lyric_dir = config.LYRIC_DIR.resolve()
    total_files = len(files)

    for idx, file in enumerate(files):
        filename = file.filename or ""
        ext = os.path.splitext(filename)[1].lower()

        await sse.broadcast("upload_progress", {
            ke.KEY_TITLE: "歌词上传",
            ke.KEY_CONTENT: f"开始上传: {filename} ({idx + 1}/{total_files})",
            ke.KEY_META: {"progress": 0, "file_name": filename, "current": idx + 1, "total": total_files}
        })

        if ext not in (".lrc", ".txt"):
            await sse.broadcast("upload_progress", {
                ke.KEY_TITLE: "歌词上传",
                ke.KEY_CONTENT: f"不支持的格式: {filename}",
                ke.KEY_META: {"progress": 100, "success": False, "file_name": filename, "current": idx + 1,
                              "total": total_files}
            })
            results.append({"ok": False, "file_name": filename, "message": "不支持的文件格式"})
            continue

        lyric_path = lyric_dir / filename
        if lyric_path.exists():
            await sse.broadcast("upload_progress", {
                ke.KEY_TITLE: "歌词上传",
                ke.KEY_CONTENT: f"文件已存在，跳过: {filename}",
                ke.KEY_META: {"progress": 100, "success": False, "file_name": filename, "current": idx + 1,
                              "total": total_files}
            })
            results.append({"ok": False, "file_name": filename, "message": "文件已存在，跳过"})
            continue

        await sse.broadcast("upload_progress", {
            ke.KEY_TITLE: "歌词上传",
            ke.KEY_CONTENT: f"保存文件: {filename}",
            ke.KEY_META: {"progress": 50, "file_name": filename, "current": idx + 1, "total": total_files}
        })

        content = await file.read()
        with open(lyric_path, "wb") as f:
            f.write(content)

        await sse.broadcast("upload_progress", {
            ke.KEY_TITLE: "歌词上传",
            ke.KEY_CONTENT: f"关联音频: {filename}",
            ke.KEY_META: {"progress": 70, "file_name": filename, "current": idx + 1, "total": total_files}
        })

        audio_base_name = os.path.splitext(filename)[0]
        matched_audio = None

        try:
            engine = await _get_engine()
            audio_list_result = engine.audio_list()
            audio_list = json.loads(audio_list_result) if isinstance(audio_list_result, str) else audio_list_result

            for audio in audio_list:
                audio_file_name = audio.get("file_name", "")
                audio_base = os.path.splitext(audio_file_name)[0]

                if audio_base.lower() == audio_base_name.lower():
                    audio["lyric_path"] = f"lyric/{filename}"
                    engine.audio_update(str(audio["id"]), json.dumps(audio, ensure_ascii=False))
                    matched_audio = audio_file_name
                    logger.info(f"歌词关联成功: {filename} -> {audio_file_name}", module_name=CHINESE_NAME)
                    break
        except Exception as e:
            logger.error(f"歌词关联失败: {filename} - {e}", module_name=CHINESE_NAME)

        if matched_audio:
            await sse.broadcast("upload_progress", {
                ke.KEY_TITLE: "歌词上传",
                ke.KEY_CONTENT: f"上传成功: {filename} -> {matched_audio}",
                ke.KEY_META: {"progress": 100, "success": True, "file_name": filename, "current": idx + 1,
                              "total": total_files, "matched_audio": matched_audio}
            })
            results.append({
                "ok": True,
                "file_name": filename,
                "matched_audio": matched_audio,
                "message": "歌词已上传并关联到同名音频"
            })
        else:
            await sse.broadcast("upload_progress", {
                ke.KEY_TITLE: "歌词上传",
                ke.KEY_CONTENT: f"上传成功: {filename} (暂未关联音频)",
                ke.KEY_META: {"progress": 100, "success": True, "file_name": filename, "current": idx + 1,
                              "total": total_files}
            })
            results.append({
                "ok": True,
                "file_name": filename,
                "message": "歌词已上传"
            })

    return {"ok": True, "results": results}


@router.get("/list", summary="获取歌词列表")
async def list_lyrics(engine=Depends(_get_engine)) -> Any:
    lyrics = []
    lyric_dir = config.LYRIC_DIR.resolve()
    if lyric_dir.exists():
        for f in lyric_dir.iterdir():
            if f.is_file() and f.name.lower().endswith(".lrc"):
                full_path = f
                lyrics.append({
                    "file_name": f.name,
                    "file_path": f"lyric/{f.name}",
                    "file_size": f.stat().st_size
                })
    return {"ok": True, "data": lyrics}


@router.delete("/{file_name}", summary="删除歌词文件")
async def delete_lyric(file_name: str, engine=Depends(_get_engine)) -> Any:
    if not file_name.lower().endswith(".lrc"):
        raise HTTPException(status_code=400, detail="歌词文件必须是 .lrc 格式")

    lyric_path = (config.LYRIC_DIR / file_name).resolve()
    if not lyric_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    lyric_path.unlink()

    try:
        audio_list = json.loads(engine.audio_list())
        audio_base_name = os.path.splitext(file_name)[0]
        for audio in audio_list:
            audio_file_name = audio.get("file_name", "")
            if audio_file_name.lower().startswith(audio_base_name.lower()):
                audio["lyric_path"] = ""
                engine.audio_update(str(audio["id"]), json.dumps(audio, ensure_ascii=False))
                logger.info(f"删除歌词后清除关联: {audio_file_name}", module_name=CHINESE_NAME)
                break
    except Exception as e:
        logger.error(f"删除歌词清除关联失败: {file_name} - {e}", module_name=CHINESE_NAME)

    return {"ok": True, "message": "歌词文件已删除"}