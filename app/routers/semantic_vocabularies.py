import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Query

from app.core.services.local_tools import LocalTextTools
from app.routers._common import _get_engine
from app.core.domain.semantic.vocabulary_normalizer import (
    normalize_semantic_payload as _normalize_semantic_payload,
    row_to_dict as _row_to_dict,
    _s,
)

router = APIRouter(prefix="/api/semantic-vocabularies", tags=["语义词汇 (Semantic Vocabularies)"])


@router.get("/", summary="查询语义词汇列表（按作品隔离）")
async def list_semantic_vocabularies(
    session_id: str = Query(..., description="作品会话 ID"),
    category: Optional[str] = Query(None, description="可选：按词汇分类过滤"),
    engine=Depends(_get_engine),
) -> Any:
    return engine.semantic_vocabulary_list(session_id, category)


@router.get("/{id}", summary="查询单条语义词汇")
async def get_semantic_vocabulary(id: str, engine=Depends(_get_engine)) -> Any:
    return engine.semantic_vocabulary_get(id)


@router.post("/", summary="创建语义词汇")
async def create_semantic_vocabulary(
    payload: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    normalized = _normalize_semantic_payload(payload)
    engine.semantic_vocabulary_create(json.dumps(normalized, ensure_ascii=False))
    session_id = _s(normalized.get("session_id")).strip()
    if session_id:
        try:
            LocalTextTools.get_instance().sync_jieba_userdict_for_session(engine, session_id)
        except Exception:
            pass
    return {"ok": True}


@router.patch("/{id}", summary="更新语义词汇")
async def update_semantic_vocabulary(
    id: str,
    patch: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    if not isinstance(patch, dict):
        patch = {}
    category = (patch.get("category") or "").strip()
    if not category:
        existing = _row_to_dict(engine.semantic_vocabulary_get(id))
        if existing:
            category = _s(existing.get("category"))
            for k, v in existing.items():
                if k not in patch and k != "id":
                    patch[k] = v
    normalized = _normalize_semantic_payload(patch, category_override=category or None)
    engine.semantic_vocabulary_update(id, json.dumps(normalized, ensure_ascii=False))
    session_id = _s(normalized.get("session_id")).strip()
    if session_id:
        try:
            LocalTextTools.get_instance().sync_jieba_userdict_for_session(engine, session_id)
        except Exception:
            pass
    return {"ok": True}


@router.delete("/{id}", summary="删除语义词汇")
async def delete_semantic_vocabulary(id: str, engine=Depends(_get_engine)) -> Any:
    session_id = ""
    try:
        existing = _row_to_dict(engine.semantic_vocabulary_get(id)) or {}
        session_id = _s(existing.get("session_id")).strip()
    except Exception:
        pass
    engine.semantic_vocabulary_delete(id)
    if session_id:
        try:
            LocalTextTools.get_instance().sync_jieba_userdict_for_session(engine, session_id)
        except Exception:
            pass
    return {"ok": True}


@router.get("/actions/next-sort-index", summary="查询某类别下一个可用的 sort_index（默认=主要时间 temporal，空集=0，非空=MAX+1）")
async def next_semantic_vocabulary_sort_index(
    session_id: str = Query(..., description="作品会话 ID"),
    category: Optional[str] = Query("temporal", description="词汇类别，默认 temporal（主要时间）"),
    engine=Depends(_get_engine),
) -> Dict[str, Any]:
    value = engine.semantic_vocabulary_next_sort_index(session_id, category)
    return {"ok": True, "next_sort_index": int(value), "category": category or "temporal"}
