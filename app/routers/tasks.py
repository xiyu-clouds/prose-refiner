import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Query, HTTPException

from app.routers._common import _get_engine
from app.core.domain.tasks.payload_tool import (
    prepare_create_payload as _prepare_create_payload,
    prepare_update_patch as _prepare_update_patch,
)
from app.core.domain.media.cascade_cleaner import (
    cascade_cleanup_media_by_task_ids,
    collect_task_subtree_ids,
)
from app.utils.logger import LoggerManager as logger

LOG_MODULE = "任务删除"

router = APIRouter(prefix="/api/tasks", tags=["任务 (Tasks)"])


@router.get("/", summary="查询任务列表（按作品隔离，支持类型过滤与排序）")
async def list_tasks(
    session_id: str = Query(..., description="作品会话 ID"),
    task_type: Optional[str] = Query(None, description="能力配置ID (如 'extract_session_memory')"),
    order_by: Optional[str] = Query(None, description="排序字段：sequence / created_at / id"),
    desc: Optional[bool] = Query(None, description="是否降序，默认升序"),
    exclude_content: Optional[bool] = Query(None, description="是否排除 content_text 字段（轻量列表查询），默认 false"),
    engine=Depends(_get_engine),
) -> Any:
    result = engine.task_list(session_id, task_type, order_by, desc, exclude_content)
    return result


@router.get("/{id}", summary="查询单个任务")
async def get_task(id: str, engine=Depends(_get_engine)) -> Any:
    return engine.task_get(id)


@router.post("/", summary="创建任务")
async def create_task(payload: Dict[str, Any] = Body(...), engine=Depends(_get_engine)) -> Any:
    safe_payload = _prepare_create_payload(payload)
    if not safe_payload.get("task_type", ""):
        raise HTTPException(status_code=400, detail="创建任务必须显式指定 task_type，禁止使用默认值")
    engine.task_create(json.dumps(safe_payload, ensure_ascii=False))
    return {"ok": True}


@router.patch("/{id}", summary="更新任务")
async def update_task(
    id: str,
    patch: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    safe_patch = _prepare_update_patch(patch)
    engine.task_update(id, json.dumps(safe_patch, ensure_ascii=False))
    return {"ok": True}


@router.delete("/{id}", summary="删除任务（同步清理关联多媒体文件）")
async def delete_task(id: str, engine=Depends(_get_engine)) -> Any:
    try:
        task_id_int = int(id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"任务 id={id!r} 不是有效的整数")

    # 先级联清理关联的多媒体（先删物理文件+media记录，再删任务，避免FK级联导致记录丢失无法取file_path）
    try:
        subtree = collect_task_subtree_ids(engine, task_id_int)
        media_cleaned = cascade_cleanup_media_by_task_ids(engine, subtree)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[单任务删除] task={task_id_int} 前置 media 清理失败，仍继续删任务: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        media_cleaned = {"audio": -1, "image": -1, "video": -1}

    logger.info(
        f"[单任务删除] begin task={task_id_int}, media_cleaned={media_cleaned}",
        module_name=LOG_MODULE,
    )
    engine.task_delete(id)
    logger.info(
        f"[单任务删除] success task={task_id_int}",
        module_name=LOG_MODULE,
    )
    return {"ok": True, "media_cleaned": media_cleaned}


@router.delete("/cascade/{id}", summary="级联删除指定节点及其所有子任务（同步清理关联多媒体文件）")
async def delete_task_cascade(id: str, engine=Depends(_get_engine)) -> Any:
    try:
        task_id_int = int(id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"任务 id={id!r} 不是有效的整数")

    # 1) 递归收集 root + 所有后代任务 id（基于 parent_id）
    try:
        subtree = collect_task_subtree_ids(engine, task_id_int)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[级联任务删除] task={task_id_int} 收集子任务失败，退化为只清理 root: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        subtree = {task_id_int}

    # 2) 先级联清理关联的多媒体（顺序必须在 task_delete_cascade 之前，否则 FK 级联删 media 记录后拿不到 file_path）
    try:
        media_cleaned = cascade_cleanup_media_by_task_ids(engine, subtree)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[级联任务删除] task={task_id_int} 前置 media 清理失败，仍继续删任务: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        media_cleaned = {"audio": -1, "image": -1, "video": -1}

    logger.info(
        f"[级联任务删除] begin root={task_id_int}, subtree_count={len(subtree)}, media_cleaned={media_cleaned}",
        module_name=LOG_MODULE,
    )
    engine.task_delete_cascade(id)
    logger.info(
        f"[级联任务删除] success root={task_id_int}, 共级联删除 {len(subtree)} 条任务",
        module_name=LOG_MODULE,
    )
    return {"ok": True, "subtree_count": len(subtree), "media_cleaned": media_cleaned}


@router.post("/semantic-upsert", summary="语义化 upsert 创建/覆写任务")
async def semantic_upsert_task(payload: Dict[str, Any] = Body(...), engine=Depends(_get_engine)) -> Any:
    safe_payload = _prepare_create_payload(payload)
    if not safe_payload.get("task_type", ""):
        raise HTTPException(status_code=400, detail="语义化 upsert 必须显式指定 task_type，禁止使用默认值")
    task_id = engine.task_upsert_semantic(json.dumps(safe_payload, ensure_ascii=False))
    return {"ok": True, "task_id": task_id}
