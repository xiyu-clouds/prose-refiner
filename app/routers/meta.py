from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException
from app.common import keys as ke
from app.common import values as va
from app.routers._common import _get_engine
from app.utils import cache_manager
from app.utils.logger import LoggerManager as logger
from app.core.domain.meta.metadata_builders import (
    build_reasoning_types,
    build_vendor_model_mapping,
    build_card_config,
    build_frontend_thresholds,
    build_frontend_timeouts,
)

CHINESE_NAME = "Meta接口"
_CK_VENDOR_MODEL = cache_manager.CK_META_VENDOR_MODEL
_CK_REASONING_TYPES = cache_manager.CK_META_REASONING_TYPES
_CK_CARD_CONFIG = cache_manager.CK_META_CARD_CONFIG
_CK_FRONTEND_THRESHOLDS = cache_manager.CK_META_FRONTEND_THRESHOLDS
_CK_FRONTEND_TIMEOUTS = "meta:front:timeouts"

router = APIRouter(prefix="/api", tags=["元信息"])


@router.get("/reasoning-types", summary="返回可配置的推理模式注入能力列表（从引擎启动时加载的全局能力元信息常量直接提取 capability_id 和 name）")
async def get_reasoning_types(engine=Depends(_get_engine)):
    cached = cache_manager.get(_CK_REASONING_TYPES)
    if cached is not None:
        return cached
    logger.info("收到获取所有可配置的推理模式注入能力列表请求", module_name=CHINESE_NAME)
    try:
        result = build_reasoning_types(engine)
        cache_manager.set_value(_CK_REASONING_TYPES, result, cache_manager.DEFAULT_TTL_CONFIG)
        return result
    except Exception as e:
        logger.error(f"获取推理模式注入能力列表失败：{e}", module_name=CHINESE_NAME, exc_info=True)
        raise HTTPException(status_code=500, detail="获取推理模式注入能力列表失败，请查看后端日志获取详细信息")


@router.get("/vendor-model", summary="返回所有可配置的厂商和模型（按域分组）")
async def get_vendor_model():
    cached = cache_manager.get(_CK_VENDOR_MODEL)
    if cached is not None:
        return cached
    logger.info("收到获取所有可配置的厂商和模型请求", module_name=CHINESE_NAME)
    try:
        result = build_vendor_model_mapping()
        cache_manager.set_value(_CK_VENDOR_MODEL, result, cache_manager.DEFAULT_TTL_STATIC)
        return result
    except Exception as e:
        logger.error(f"获取可配置的厂商和模型失败：{e}", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail="获取可配置的厂商和模型失败，请查看后端日志获取详细信息")


@router.get("/card-config", summary="归墟页卡片配置")
async def get_card_config(engine=Depends(_get_engine)):
    cached = cache_manager.get(_CK_CARD_CONFIG)
    if cached is not None and isinstance(cached, dict):
        if "novel_bg_image_url" not in cached or "message_wall_bg_image_url" not in cached:
            cached = None
    if cached is not None:
        return cached
    logger.info("查询归墟页卡片配置", module_name=CHINESE_NAME)
    try:
        result = build_card_config(engine)
        cache_manager.set_value(_CK_CARD_CONFIG, result, cache_manager.DEFAULT_TTL_CONFIG)
        return result
    except Exception as e:
        logger.exception("获取归墟页卡片配置失败", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail="获取归墟页卡片配置失败，请查看后端日志获取详细信息")


@router.get("/meta/frontend-thresholds", summary="前端页面所有字符/条数阈值统一真源（注入层+UI层+CRUD层，避免前端硬编码分叉）")
async def get_frontend_thresholds():
    cached = cache_manager.get(_CK_FRONTEND_THRESHOLDS)
    _REQUIRED_OUTLINE_KEYS = (
        "global_plot_chars", "global_plot_suggest_chars", "global_plot_hard_chars",
        "global_summary_chars", "global_summary_suggest_chars", "global_summary_hard_chars",
        "volume_plot_chars", "volume_plot_suggest_chars", "volume_plot_hard_chars",
        "volume_summary_chars", "volume_summary_suggest_chars", "volume_summary_hard_chars",
        "chapter_plot_chars", "chapter_plot_suggest_chars", "chapter_plot_hard_chars",
        "chapter_summary_chars", "chapter_summary_suggest_chars", "chapter_summary_hard_chars",
        "deduction_event_chars", "deduction_event_hard_chars",
        "danmaku_max_chars", "danmaku_max_base_speed",
        "image_prompt_max_chars",
    )
    if cached is not None and isinstance(cached, dict):
        if any(k not in cached for k in _REQUIRED_OUTLINE_KEYS):
            cached = None
    if cached is not None:
        return cached
    logger.info("查询前端阈值配置（注入/UI/CRUD三层统一真源）", module_name=CHINESE_NAME)
    try:
        result = build_frontend_thresholds()
        cache_manager.set_value(_CK_FRONTEND_THRESHOLDS, result, cache_manager.DEFAULT_TTL_CONFIG)
        return result
    except Exception as e:
        logger.exception("获取前端阈值配置失败", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail="获取前端阈值配置失败，请查看后端日志获取详细信息")


@router.get("/meta/frontend-timeout", summary="前端页面超时配置统一真源（避免前端硬编码分叉）")
async def get_frontend_timeouts():
    cached = cache_manager.get(_CK_FRONTEND_TIMEOUTS)
    if cached is not None:
        return cached
    logger.info("查询前端超时配置", module_name=CHINESE_NAME)
    try:
        result = build_frontend_timeouts()
        cache_manager.set_value(_CK_FRONTEND_TIMEOUTS, result, cache_manager.DEFAULT_TTL_CONFIG)
        return result
    except Exception as e:
        logger.exception("获取前端超时配置失败", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail="获取前端超时配置失败，请查看后端日志获取详细信息")


@router.get("/models/options", summary="模型加载与任务元信息枚举")
async def get_model_options() -> Dict[str, Any]:
    return {
        ke.KEY_MODALITIES: va.VAL_SUPPORTED_MODALITIES,
        ke.KEY_LOADER_TYPES: va.VAL_SUPPORTED_LOADER_TYPES,
        ke.KEY_TASKS: va.VAL_SUPPORTED_TASK_TYPES,
    }
