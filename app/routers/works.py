import io
import json
from typing import Any, Dict
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.domain.works.work_exporter import export_work_to_zip
from app.core.domain.media.cascade_cleaner import cascade_cleanup_media_by_work
from app.routers._common import _get_engine
from app.utils.logger import LoggerManager as logger

router = APIRouter(prefix="/api/works", tags=["作品 (Works)"])

LOG_MODULE = "作品接口"


@router.get("/", summary="查询全部作品列表")
async def list_works(engine=Depends(_get_engine)) -> Any:
    try:
        logger.info("查询全部作品列表", module_name=LOG_MODULE)
        data = engine.work_list()
        count = len(data) if hasattr(data, "__len__") else -1
        logger.info(f"查询全部作品列表成功，共 {count} 条", module_name=LOG_MODULE)
        return data
    except Exception as e:
        logger.error(f"查询全部作品列表失败: {e}", module_name=LOG_MODULE, exc_info=True)
        raise HTTPException(status_code=500, detail="查询作品列表失败，请查看后端日志获取详细信息")


@router.get("/{session_id}", summary="查询单个作品")
async def get_work(session_id: str, engine=Depends(_get_engine)) -> Any:
    try:
        logger.info(f"查询单个作品 session_id={session_id}", module_name=LOG_MODULE)
        return engine.work_get(session_id)
    except Exception as e:
        logger.error(f"查询单个作品失败 session_id={session_id}: {e}", module_name=LOG_MODULE, exc_info=True)
        raise HTTPException(status_code=500, detail="查询作品失败，请查看后端日志获取详细信息")


@router.post("/", summary="创建作品")
async def create_work(payload: Dict[str, Any] = Body(...), engine=Depends(_get_engine)) -> Any:
    title = payload.get("title")
    has_session_id = payload.get("session_id") is not None
    summary = f"title={title!r}, session_id_provided={has_session_id}"
    try:
        logger.info(f"创建作品 {summary}", module_name=LOG_MODULE)
        created = engine.work_create(json.dumps(payload, ensure_ascii=False))
        new_sid = created.get("session_id") if isinstance(created, dict) else None
        logger.info(f"创建作品成功 session_id={new_sid} title={title!r}", module_name=LOG_MODULE)
        return created
    except Exception as e:
        logger.error(f"创建作品失败 {summary}: {e}", module_name=LOG_MODULE, exc_info=True)
        raise HTTPException(status_code=500, detail="创建作品失败，请查看后端日志获取详细信息")


@router.patch("/{session_id}", summary="更新作品")
async def update_work(
    session_id: str,
    patch: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    keys = sorted([k for k in patch.keys() if k != "extra_meta"])
    has_extra_meta = "extra_meta" in patch
    summary = f"keys={keys}, extra_meta_included={has_extra_meta}"
    try:
        logger.info(f"更新作品 session_id={session_id} {summary}", module_name=LOG_MODULE)
        engine.work_update(session_id, json.dumps(patch, ensure_ascii=False))
        logger.info(f"更新作品成功 session_id={session_id}", module_name=LOG_MODULE)
        return {"ok": True}
    except Exception as e:
        logger.error(f"更新作品失败 session_id={session_id} {summary}: {e}", module_name=LOG_MODULE, exc_info=True)
        raise HTTPException(status_code=500, detail="更新作品失败，请查看后端日志获取详细信息")


@router.delete("/{session_id}", summary="删除作品（级联清理全局剧情/卷/章/任务及关联多媒体文件）")
async def delete_work(session_id: str, engine=Depends(_get_engine)) -> Any:
    if not isinstance(session_id, str) or not session_id.strip():
        raise HTTPException(status_code=400, detail="session_id 为非空字符串必填")
    sid = session_id.strip()
    try:
        logger.info(f"删除作品 begin session_id={sid}", module_name=LOG_MODULE)

        # 1) 先清多媒体（必须在 work_delete 之前；FK 级联会把 media 记录删掉导致拿不到 file_path）
        try:
            media_cleaned = cascade_cleanup_media_by_work(engine, sid)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"删除作品 session_id={sid} 前置 media 清理失败，仍继续删作品记录: {e}",
                module_name=LOG_MODULE,
                exc_info=True,
            )
            media_cleaned = {"audio": -1, "image": -1, "video": -1}
        logger.info(
            f"删除作品 session_id={sid} 前置 media 清理完成: {media_cleaned}",
            module_name=LOG_MODULE,
        )

        # 2) 再删作品本体（DB FK 级联会自动删 task/session_memory/tag_config/works_labels 等）
        engine.work_delete(sid)
        logger.info(f"删除作品成功 session_id={sid}", module_name=LOG_MODULE)
        return {"ok": True, "media_cleaned": media_cleaned}
    except Exception as e:
        logger.error(f"删除作品失败 session_id={sid}: {e}", module_name=LOG_MODULE, exc_info=True)
        raise HTTPException(status_code=500, detail="删除作品失败，请查看后端日志获取详细信息")


@router.get("/{session_id}/export", summary="导出完整作品创作包（剧情/摘要/事件链/正文，zip 下载）")
async def export_work(session_id: str, engine=Depends(_get_engine)) -> Any:
    if not isinstance(session_id, str) or not session_id.strip():
        raise HTTPException(status_code=400, detail="session_id 为非空字符串必填")
    summary = f"session_id={session_id!r}"
    try:
        logger.info(f"导出作品创作包 {summary}", module_name=LOG_MODULE)
        zip_bytes, filename_no_ext = export_work_to_zip(engine, session_id.strip())
        safe_utf8 = quote(f"{filename_no_ext}.zip")
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{safe_utf8}",
            "Cache-Control": "no-store, no-cache",
        }
        logger.info(f"导出作品创作包成功 {summary}, size={len(zip_bytes)} bytes", module_name=LOG_MODULE)
        return StreamingResponse(
            io.BytesIO(zip_bytes),
            media_type="application/zip",
            headers=headers,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出作品创作包失败 {summary}: {e}", module_name=LOG_MODULE, exc_info=True)
        raise HTTPException(status_code=500, detail="导出作品失败，请查看后端日志获取详细信息")
