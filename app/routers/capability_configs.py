import json
from typing import Any, Dict, List
from fastapi import APIRouter, Body, Depends, HTTPException
from app.routers._common import _get_engine
from app.utils import cache_manager
from app.utils.logger import LoggerManager as logger

LOG_MODULE = "能力配置接口"

router = APIRouter(prefix="/api/capability-configs", tags=["能力配置 (Capability Configs)"])


@router.get("/config/get", summary="获取全局能力配置（快捷单例接口）")
async def get_global_capability_config_shortcut(engine=Depends(_get_engine)) -> Any:
    try:
        return engine.capability_config_list_global()
    except Exception as e:
        logger.error(f"获取全局能力配置失败: {e}", module_name=LOG_MODULE, exc_info=True)
        raise HTTPException(status_code=500, detail="获取全局能力配置失败，请查看后端日志获取详细信息")


@router.post("/config/save", summary="保存全局能力配置（快捷单例接口，覆盖写入）")
async def save_global_capability_config_shortcut(
    config: List[Dict[str, Any]] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    count = len(config) if isinstance(config, list) else -1
    sample: List[str] = []
    if isinstance(config, list):
        sample = [_cap_preview(c) for c in config[:3] if isinstance(c, dict)]
    summary = f"count={count}, sample={sample}"
    try:
        logger.info(f"保存全局能力配置 {summary}", module_name=LOG_MODULE)
        engine.capability_config_save_global(json.dumps(config, ensure_ascii=False))
        cache_manager.invalidate(cache_manager.CK_META_REASONING_TYPES)
        logger.info(f"保存全局能力配置成功 {summary}", module_name=LOG_MODULE)
        return {"ok": True}
    except Exception as e:
        logger.error(
            f"保存全局能力配置失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="保存全局能力配置失败，请查看后端日志获取详细信息")


def _cap_preview(cap: Any) -> str:
    if not isinstance(cap, dict):
        return ""
    cap_id = cap.get("id") or cap.get("capability_id")
    name = cap.get("name")
    params = cap.get("params")
    params_keys = sorted(list(params.keys())) if isinstance(params, dict) else []
    return f"capability_id={cap_id!r}, name={name!r}, params_keys={params_keys}"


@router.get("/", summary="查询作品能力配置列表")
async def list_capability_configs(
    session_id: str,
    engine=Depends(_get_engine),
) -> Any:
    summary = f"session_id={session_id!r}"
    try:
        logger.info(f"查询能力配置列表 {summary}", module_name=LOG_MODULE)
        data = engine.capability_config_list(session_id)
        count = len(data) if isinstance(data, (list, tuple)) else -1
        sample: List[str] = []
        if isinstance(data, list):
            sample = [_cap_preview(c) for c in data[:3] if isinstance(c, dict)]
        logger.info(
            f"查询能力配置列表成功 {summary}，共 {count} 条（sample={sample}）",
            module_name=LOG_MODULE,
        )
        return data
    except Exception as e:
        logger.error(
            f"查询能力配置列表失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="查询能力配置列表失败，请查看后端日志获取详细信息")


@router.get("/{session_id}/{capability_id}", summary="查询单个能力配置")
async def get_capability_config(
    session_id: str,
    capability_id: str,
    engine=Depends(_get_engine),
) -> Any:
    summary = f"session_id={session_id!r}, capability_id={capability_id!r}"
    try:
        logger.info(f"查询单个能力配置 {summary}", module_name=LOG_MODULE)
        data = engine.capability_config_get(session_id, capability_id)
        preview = _cap_preview(data)
        hit = "命中" if data else "未命中"
        logger.info(
            f"查询单个能力配置成功 {summary} {hit} {preview}",
            module_name=LOG_MODULE,
        )
        return data
    except Exception as e:
        logger.error(
            f"查询单个能力配置失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="查询能力配置失败，请查看后端日志获取详细信息")


@router.post("/", summary="创建能力配置")
async def create_capability_config(
    payload: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    summary = _cap_preview(payload) or f"keys={sorted(list(payload.keys()))}"
    try:
        logger.info(f"创建能力配置 {summary}", module_name=LOG_MODULE)
        engine.capability_config_create(json.dumps(payload, ensure_ascii=False))
        logger.info(f"创建能力配置成功 {summary}", module_name=LOG_MODULE)
        return {"ok": True}
    except Exception as e:
        logger.error(
            f"创建能力配置失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="创建能力配置失败，请查看后端日志获取详细信息")


@router.patch("/{session_id}/{capability_id}", summary="更新能力配置")
async def update_capability_config(
    session_id: str,
    capability_id: str,
    patch: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    keys = sorted(list(patch.keys()))
    summary = f"session_id={session_id!r}, capability_id={capability_id!r}, updated_keys={keys}"
    try:
        logger.info(f"更新能力配置 {summary}", module_name=LOG_MODULE)
        engine.capability_config_update(
            session_id, capability_id, json.dumps(patch, ensure_ascii=False)
        )
        logger.info(f"更新能力配置成功 {summary}", module_name=LOG_MODULE)
        return {"ok": True}
    except Exception as e:
        logger.error(
            f"更新能力配置失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="更新能力配置失败，请查看后端日志获取详细信息")


@router.delete("/{session_id}/{capability_id}", summary="删除能力配置")
async def delete_capability_config(
    session_id: str,
    capability_id: str,
    engine=Depends(_get_engine),
) -> Any:
    summary = f"session_id={session_id!r}, capability_id={capability_id!r}"
    try:
        logger.info(f"删除能力配置 {summary}", module_name=LOG_MODULE)
        engine.capability_config_delete(session_id, capability_id)
        logger.info(f"删除能力配置成功 {summary}", module_name=LOG_MODULE)
        return {"ok": True}
    except Exception as e:
        logger.error(
            f"删除能力配置失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="删除能力配置失败，请查看后端日志获取详细信息")


@router.post("/{session_id}/init-defaults", summary="初始化作品的默认能力配置（从全局模板加载）")
async def init_capability_defaults(
    session_id: str,
    engine=Depends(_get_engine),
) -> Any:
    summary = f"session_id={session_id!r}"
    try:
        logger.info(f"初始化默认能力配置 {summary}", module_name=LOG_MODULE)
        engine.capability_config_init_defaults(session_id)
        logger.info(f"初始化默认能力配置成功 {summary}", module_name=LOG_MODULE)
        return {"ok": True}
    except Exception as e:
        logger.error(
            f"初始化默认能力配置失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="初始化默认能力配置失败，请查看后端日志获取详细信息")


@router.get("/{session_id}/{capability_id}/compiled-prompt", summary="获取已编译的能力提示词（含变量替换、模板渲染）")
async def get_compiled_prompt(
    session_id: str,
    capability_id: str,
    engine=Depends(_get_engine),
) -> Any:
    summary = f"session_id={session_id!r}, capability_id={capability_id!r}"
    try:
        logger.info(f"获取编译后 Prompt {summary}", module_name=LOG_MODULE)
        prompt = engine.capability_config_get_compiled_prompt(session_id, capability_id)
        length = len(prompt) if isinstance(prompt, str) else -1
        preview = (prompt or "")[:120] if isinstance(prompt, str) else ""
        if len(preview) != length:
            preview += f"...(len={length})"
        logger.info(
            f"获取编译后 Prompt 成功 {summary} len={length}",
            module_name=LOG_MODULE,
        )
        return {"compiled_prompt": prompt, "preview": preview}
    except Exception as e:
        logger.error(
            f"获取编译后 Prompt 失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="获取编译后 Prompt 失败，请查看后端日志获取详细信息")


@router.get("/global/list", summary="查询全局能力配置列表（跨作品共享模板）")
async def list_global_capability_configs(engine=Depends(_get_engine)) -> Any:
    try:
        logger.info("查询全局能力配置列表", module_name=LOG_MODULE)
        data = engine.capability_config_list_global()
        count = len(data) if isinstance(data, (list, tuple)) else -1
        sample: List[str] = []
        if isinstance(data, list):
            sample = [_cap_preview(c) for c in data[:3] if isinstance(c, dict)]
        logger.info(
            f"查询全局能力配置列表成功，共 {count} 条（sample={sample}）",
            module_name=LOG_MODULE,
        )
        return data
    except Exception as e:
        logger.error(
            f"查询全局能力配置列表失败: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="查询全局能力配置列表失败，请查看后端日志获取详细信息")


@router.post("/global/save", summary="保存全局能力配置（覆盖写入，JSON 数组）")
async def save_global_capability_configs(
    config: List[Dict[str, Any]] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    count = len(config) if isinstance(config, list) else -1
    sample: List[str] = []
    if isinstance(config, list):
        sample = [_cap_preview(c) for c in config[:3] if isinstance(c, dict)]
    summary = f"count={count}, sample={sample}"
    try:
        logger.info(f"保存全局能力配置 {summary}", module_name=LOG_MODULE)
        engine.capability_config_save_global(json.dumps(config, ensure_ascii=False))
        cache_manager.invalidate(cache_manager.CK_META_REASONING_TYPES)
        logger.info(f"保存全局能力配置成功 {summary}", module_name=LOG_MODULE)
        return {"ok": True}
    except Exception as e:
        logger.error(
            f"保存全局能力配置失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="保存全局能力配置失败，请查看后端日志获取详细信息")
