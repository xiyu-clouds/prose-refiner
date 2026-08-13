"""元信息构建器 —— 推理能力列表、厂商模型映射、卡片配置、前端阈值、前端超时。

从 routers/meta.py 提取，纯函数化：不处理缓存（缓存命中/写入留在路由薄封装层），
不抛 HTTPException（异常由路由层捕获转换为 HTTP 响应）。
"""

from typing import Any, Dict

from app.common import keys as ke
from app.common import values as va
from app.common.llm_constants import LLMModelType, LLMTypeVendorModelMapping
from app.config.config import config
from app.utils.logger import LoggerManager as logger

LOG_MODULE = "Meta接口"


def build_reasoning_types(engine: Any) -> Dict[str, Any]:
    """从引擎全局能力元信息提取推理模式注入能力列表。"""
    metas = engine.capability_meta_list_global()
    types = []
    if isinstance(metas, list):
        for m in metas:
            if not isinstance(m, dict):
                continue
            cap_id = str(m.get("capability_id") or "").strip()
            if not cap_id:
                continue
            cap_name = str(m.get("name") or cap_id).strip()
            types.append({"id": cap_id, "name": cap_name})
    logger.info(
        f"推理模式注入能力列表获取成功，共 {len(types)} 条",
        module_name=LOG_MODULE,
    )
    return {ke.KEY_TYPES: types}


def build_vendor_model_mapping() -> Dict[str, Any]:
    """按"域→厂商→模型"三级映射生成前端下拉数据源。"""
    domains = [
        LLMModelType.TEXT,
        LLMModelType.AUDIO_TTS,
        LLMModelType.IMAGE,
        LLMModelType.VIDEO,
    ]
    vendor_by_domain = {}
    model_by_domain_vendor = {}
    for domain in domains:
        vendors = LLMTypeVendorModelMapping.get_vendors_by_type(domain)
        vendor_by_domain[domain] = vendors
        model_by_domain_vendor[domain] = {
            v: LLMTypeVendorModelMapping.get_models_by_type_vendor(domain, v)
            for v in vendors
        }
    logger.info("可配置的厂商和模型获取成功（按域分组）", module_name=LOG_MODULE)
    return {
        ke.KEY_VENDOR_BY_DOMAIN: vendor_by_domain,
        ke.KEY_MODEL_BY_DOMAIN_VENDOR: model_by_domain_vendor,
    }


def build_card_config(engine: Any) -> Dict[str, Any]:
    """构建归墟页卡片配置（背景图、刷新间隔、图片数量等）。"""
    image_count = int(engine.image_count(None, None)) or config.IMAGE_COUNT
    refresh_interval_ms = config.REFRESH_INTERVAL_MS
    header_bg_image_id = config.HEADER_BG_IMAGE_ID
    footer_bg_image_id = config.FOOTER_BG_IMAGE_ID
    default_bg_image_id = config.DEFAULT_BG_IMAGE_ID
    novel_bg_image_id = config.NOVEL_BG_IMAGE_ID
    message_wall_bg_image_id = config.MESSAGE_WALL_BG_IMAGE_ID

    header_image = {}
    footer_image = {}
    default_image = {}
    novel_image = {}
    message_wall_image = {}
    try:
        if header_bg_image_id:
            header_image = engine.image_get(str(header_bg_image_id)) or {}
        if footer_bg_image_id:
            footer_image = engine.image_get(str(footer_bg_image_id)) or {}
        if default_bg_image_id:
            default_image = engine.image_get(str(default_bg_image_id)) or {}
        if novel_bg_image_id:
            novel_image = engine.image_get(str(novel_bg_image_id)) or {}
        if message_wall_bg_image_id:
            message_wall_image = engine.image_get(str(message_wall_bg_image_id)) or {}
    except Exception:
        pass

    return {
        ke.KEY_IMAGE_COUNT: image_count,
        ke.KEY_REFRESH_INTERVAL_MS: refresh_interval_ms,
        "header_bg_image_id": header_bg_image_id,
        "header_bg_image_url": f"/media/image/{header_image.get('file_name', '')}" if header_image.get('file_name') else "",
        "footer_bg_image_id": footer_bg_image_id,
        "footer_bg_image_url": f"/media/image/{footer_image.get('file_name', '')}" if footer_image.get('file_name') else "",
        "default_bg_image_id": default_bg_image_id,
        "default_bg_image_url": f"/media/image/{default_image.get('file_name', '')}" if default_image.get('file_name') else "",
        "novel_bg_image_id": novel_bg_image_id,
        "novel_bg_image_url": f"/media/image/{novel_image.get('file_name', '')}" if novel_image.get('file_name') else "",
        "message_wall_bg_image_id": message_wall_bg_image_id,
        "message_wall_bg_image_url": f"/media/image/{message_wall_image.get('file_name', '')}" if message_wall_image.get('file_name') else "",
    }


def build_frontend_thresholds() -> Dict[str, Any]:
    """构建前端页面所有字符/条数阈值统一真源。"""
    nlp_chars = va.VAL_INJECT_NLP_SUMMARY_CHARS
    session_chars = va.VAL_INJECT_SESSION_MEMORY_CHARS
    return {
        "character_count": va.VAL_INJECT_CHARACTER_COUNT,
        "character_chars": va.VAL_INJECT_CHARACTER_CHARS,
        "timeline_count": va.VAL_INJECT_TIMELINE_COUNT,
        "timeline_chars": va.VAL_INJECT_TIMELINE_CHARS,
        "location_count": va.VAL_INJECT_LOCATION_COUNT,
        "location_chars": va.VAL_INJECT_LOCATION_CHARS,
        "session_count": va.VAL_INJECT_SESSION_MEMORY_COUNT,
        "session_chars": session_chars,
        "session_memory_chars": session_chars,
        "session_memory_hard_chars": session_chars,
        "nlp_chars": nlp_chars,
        "user_input_chars": nlp_chars * 2,
        "match_k": va.VAL_INJECT_MATCH_KEYWORDS_TOP_K,
        "core_plot_max_chars": nlp_chars * 2,
        "global_plot_chars": int(va.VAL_OUTLINE_GLOBAL_PLOT_SUGGEST_CHARS),
        "global_plot_suggest_chars": int(va.VAL_OUTLINE_GLOBAL_PLOT_SUGGEST_CHARS),
        "global_plot_hard_chars": int(va.VAL_OUTLINE_GLOBAL_PLOT_HARD_CHARS),
        "global_summary_chars": int(va.VAL_OUTLINE_GLOBAL_SUMMARY_SUGGEST_CHARS),
        "global_summary_suggest_chars": int(va.VAL_OUTLINE_GLOBAL_SUMMARY_SUGGEST_CHARS),
        "global_summary_hard_chars": int(va.VAL_OUTLINE_GLOBAL_SUMMARY_HARD_CHARS),
        "volume_plot_chars": int(va.VAL_OUTLINE_VOLUME_PLOT_SUGGEST_CHARS),
        "volume_plot_suggest_chars": int(va.VAL_OUTLINE_VOLUME_PLOT_SUGGEST_CHARS),
        "volume_plot_hard_chars": int(va.VAL_OUTLINE_VOLUME_PLOT_HARD_CHARS),
        "volume_summary_chars": int(va.VAL_OUTLINE_VOLUME_SUMMARY_SUGGEST_CHARS),
        "volume_summary_suggest_chars": int(va.VAL_OUTLINE_VOLUME_SUMMARY_SUGGEST_CHARS),
        "volume_summary_hard_chars": int(va.VAL_OUTLINE_VOLUME_SUMMARY_HARD_CHARS),
        "chapter_plot_chars": int(va.VAL_OUTLINE_CHAPTER_PLOT_SUGGEST_CHARS),
        "chapter_plot_suggest_chars": int(va.VAL_OUTLINE_CHAPTER_PLOT_SUGGEST_CHARS),
        "chapter_plot_hard_chars": int(va.VAL_OUTLINE_CHAPTER_PLOT_HARD_CHARS),
        "chapter_summary_chars": int(va.VAL_OUTLINE_CHAPTER_SUMMARY_SUGGEST_CHARS),
        "chapter_summary_suggest_chars": int(va.VAL_OUTLINE_CHAPTER_SUMMARY_SUGGEST_CHARS),
        "chapter_summary_hard_chars": int(va.VAL_OUTLINE_CHAPTER_SUMMARY_HARD_CHARS),
        "deduction_event_chars": int(va.VAL_DEDUCTION_EVENT_SUGGEST_CHARS),
        "deduction_event_hard_chars": int(va.VAL_DEDUCTION_EVENT_HARD_CHARS),
        "image_prompt_max_chars": int(va.VAL_IMAGE_PROMPT_MAX_CHARS),
        "weave_field_limits": {
            "common": {
                "name": va.VAL_WEAVE_NAME_MAX,
                "type": va.VAL_WEAVE_TYPE_MAX,
                "aliases": va.VAL_WEAVE_ALIASES_MAX,
                "identity": va.VAL_WEAVE_IDENTITY_MAX,
                "rel_type": va.VAL_WEAVE_REL_TYPE_MAX,
                "attr_key": va.VAL_WEAVE_ATTR_KEY_MAX,
                "attr_value": va.VAL_WEAVE_ATTR_VALUE_MAX,
            },
            "character": {
                "secret": va.VAL_WEAVE_CHAR_SECRET_MAX,
                "total": va.VAL_WEAVE_CHAR_TOTAL_MAX,
                "max_attrs": va.VAL_WEAVE_ATTRS_MAX_COUNT_CHARACTER,
                "max_relations": va.VAL_WEAVE_RELS_MAX_COUNT_CHARACTER,
            },
            "temporal": {
                "description": va.VAL_WEAVE_TIME_DESC_MAX,
                "total": va.VAL_WEAVE_TIME_TOTAL_MAX,
                "max_attrs": va.VAL_WEAVE_ATTRS_MAX_COUNT_TEMPORAL,
            },
            "location": {
                "description": va.VAL_WEAVE_LOC_DESC_MAX,
                "total": va.VAL_WEAVE_LOC_TOTAL_MAX,
                "max_attrs": va.VAL_WEAVE_ATTRS_MAX_COUNT_LOCATION,
            },
        },
        "danmaku_max_chars": va.DANMAKU_MAX_CHARS,
        "danmaku_max_base_speed": va.DANMAKU_MAX_BASE_SPEED,
    }


def build_frontend_timeouts() -> Dict[str, Any]:
    """构建前端页面超时配置。"""
    text_timeout = int(config.TEXT_API_TIMEOUT)
    return {
        "text_api_timeout_seconds": text_timeout,
        "batch_api_timeout_seconds": max(text_timeout, 300),
        "image_gen_timeout_seconds": 180,
        "audio_gen_timeout_seconds": 600,
        "video_gen_timeout_seconds": 1800,
    }
