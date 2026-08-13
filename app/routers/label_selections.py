import json
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends

from app.routers._common import _get_engine

router = APIRouter(prefix="/api/label-selections", tags=["标签选择 (Label Selections)"])


@router.get("/{session_id}", summary="查询作品的标签选择结果")
async def get_label_selection(session_id: str, engine=Depends(_get_engine)) -> Any:
    return engine.label_selection_get(session_id)


@router.patch("/{session_id}", summary="更新作品的标签选择结果")
async def update_label_selection(
    session_id: str,
    patch: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    engine.label_selection_update(session_id, json.dumps(patch, ensure_ascii=False))
    return {"ok": True}
