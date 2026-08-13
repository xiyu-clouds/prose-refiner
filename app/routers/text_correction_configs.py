import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends

from app.routers._common import _get_engine
from app.utils import cache_manager

router = APIRouter(prefix="/api/text-correction-configs", tags=["文本纠错配置 (Text Correction Configs)"])
_CK_TEXT_CORRECTION = cache_manager.CK_CONFIG_TEXT_CORRECTION


def _is_empty_dict(v: Any) -> bool:
    """空字典视为「无有效配置」：不缓存、缓存命中时视为 miss，避免脏数据 {} 影响页面 30 分钟。"""
    return isinstance(v, dict) and len(v) == 0


@router.get("/", summary="查询文本纠错配置列表")
async def list_text_correction_configs(engine=Depends(_get_engine)) -> Any:
    return engine.text_correction_config_list()


@router.get("/config/get", summary="获取全局文本纠错配置（快捷单例接口）")
async def get_text_correction_config(engine=Depends(_get_engine)) -> Any:
    cached = cache_manager.get(_CK_TEXT_CORRECTION)
    if cached is not None and not _is_empty_dict(cached):
        return cached
    result = engine.text_correction_config_get_config()
    if not _is_empty_dict(result):
        cache_manager.set_value(_CK_TEXT_CORRECTION, result, cache_manager.DEFAULT_TTL_CONFIG)
    return result


@router.post("/config/save", summary="保存全局文本纠错配置（快捷单例接口）")
async def save_text_correction_config(
    config: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    engine.text_correction_config_save_config(json.dumps(config, ensure_ascii=False))
    cache_manager.invalidate(_CK_TEXT_CORRECTION)
    return {"ok": True}


@router.get("/{id}", summary="查询单条文本纠错配置")
async def get_text_correction_config_by_id(id: str, engine=Depends(_get_engine)) -> Any:
    return engine.text_correction_config_get(id)


@router.post("/", summary="创建文本纠错配置")
async def create_text_correction_config(
    payload: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    engine.text_correction_config_create(json.dumps(payload, ensure_ascii=False))
    cache_manager.invalidate(_CK_TEXT_CORRECTION)
    return {"ok": True}


@router.patch("/{id}", summary="更新文本纠错配置")
async def update_text_correction_config(
    id: str,
    patch: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    engine.text_correction_config_update(id, json.dumps(patch, ensure_ascii=False))
    cache_manager.invalidate(_CK_TEXT_CORRECTION)
    return {"ok": True}


@router.delete("/{id}", summary="删除文本纠错配置")
async def delete_text_correction_config(id: str, engine=Depends(_get_engine)) -> Any:
    engine.text_correction_config_delete(id)
    cache_manager.invalidate(_CK_TEXT_CORRECTION)
    return {"ok": True}
