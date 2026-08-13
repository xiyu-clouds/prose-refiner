import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Query

from app.routers._common import _get_engine

router = APIRouter(prefix="/api/quotes", tags=["引用素材 (Quotes)"])


@router.get("/", summary="查询引用素材列表")
async def list_quotes(
    only_active: Optional[bool] = Query(None, description="可选：仅返回已启用（active=true）的条目"),
    engine=Depends(_get_engine),
) -> Any:
    return engine.quote_list(only_active)


@router.get("/{id}", summary="查询单条引用素材")
async def get_quote(id: str, engine=Depends(_get_engine)) -> Any:
    return engine.quote_get(id)


@router.post("/", summary="创建引用素材")
async def create_quote(
    payload: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    engine.quote_create(json.dumps(payload, ensure_ascii=False))
    return {"ok": True}


@router.patch("/speed", summary="批量更新所有弹幕速度")
async def update_quotes_speed(
    payload: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    base_speed = str(payload.get("base_speed", 40))
    engine.quote_update_all_speed(base_speed)
    return {"ok": True}


@router.patch("/{id}", summary="更新引用素材")
async def update_quote(
    id: str,
    patch: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    engine.quote_update(id, json.dumps(patch, ensure_ascii=False))
    return {"ok": True}


@router.delete("/{id}", summary="删除引用素材")
async def delete_quote(id: str, engine=Depends(_get_engine)) -> Any:
    engine.quote_delete(id)
    return {"ok": True}


@router.post("/{id}/display-fields", summary="更新弹幕展示字段")
async def update_display_fields(
    id: str,
    payload: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    engine.quote_update_display_fields(id, json.dumps(payload, ensure_ascii=False))
    return {"ok": True}
