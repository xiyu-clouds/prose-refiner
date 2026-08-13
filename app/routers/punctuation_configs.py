import json
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends

from app.routers._common import _get_engine
from app.utils import cache_manager

router = APIRouter(prefix="/api/punctuation-configs", tags=["标点配置 (Punctuation Configs)"])
_CK_PUNCTUATION = cache_manager.CK_CONFIG_PUNCTUATION


def _is_empty_dict(v: Any) -> bool:
    """空字典视为“无有效配置”：不缓存，避免把历史脏数据（{}）缓存 1800 秒。"""
    return isinstance(v, dict) and len(v) == 0


@router.get("/", summary="查询标点配置列表")
async def list_punctuation_configs(engine=Depends(_get_engine)) -> Any:
    return engine.punctuation_config_list()


@router.get("/config/get", summary="获取全局标点配置（快捷单例接口）")
async def get_punctuation_config(engine=Depends(_get_engine)) -> Any:
    cached = cache_manager.get(_CK_PUNCTUATION)
    if cached is not None and not _is_empty_dict(cached):
        return cached
    result = engine.punctuation_config_get_config()
    # 空字典不缓存，避免把历史脏数据缓存导致页面一直空白
    if not _is_empty_dict(result):
        cache_manager.set_value(_CK_PUNCTUATION, result, cache_manager.DEFAULT_TTL_CONFIG)
    return result


@router.post("/config/save", summary="保存全局标点配置（快捷单例接口，语义 UPSERT）")
async def save_punctuation_config(
    config: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    engine.punctuation_config_save_config(json.dumps(config, ensure_ascii=False))
    cache_manager.invalidate(_CK_PUNCTUATION)
    return {"ok": True}


@router.get("/{id}", summary="查询单个标点配置（当前为单例，固定传 id='1' 即可）")
async def get_punctuation_config_by_id(id: str, engine=Depends(_get_engine)) -> Any:
    return engine.punctuation_config_get(id)


@router.post("/", summary="创建标点配置")
async def create_punctuation_config(
    payload: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    engine.punctuation_config_create(json.dumps(payload, ensure_ascii=False))
    cache_manager.invalidate(_CK_PUNCTUATION)
    return {"ok": True}


@router.patch("/{id}", summary="更新标点配置")
async def update_punctuation_config(
    id: str,
    patch: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    engine.punctuation_config_update(id, json.dumps(patch, ensure_ascii=False))
    cache_manager.invalidate(_CK_PUNCTUATION)
    return {"ok": True}


@router.delete("/{id}", summary="删除标点配置")
async def delete_punctuation_config(id: str, engine=Depends(_get_engine)) -> Any:
    engine.punctuation_config_delete(id)
    cache_manager.invalidate(_CK_PUNCTUATION)
    return {"ok": True}
