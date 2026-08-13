import json
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, Query

from app.routers._common import _get_engine

router = APIRouter(prefix="/api/dao-configs", tags=["道配置 (DAO Configs)"])


@router.get("/config/get", summary="获取作品道配置（快捷单例接口）")
async def get_dao_config_shortcut(
    session_id: str = Query(..., description="作品会话 ID"),
    engine=Depends(_get_engine),
) -> Any:
    return engine.dao_config_get(session_id)


@router.post("/config/save", summary="保存作品道配置（快捷单例接口，与 PATCH /{session_id} 等价）")
async def save_dao_config_shortcut(
    session_id: str = Query(..., description="作品会话 ID"),
    patch: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    engine.dao_config_update(session_id, json.dumps(patch, ensure_ascii=False))
    return {"ok": True}


@router.get("/{session_id}", summary="查询作品的道配置（不存在则自动初始化默认值）")
async def get_dao_config(session_id: str, engine=Depends(_get_engine)) -> Any:
    return engine.dao_config_get(session_id)


@router.patch("/{session_id}", summary="更新作品的道配置")
async def update_dao_config(
    session_id: str,
    patch: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    engine.dao_config_update(session_id, json.dumps(patch, ensure_ascii=False))
    return {"ok": True}
