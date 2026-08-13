"""
全局配置 REST 接口。

持久化唯一来源：Rust 引擎 global_config 表（engine.global_config_*）。
校验 SSOT：app.utils.config_validators.validate_global_config（集中式校验函数）+
           ConfigValidator（cv 静态方法组）负责 float 标准化、类型/范围校验、嵌套结构精细校验。

逗号分隔字段（list 类型）统一使用 utils.text_utils.parse_comma_list 做中英文逗号兼容，
避免因前端漏处理、API 直接调用、环境变量带中文逗号导致数据被当成单元素。
"""
import json
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException

from app.config.config import _unwrap_engine_config, config
from app.routers._common import _get_engine
from app.utils import cache_manager
from app.utils.config_validators import (
    ConfigValidator as cv,
    BOOL_FALSE_VALUES as _BOOL_FALSE_VALUES,
    BOOL_TRUE_VALUES as _BOOL_TRUE_VALUES,
    MASK_STR as _MASK_STR,
    cast_bool as _cast_bool,
    contains_placeholder as _contains_placeholder,
    is_all_stars_placeholder as _is_all_stars_placeholder,
    is_sensitive_key as _is_sensitive_key,
    light_cast_for_patch as _light_cast_for_patch,
    mask_sensitive as _mask_sensitive,
    normalize_config as _normalize_config,
    normalize_full_keys as _normalize_full_keys,
    normalize_key as _normalize_key,
    unwrap_engine_scalar as _unwrap_engine_scalar,
    validate_global_config,
    values_equal as _values_equal,
)
from app.utils.logger import LoggerManager as logger
from app.utils.text_utils import LIST_FIELD_KEYS, parse_comma_list

LOG_MODULE = "全局配置"

# list 字段的 SSOT 统一从 utils.text_utils.LIST_FIELD_KEYS 导入，
# 这里只保留一个本地别名，方便在 GET/PATCH 链路内快速判断。
_LIST_FIELD_KEYS: frozenset = LIST_FIELD_KEYS

router = APIRouter(prefix="/api/global-configs", tags=["全局配置 (Global Configs)"])


# ============ 路由：查询 ============


@router.get("/", summary="查询完整全局配置（单例）")
async def get_full_global_config(engine=Depends(_get_engine)) -> Any:
    try:
        logger.info("查询完整全局配置", module_name=LOG_MODULE)

        # 0) 先把引擎 global_config 表的最新值同步到 Python Config 单例的槽位属性上，
        #    确保「/config 页面一打开 → Config 单例立刻变成 DB 最新值 → 后续任何接口读
        #    属性都直接命中正确值」，完全无需依赖 PATCH 保存后的 sync。
        #    注意：只有引擎内容真的发生了变化才 reload，避免无意义的缓存清空。
        try:
            changed = False
            if hasattr(config, "sync_from_engine"):
                changed = bool(await config.sync_from_engine(engine))
            if hasattr(config, "reload") and changed:
                config.reload()
        except Exception as sync_e:
            logger.warning(
                f"查询全局配置：sync_from_engine 失败（不影响 GET 返回）：{sync_e}",
                module_name=LOG_MODULE,
                exc_info=True,
            )

        # 1) 引擎查询 → 解包 id/config_json/created_at/updated_at 行包装，只剩扁平 KV
        raw = engine.global_config_get_full()
        unwrapped: Dict[str, Any] = _unwrap_engine_config(raw)

        # 1.1) key 规范化：无论引擎 DB 里存的是带前缀还是不带前缀，返回给前端时
        #      统一大写 + 自动补齐 XINHAI_，保证前端 config.js 里的字段永远能命中，
        #      彻底解决「表中已填值但页面显示默认」的 key 不匹配问题。
        unwrapped = _normalize_full_keys(unwrapped)

        # 2) dict/list 规范化 + 标量按 SLOT_CAST_MAP 还原类型（float 不会变成字符串）
        normalized = _normalize_config(unwrapped)

        # 3) **仅**整词敏感字段遮蔽（MAX_TOKENS_EXPANSION_FACTOR 不会命中）
        masked = _mask_sensitive(normalized)

        # 4) 注入运行时动态修正值（如 LOCAL_MODEL_MAX_MEMORY_MB 根据物理内存 × 50% 修正）
        #    这些值只存在于 Python 内存中，需要覆盖数据库返回值，确保前端看到的是实际生效的值
        _runtime_keys = {
            "XINHAI_LOCAL_MODEL_MAX_MEMORY_MB": config.LOCAL_MODEL_MAX_MEMORY_MB,
        }
        for rk, rv in _runtime_keys.items():
            if rk in masked and masked[rk] != rv:
                masked[rk] = rv

        count = len(masked)
        sample_keys = [k for k in list(masked.keys())[:5]]
        logger.info(
            f"查询完整全局配置成功，共 {count} 项（sample keys={sample_keys}，仅整词敏感字段已遮蔽）",
            module_name=LOG_MODULE,
        )
        return masked
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询完整全局配置失败: {e}", module_name=LOG_MODULE, exc_info=True)
        raise HTTPException(status_code=500, detail="查询全局配置失败，请查看后端日志获取详细信息")


@router.get("/{key}", summary="按键查询全局配置单个字段（支持点号路径）")
async def get_global_config_by_key(key: str, engine=Depends(_get_engine)) -> Any:
    try:
        norm_key = _normalize_key(key)
        if not norm_key:
            raise HTTPException(status_code=422, detail=f"非法 key：{key!r}")
        logger.info(
            f"查询全局配置单键 key={norm_key}（敏感={_is_sensitive_key(norm_key)}）",
            module_name=LOG_MODULE,
        )

        # 1) 引擎单键查询，兜底解包（避免误返回行包装）
        raw_value = engine.global_config_get_by_key(norm_key)
        value = _unwrap_engine_scalar(norm_key, raw_value)

        # 2) dict/list 规范化 + 标量类型还原（float 保持 float）
        value = _normalize_config({norm_key: value}).get(norm_key, value)

        # 3) **仅**整词敏感字段遮蔽：
        #    只有有真实非空非占位符值才返回 ***；空值 / None / 含占位符关键词（如
        #    "请输入腾讯云SecretId" / "<your-secret>" 等）都返回空字符串，
        #    让前端显示 placeholder 红色徽章 + placeholder 文字。
        if _is_sensitive_key(norm_key):
            has_real_value = (
                value is not None
                and not _contains_placeholder(value)
                and not (isinstance(value, str) and not value.strip())
                and not (isinstance(value, str) and _is_all_stars_placeholder(value))
            )
            if not has_real_value:
                logger.info(
                    f"查询全局配置单键成功 key={norm_key}（敏感字段为空/占位符值，返回空字符串以便前端显示 placeholder）",
                    module_name=LOG_MODULE,
                )
                return ""
            logger.info(
                f"查询全局配置单键成功 key={norm_key}（整词命中敏感规则：已遮蔽返回）",
                module_name=LOG_MODULE,
            )
            return _MASK_STR

        logger.info(
            f"查询全局配置单键成功 key={norm_key}（值类型={type(value).__name__}）",
            module_name=LOG_MODULE,
        )
        return value
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询全局配置单键失败 key={key}: {e}", module_name=LOG_MODULE, exc_info=True)
        raise HTTPException(status_code=500, detail="查询配置项失败，请查看后端日志获取详细信息")


# ============ 路由：保存（部分更新 → 合并成完整 config_json 再写引擎）============


@router.patch("/", summary="更新全局配置（JSON merge patch，与现有配置合并）")
async def update_global_config(
    patch: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    # ========== Step 0: 基本结构校验 ==========
    if not isinstance(patch, dict):
        raise HTTPException(status_code=422, detail="请求体必须为 JSON 对象（dict）")
    if not patch:
        return {"ok": True, "changed_keys": []}

    # ========== Step 1: 读取当前引擎值（解包 + 规范化）作为 MERGE 基线 ==========
    current_raw = None
    try:
        current_raw = engine.global_config_get_full()
        current_unwrapped: Dict[str, Any] = _unwrap_engine_config(current_raw)
        current: Dict[str, Any] = _normalize_config(current_unwrapped)
    except Exception as e:
        logger.warning(
            f"更新全局配置：读取当前引擎值失败（降级为空基线继续保存）：{e}",
            module_name=LOG_MODULE,
        )
        current = {}

    # ========== Step 2: key 规范化 + 强类型校验 + 占位符/空串 过滤 ==========
    cleaned: Dict[str, Any] = {}
    errors: List[str] = []
    skipped_noop: List[str] = []       # 与现有值相同，跳过
    skipped_empty: List[str] = []      # 空串覆盖已存在有效值，跳过

    patch_keys = sorted(patch.keys())
    for raw_key in patch_keys:
        raw_value = patch[raw_key]
        k = _normalize_key(raw_key)
        if not k:
            errors.append(f"非法 key：{raw_key!r}")
            continue

        # 2.1 全星号占位符（来自 GET 端 _MASK_STR 遮蔽）：拒绝写回
        if _is_all_stars_placeholder(raw_value):
            errors.append(f"字段 {k} 仍为占位符（***），请输入真实值或留空不修改")
            continue

        # 2.2 轻量通用 cast（不依赖字段名）：
        #     - 字符串看起来像 JSON（{/[）→ 解析；
        #     - 布尔关键词：显式转 bool；
        #     - 其它：直接过。
        try:
            coerced = _light_cast_for_patch(raw_value)
            # 只有当字符串看起来是布尔关键词时才做 bool cast，避免把任意非空字符串都转成 True
            if isinstance(raw_value, str):
                lower_stripped = raw_value.strip().lower()
                if lower_stripped in _BOOL_TRUE_VALUES or lower_stripped in _BOOL_FALSE_VALUES:
                    coerced = _cast_bool(raw_value)
            # 对于 list 字段：如果 _light_cast_for_patch 出来还是 str（例如用户直接调 API 传了 "a，b，c"），
            # 再跑一次 parse_comma_list，保证入库一定是干净的 list[str]。
            if k in _LIST_FIELD_KEYS and isinstance(coerced, str):
                coerced = parse_comma_list(coerced) if coerced.strip() else []
        except (ValueError, json.JSONDecodeError) as ve:
            errors.append(str(ve))
            continue

        # 2.3 占位符拦截（**仅针对敏感字段**）：
        if _is_sensitive_key(k) and _contains_placeholder(coerced):
            errors.append(
                f"字段 {k}（敏感配置）包含占位符关键词，请输入真实值或留空不修改。"
                "禁止使用：请输入 / 请填写 / 请选择 / 请设置 / 请替换 / your- / YOUR_ / <your- / TODO / <todo> 等"
            )
            continue

        # 2.4 空字符串 / None 覆盖策略：避免误清空已有有效值
        if coerced is None or (isinstance(coerced, str) and coerced.strip() == ""):
            existing = current.get(k)
            if existing not in (None, "", [], {}):
                skipped_empty.append(k)
                continue

        # 2.5 与现有值完全一致：跳过
        if k in current and _values_equal(current.get(k), coerced):
            skipped_noop.append(k)
            continue

        cleaned[k] = coerced

    # ========== Step 2 bis: 集中式统一校验（取代零散 SLOT_CAST_MAP + _coerce_value_for_key）==========
    # cleaned 组装完后再调用 validate_global_config（cv 工具函数组）做：
    #   - 所有 int/float/bool/dict/list 字段的类型 + 范围 + 枚举 + 渠道合法性校验；
    #   - LLM_PARAMS / DEFAULT_RETRY_CONFIG 的嵌套结构精细校验；
    #   - 以及 float 字段 in-place 标准化（int→float）。
    if cleaned:
        errs = validate_global_config(cleaned)
        if errs:
            errors.extend(errs)

    # ========== Step 3: 有错误 → 直接 422 汇总返回，不做任何保存 ==========
    if errors:
        joined = "\n".join(f"- {e}" for e in errors)
        logger.error(
            f"更新全局配置：字段校验失败（{len(errors)} 项），已中止保存。明细：\n{joined}",
            module_name=LOG_MODULE,
        )
        raise HTTPException(
            status_code=422,
            detail=f"配置字段校验失败（共 {len(errors)} 项）：\n{joined}",
        )

    # ========== Step 4: 无需实际保存 ==========
    if not cleaned:
        masked_skipped = [
            f"{k}(敏感)" if _is_sensitive_key(k) else k
            for k in sorted(set(skipped_empty) | set(skipped_noop))
        ]
        logger.info(
            f"更新全局配置：没有需要实际写入的字段（empty_skip={len(skipped_empty)}, "
            f"noop_skip={len(skipped_noop)}，skip_keys={masked_skipped})",
            module_name=LOG_MODULE,
        )
        return {
            "ok": True,
            "changed_keys": [],
            "skipped_empty": skipped_empty,
            "skipped_noop": skipped_noop,
        }

    # ========== Step 5: 构造「完整配置」→ 写入引擎表（唯一持久化点）==========
    # 把 cleaned（patch）叠到 current 上，生成引擎侧最终要落盘的 config_json 全量字典。
    # Rust 端 global_config_update 直接替换整列 config_json（不做深合并），
    # 因此嵌套 dict 值（如 REASONING_EFFORT_MAP）会被整体替换，用户删除的 key 不会恢复。
    full_config: Dict[str, Any] = {**current, **cleaned}

    cleaned_keys = sorted(cleaned.keys())
    masked_cleaned_keys = [
        f"{k}(敏感)" if _is_sensitive_key(k) else k for k in cleaned_keys
    ]
    full_count = len(full_config)

    try:
        logger.info(
            f"更新全局配置：开始写入引擎 global_config 表（change={len(cleaned_keys)}, "
            f"total={full_count}, changed_keys={masked_cleaned_keys}）",
            module_name=LOG_MODULE,
        )
        # 注意：Python 侧**永远不会**写入默认配置文件（resources/global.json 等）。
        # 此处仅调用 Rust 引擎接口，Rust 内部负责把完整 config_json 持久化到它自己的表。
        payload = json.dumps(full_config, ensure_ascii=False)
        engine.global_config_update(payload)
        cache_manager.invalidate(cache_manager.CK_META_CARD_CONFIG)
        cache_manager.invalidate(cache_manager.CK_META_VENDOR_MODEL)
        cache_manager.invalidate(cache_manager.CK_META_REASONING_TYPES)
        logger.info(
            f"更新全局配置：写入引擎表成功 changed_keys={masked_cleaned_keys}",
            module_name=LOG_MODULE,
        )

        # ========== Step 6: 同步回 Python Config 单例内存 + 热重载 ==========
        try:
            if hasattr(config, "sync_from_engine"):
                await config.sync_from_engine(engine)
            if hasattr(config, "reload"):
                config.reload()
            logger.info(
                "更新全局配置：Python 内存 Config 已 sync_from_engine + reload",
                module_name=LOG_MODULE,
            )
        except Exception as sync_e:
            logger.warning(
                f"更新全局配置：持久化成功，但 Python 内存同步/重载失败（不影响已保存）：{sync_e}",
                module_name=LOG_MODULE,
                exc_info=True,
            )

        result = {
            "ok": True,
            "changed_keys": cleaned_keys,
            "total_keys": full_count,
        }
        if skipped_empty:
            result["skipped_empty"] = skipped_empty
        if skipped_noop:
            result["skipped_noop"] = skipped_noop
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"更新全局配置失败 changed_keys={masked_cleaned_keys}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="更新配置失败，请查看后端日志获取详细信息")


@router.get("/config/get", summary="获取全局配置（快捷单例接口）")
async def get_global_config_shortcut(engine=Depends(_get_engine)) -> Any:
    return await get_full_global_config(engine)


@router.post("/config/save", summary="保存全局配置（快捷单例接口，与 PATCH / 等价：JSON merge patch）")
async def save_global_config_shortcut(
    patch: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    return await update_global_config(patch, engine)
