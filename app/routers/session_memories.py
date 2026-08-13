import json
from typing import Any, Dict
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from app.routers._common import _get_engine
from app.utils.logger import LoggerManager as logger

LOG_MODULE = "会话记忆接口"

router = APIRouter(prefix="/api/session-memories", tags=["会话记忆 (Session Memories)"])


def _preview_content(content: Any, limit: int = 60) -> str:
    text = content if isinstance(content, str) else (content or "")
    text = str(text or "")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...({len(text)}字符)"


@router.get("/", summary="查询会话记忆列表（按作品隔离）")
async def list_session_memories(
    session_id: str = Query(..., description="作品会话 ID"),
    engine=Depends(_get_engine),
) -> Any:
    summary = f"session_id={session_id!r}"
    try:
        logger.info(f"查询会话记忆列表 {summary}", module_name=LOG_MODULE)
        data = engine.session_memory_list(session_id)
        count = len(data) if isinstance(data, (list, tuple)) else -1
        logger.info(
            f"查询会话记忆列表成功 {summary}，共 {count} 条",
            module_name=LOG_MODULE,
        )
        return data
    except Exception as e:
        logger.error(
            f"查询会话记忆列表失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="查询会话记忆列表失败，请查看后端日志获取详细信息")


@router.get("/{id}", summary="查询单条会话记忆")
async def get_session_memory(id: str, engine=Depends(_get_engine)) -> Any:
    summary = f"id={id!r}"
    try:
        logger.info(f"查询单条会话记忆 {summary}", module_name=LOG_MODULE)
        data = engine.session_memory_get(id)
        if data and isinstance(data, dict):
            preview = _preview_content(data.get("content"))
            logger.info(
                f"查询单条会话记忆成功 {summary} content_preview={preview!r}",
                module_name=LOG_MODULE,
            )
        else:
            logger.info(f"查询单条会话记忆成功 {summary} 未命中", module_name=LOG_MODULE)
        return data
    except Exception as e:
        logger.error(
            f"查询单条会话记忆失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="查询会话记忆失败，请查看后端日志获取详细信息")


@router.post("/", summary="创建会话记忆")
async def create_session_memory(
    payload: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    sid = payload.get("session_id")
    preview = _preview_content(payload.get("content"))
    summary = f"session_id={sid!r} content_preview={preview!r}"
    try:
        logger.info(f"创建会话记忆 {summary}", module_name=LOG_MODULE)
        engine.session_memory_create(json.dumps(payload, ensure_ascii=False))
        logger.info(f"创建会话记忆成功 {summary}", module_name=LOG_MODULE)
        return {"ok": True}
    except Exception as e:
        logger.error(
            f"创建会话记忆失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="创建会话记忆失败，请查看后端日志获取详细信息")


@router.patch("/{id}", summary="更新会话记忆")
async def update_session_memory(
    id: str,
    patch: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    keys = sorted(list(patch.keys()))
    content_preview = "content" in patch and _preview_content(patch.get("content")) or None
    summary = (
        f"id={id!r} updated_keys={keys}"
        + (f" content_preview={content_preview!r}" if content_preview else "")
    )
    try:
        logger.info(f"更新会话记忆 {summary}", module_name=LOG_MODULE)
        engine.session_memory_update(id, json.dumps(patch, ensure_ascii=False))
        logger.info(f"更新会话记忆成功 {summary}", module_name=LOG_MODULE)
        return {"ok": True}
    except Exception as e:
        logger.error(
            f"更新会话记忆失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="更新会话记忆失败，请查看后端日志获取详细信息")


@router.delete("/{id}", summary="删除会话记忆")
async def delete_session_memory(id: str, engine=Depends(_get_engine)) -> Any:
    summary = f"id={id!r}"
    try:
        logger.info(f"删除会话记忆 {summary}", module_name=LOG_MODULE)
        engine.session_memory_delete(id)
        logger.info(f"删除会话记忆成功 {summary}", module_name=LOG_MODULE)
        return {"ok": True}
    except Exception as e:
        logger.error(
            f"删除会话记忆失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="删除会话记忆失败，请查看后端日志获取详细信息")
