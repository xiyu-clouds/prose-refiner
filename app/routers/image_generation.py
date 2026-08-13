import asyncio
import json
import os
import random
import time
from typing import Any, Dict, Optional

import requests
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.common.image_capabilities import (
    IMAGE_MODEL_CAPABILITIES,
    get_default_enable_sequential,
    get_default_thinking_mode,
    get_image_capabilities,
    get_valid_sizes,
    is_supports_batch_n,
    is_supports_color_palette,
    is_supports_negative_prompt,
    is_supports_sequential,
    is_supports_thinking_mode,
)
from app.common.llm_constants import LLMVendor, LLMModelType, LLMTypeVendorModelMapping
from app.common import values as va
from app.config.config import config
from app.core.domain.media.cascade_cleaner import attach_ownership
from app.core.services.sse_manager import get_sse_manager
from app.core.registry.global_singleton_registry import GlobalSingletonRegistry
from app.routers._common import _get_engine
from app.utils.logger import LoggerManager as logger
from app.utils.retry_util import is_retryable_exception
from app.core.domain.images.rate_limit import (
    check_rate_limit as _check_rate_limit,
    record_call as _record_call,
    is_rate_limit_exception as _is_rate_limit_exception,
    extract_retry_after as _extract_retry_after,
    INTER_BATCH_INTERVAL,
    RATE_LIMIT_BACKOFF_BASE,
    MAX_RETRIES_PER_IMAGE,
)
from app.core.domain.images.tongyi_wanxiang import (
    call_sync_image_api as _call_sync_image_api,
)

router = APIRouter(prefix="/api/images/generate", tags=["图片生成 (Image Generation)"])
LOG_MODULE = "图片生成路由"


async def _get_registry() -> GlobalSingletonRegistry:
    return await GlobalSingletonRegistry.get_instance()


async def _refine_image_prompt(
    session_id: str,
    user_prompt: str,
    engine,
    registry: GlobalSingletonRegistry,
) -> str:
    """
    调用 image_prompt_refine 能力，优化用户输入的图像生成提示词。

    通过标准能力调用流程（加载配置 → 渲染 Prompt → 调用 LLM → 解析 JSON），
    返回优化后的提示词文本；失败抛 HTTPException。
    不预创建 task、不回填 task，但记录 llm_invoke_log。
    """
    from app.core.domain.capabilities.core import (
        _resolve_capability, _load_compiled_prompt,
        _parse_llm_dict_response, _write_llm_log,
        _record_capability_stat_safely,
    )
    from app.core.domain.capabilities.handlers_core import (
        _prepare_and_render_prompt, _invoke_llm_and_get_response,
    )

    capability_id = "image_prompt_refine"
    summary = f"session_id={session_id!r}, capability_id={capability_id!r}"

    # 1. 加载能力配置
    cap = await _resolve_capability(session_id, capability_id, engine, summary)

    # 2. 加载编译后的 prompt
    compiled_prompt = _load_compiled_prompt(session_id, capability_id, engine, summary)

    # 3. 渲染 prompt（填入 user_prompt）
    variables = {
        "user_prompt": user_prompt,
    }
    formatted_prompt, _, *_ = _prepare_and_render_prompt(
        session_id, capability_id, variables, engine,
        compiled_prompt, summary, 0, 0,
    )

    # 4. 调用 LLM
    llm_resp = await _invoke_llm_and_get_response(
        cap, registry, formatted_prompt, session_id, capability_id,
    )

    # 5. 立即记录 LLM 调用日志和能力统计（无论后续解析是否成功）
    resp_content = getattr(llm_resp, "content", None)
    llm_ok = bool(llm_resp and getattr(llm_resp, "ok", False))
    token_cost = _write_llm_log(
        session_id, capability_id, None,
        formatted_prompt, resp_content, llm_resp, summary, engine,
    )
    _record_capability_stat_safely(
        engine, capability_id, llm_ok, float(token_cost),
    )

    if not llm_ok:
        msg = getattr(llm_resp, "msg", None) or "模型调用失败"
        raise HTTPException(status_code=502, detail=f"图像提示词优化失败: {msg}")

    # 6. 解析返回的 JSON
    parsed = _parse_llm_dict_response(resp_content)
    node = parsed.get("image_prompt_refine")
    if not isinstance(node, dict):
        raise HTTPException(
            status_code=500,
            detail="图像提示词优化结果格式错误：缺少 image_prompt_refine 节点",
        )
    prompt_text = node.get("prompt_text")
    if not isinstance(prompt_text, str) or not prompt_text.strip():
        raise HTTPException(status_code=500, detail="图像提示词优化结果为空")

    logger.info(
        f"图像提示词优化成功 {summary}, prompt_len={len(prompt_text.strip())}",
        module_name=LOG_MODULE,
    )
    return prompt_text.strip()


@router.post("/", summary="生成图片（两阶段可选：用户自定义提示词直接生成 / 或点击优化按钮后再生成）")
async def generate_images(
        session_id: str = Query(..., description="会话ID"),
        volume_index: int = Query(..., description="卷索引"),
        chapter_index: int = Query(..., description="章索引"),
        user_prompt: str = Query(..., description="用户输入的图像提示词（字符上限由 VAL_IMAGE_PROMPT_MAX_CHARS 统一管控，前端 maxlength / 后端校验 / meta 接口三端同源；默认直接作为模型提示词，不再默认走 LLM 优化）"),
        image_size: str = Query("720*1280", description="图片尺寸"),
        negative_prompt: str = Query("", description="负面提示词"),
        batch_size: int = Query(2, description="生成数量（1-4，组图模式1-12）"),
        model: str = Query("", description="图像模型名（空则用全局默认）"),
        thinking_mode: Optional[bool] = Query(None, description="增强推理模式（仅 wan2.7，非组图时）"),
        enable_sequential: Optional[bool] = Query(None, description="组图模式（仅 wan2.7，组图时 n 上限12）"),
        color_palette: str = Query("", description="颜色主题 JSON（仅 wan2.7，非组图时，3-10种颜色 ratio 总和100）"),
        skip_refine_prompt: bool = Query(True, description="是否跳过 LLM 优化（默认 true：直接使用用户输入；false：走 image_prompt_refine 能力优化）——前端默认不传为 true，仅左下角「优化提示词」按钮走独立 refine 接口，再把结果作为 user_prompt 提交到此接口。"),
        engine=Depends(_get_engine),
        registry=Depends(_get_registry),
) -> Dict[str, Any]:
    """生成图片并持久化存储，覆盖旧数据。"""
    # 限流检查
    rate_err = _check_rate_limit()
    if rate_err:
        raise HTTPException(status_code=429, detail=rate_err)

    # 读取图像域配置（厂商 + 模型 + 三级校验）
    vendor = config.IMAGE_DEFAULT_VENDOR
    model = model.strip() or config.IMAGE_DEFAULT_MODEL
    if not LLMTypeVendorModelMapping.is_valid(LLMModelType.IMAGE, vendor, model):
        raise HTTPException(status_code=400, detail=f"不支持的图像模型: {vendor}/{model}")

    # 厂商级密钥（跨域通用）
    api_key = LLMVendor.get_api_key(vendor)
    if not api_key or "请输入" in api_key:
        raise HTTPException(
            status_code=400,
            detail=f"未配置 {vendor} 厂商 API Key，请在全局配置中设置",
        )

    # 参数校验（按模型能力元数据驱动）
    cap = get_image_capabilities(model)

    # --- wan2.7 特有参数校验与默认值填充 ---
    supports_tm = is_supports_thinking_mode(model)
    supports_seq = is_supports_sequential(model)
    supports_cp = is_supports_color_palette(model)

    # enable_sequential：不支持的模型强制 None；支持但未传则用默认
    if not supports_seq:
        enable_sequential = None
    elif enable_sequential is None:
        enable_sequential = get_default_enable_sequential(model)

    # thinking_mode：不支持 → None；支持且非组图 → 未传则用默认；组图模式互斥禁用
    if not supports_tm:
        thinking_mode = None
    elif enable_sequential:
        thinking_mode = None
    elif thinking_mode is None:
        thinking_mode = get_default_thinking_mode(model)

    # color_palette：不支持 → None；组图互斥禁用；非组图时解析 JSON
    # 官方格式（wan2.7-image-pro / wan2.7-image）：[{"hex": "#RRGGBB", "ratio": "xx.xx%"}, ...]
    #   - 3~10 种颜色（推荐 8 种）
    #   - ratio 为百分比字符串，精确到小数点后两位，所有 ratio 总和必须为 100.00%
    #   - 仅 enable_sequential=false 时可用
    color_palette_obj: Optional[list] = None
    if supports_cp and not enable_sequential:
        cp_raw = color_palette.strip()
        if cp_raw:
            try:
                parsed = json.loads(cp_raw)
                if not isinstance(parsed, list) or not (3 <= len(parsed) <= 10):
                    logger.warning(
                        f"color_palette 项数 {len(parsed) if isinstance(parsed, list) else '非数组'} 超出范围（需3-10），忽略颜色主题",
                        module_name=LOG_MODULE,
                    )
                else:
                    total_ratio = 0.0
                    ok_items = []
                    for item in parsed:
                        if not isinstance(item, dict):
                            continue
                        hex_val = str(item.get("hex", "")).strip()
                        # hex 必须为 #RRGGBB 格式
                        if not (hex_val.startswith("#") and len(hex_val) == 7):
                            continue
                        # ratio 可为百分比字符串 "25.00%" 或数字 25.0，统一解析为 float
                        ratio_raw: Any = item.get("ratio")
                        if ratio_raw is None:
                            continue
                        if isinstance(ratio_raw, str):
                            ratio_num = float(ratio_raw.rstrip("%"))
                        else:
                            ratio_num = float(ratio_raw)
                        if ratio_num < 0 or ratio_num > 100:
                            continue
                        total_ratio += ratio_num
                        ok_items.append({"hex": hex_val, "ratio_num": ratio_num})
                    if len(ok_items) >= 3:
                        # ratio 总和归一化到 100.00%（容差 0.01）
                        if abs(total_ratio - 100.0) > 0.01 and total_ratio > 0:
                            scale = 100.0 / total_ratio
                            ok_items = [
                                {"hex": it["hex"], "ratio_num": round(it["ratio_num"] * scale, 2)}
                                for it in ok_items
                            ]
                        # 转为官方百分比字符串格式 "xx.xx%"
                        color_palette_obj = [
                            {"hex": it["hex"], "ratio": f"{it['ratio_num']:.2f}%"}
                            for it in ok_items
                        ]
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                logger.warning(
                    f"color_palette JSON 解析失败，忽略颜色主题: {e}",
                    module_name=LOG_MODULE,
                )

    # --- batch_size 上限按组图模式切换 ---
    if enable_sequential:
        max_cnt = int(cap.get("sequential_max_count", 12))
    else:
        max_cnt = int(cap.get("max_count", 4))
    batch_size = max(1, min(batch_size, max_cnt))

    # 尺寸校验
    valid_sizes = get_valid_sizes(model)
    if image_size not in valid_sizes:
        image_size = cap.get("default_size", "720*1280")
    # 不支持 negative_prompt 的模型清空（避免无效参数下发）
    if not is_supports_negative_prompt(model):
        negative_prompt = ""
    # 用户提示词校验
    user_prompt = user_prompt.strip()
    if not user_prompt:
        raise HTTPException(status_code=400, detail="图像提示词不能为空")
    # 长度上限校验（SSOT: VAL_IMAGE_PROMPT_MAX_CHARS，与前端 maxlength / meta 接口三端统一）
    if len(user_prompt) > va.VAL_IMAGE_PROMPT_MAX_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"图像提示词超过 {va.VAL_IMAGE_PROMPT_MAX_CHARS} 字符上限，请精简后重试",
        )

    sse = get_sse_manager()
    title = f"{session_id}_v{volume_index}_c{chapter_index}"

    # ========== 阶段1：按 skip_refine_prompt 决定是否走 LLM 优化 ==========
    # 需求3：权限让步。默认 skip_refine_prompt=true → 直接使用用户提供的提示词；
    # 只有显式传 skip_refine_prompt=false 时才调用 image_prompt_refine 能力。
    # 前端正常流程：不调模型优化（用户权限让步），需要优化时点左下角「优化提示词」按钮，
    # 走独立的 POST /api/images/generate/refine-prompt，然后把优化结果再 POST 到本接口。
    if skip_refine_prompt:
        refined_prompt = user_prompt
        await sse.broadcast("task_progress", {
            "title": "图片生成",
            "content": "已使用用户输入的画面提示词，准备调用通义万相...",
            "meta": {"progress": 10}
        })
    else:
        await sse.broadcast("task_progress", {
            "title": "图片生成",
            "content": "正在调用大模型优化画面提示词...",
            "meta": {"progress": 5}
        })
        refined_prompt = await _refine_image_prompt(session_id, user_prompt, engine, registry)
        await sse.broadcast("task_progress", {
            "title": "图片生成",
            "content": f"提示词优化完成（{len(refined_prompt)}字），准备调用通义万相...",
            "meta": {"progress": 15}
        })

    # ========== 阶段2：调用通义万相同步 API（按模型能力分流：batch_n 单次多张 / 循环单张，带重试）==========
    MAX_RETRIES = 3
    BACKOFF_BASE = 3.0          # 付费调用限流放宽（120次/分），退避基数大幅下降
    batch_n_model = is_supports_batch_n(model)
    images_data: list = []

    for attempt in range(MAX_RETRIES):
        try:
            await sse.broadcast("task_progress", {
                "title": "图片生成",
                "content": f"正在调用通义万相 API（第 {attempt + 1} 次尝试）...",
                "meta": {"progress": 20 + attempt * 10}
            })

            images_data = []
            if batch_n_model:
                # wan2.7：单次调用 n=batch_size，返回多张 URL；传递 thinking_mode / enable_sequential / color_palette
                urls = await asyncio.to_thread(
                    _call_sync_image_api, model, refined_prompt,
                    image_size, negative_prompt, batch_size, api_key,
                    thinking_mode, enable_sequential, color_palette_obj, None,
                )
                for u in urls:
                    images_data.append({"url": u})
                    await sse.broadcast("task_progress", {
                        "title": "图片生成",
                        "content": f"已生成 {len(images_data)}/{batch_size} 张...",
                        "meta": {"progress": 20 + attempt * 10 + int((len(images_data) / max(batch_size, 1)) * 30)}
                    })
                # 数量不足仅推送提示，不自动补调
                if len(images_data) < batch_size:
                    await sse.broadcast("task_progress", {
                        "title": "图片生成",
                        "content": f"注意：API 仅返回 {len(images_data)}/{batch_size} 张图片",
                        "meta": {"progress": 30, "incomplete": True}
                    })
            else:
                # z-image-turbo / qwen-image-plus：单次仅 n=1，串行发起 + 间隔避让 QPS 限流
                # 阿里云 QPS 限制（免费=1，付费=2），INTER_BATCH_INTERVAL=1.5s 覆盖最坏情况
                # 单张独立重试：429 长 15~25s 退避（读 Retry-After），其他异常短退避
                # 部分降级：单张重试耗尽仅跳过该张，不影响其他张；全部失败才抛错触发外层 attempt
                for img_idx in range(batch_size):
                    # 第 1 张不等待；后续每张前等间隔避开 QPS 滑动窗口
                    if img_idx > 0:
                        await asyncio.sleep(INTER_BATCH_INTERVAL)
                    await sse.broadcast("task_progress", {
                        "title": "图片生成",
                        "content": f"正在生成第 {img_idx + 1}/{batch_size} 张...",
                        "meta": {"progress": 20 + attempt * 10 + int((img_idx / max(batch_size, 1)) * 30)}
                    })
                    last_exc: Optional[Exception] = None
                    single_url: Optional[str] = None
                    for retry_idx in range(MAX_RETRIES_PER_IMAGE):
                        try:
                            if retry_idx > 0 and last_exc is not None:
                                # 重试前等待：429 长退避，其他异常短退避
                                if _is_rate_limit_exception(last_exc):
                                    wait_time = _extract_retry_after(last_exc) or (RATE_LIMIT_BACKOFF_BASE + random.uniform(0, 10))
                                else:
                                    wait_time = BACKOFF_BASE * (2 ** retry_idx) + random.uniform(0, 3)
                                await sse.broadcast("task_progress", {
                                    "title": "图片生成",
                                    "content": f"第 {img_idx + 1} 张失败（{type(last_exc).__name__}），{wait_time:.0f}s 后重试（第 {retry_idx + 1}/{MAX_RETRIES_PER_IMAGE} 次）",
                                    "meta": {"progress": 20 + attempt * 10, "is_retrying": True}
                                })
                                logger.warning(
                                    f"第 {img_idx + 1}/{batch_size} 张失败，{wait_time:.0f}s 后重试: {type(last_exc).__name__}: {last_exc}",
                                    module_name=LOG_MODULE
                                )
                                await asyncio.sleep(wait_time)
                            urls = await asyncio.to_thread(
                                _call_sync_image_api, model, refined_prompt,
                                image_size, negative_prompt, 1, api_key,
                                None, None, None, random.randint(1, 2_000_000_000),
                            )
                            if urls:
                                single_url = urls[0]
                                break
                            last_exc = RuntimeError("通义万相未返回有效图片URL")
                        except Exception as e:
                            last_exc = e
                            # 非可重试异常（如 4xx 非 429）直接抛，不走重试
                            if not is_retryable_exception(e):
                                raise
                            # 可重试异常（429/5xx/网络错误）继续内层重试
                    if single_url:
                        images_data.append({"url": single_url})
                        await sse.broadcast("task_progress", {
                            "title": "图片生成",
                            "content": f"已生成 {len(images_data)}/{batch_size} 张...",
                            "meta": {"progress": 20 + attempt * 10 + int((len(images_data) / max(batch_size, 1)) * 30)}
                        })
                    else:
                        # 单张重试耗尽：部分降级，跳过该张继续后续
                        logger.warning(
                            f"第 {img_idx + 1}/{batch_size} 张重试耗尽，跳过（已成功 {len(images_data)} 张）",
                            module_name=LOG_MODULE
                        )
                        if images_data:
                            # 已有部分成功，继续后续张；不再触发外层 attempt 整体重试
                            continue
                        # 全部失败：抛错触发外层 attempt 整体重试
                        raise RuntimeError(f"通义万相图片生成失败（第 {img_idx + 1}/{batch_size} 张重试耗尽）: {last_exc}")

            if not images_data:
                raise RuntimeError("通义万相未返回有效图片数据")

            _record_call()
            break

        except Exception as e:
            if attempt + 1 >= MAX_RETRIES or not is_retryable_exception(e):
                raise
            wait_time = BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 3)
            await sse.broadcast("task_progress", {
                "title": "图片生成",
                "content": f"API 调用失败，{wait_time:.0f}秒后重试（第 {attempt + 2}/{MAX_RETRIES} 次）",
                "meta": {"progress": 20, "is_retrying": True}
            })
            logger.warning(
                f"通义万相图片生成失败，{wait_time:.0f}s 后重试: {type(e).__name__}: {e}",
                module_name=LOG_MODULE
            )
            await asyncio.sleep(wait_time)

    if not images_data:
        raise RuntimeError("图片生成失败：API 未返回有效数据")

    # ========== 阶段3：下载图片并持久化 ==========
    await sse.broadcast("task_progress", {
        "title": "图片生成",
        "content": f"下载并保存 {len(images_data)} 张图片...",
        "meta": {"progress": 60}
    })

    # 覆盖旧图片
    usage_tag = f"novel_{title}"
    all_images = engine.image_list_by_type("generated")
    for old_img in all_images:
        if old_img.get("usage_tag") == usage_tag:
            old_file_path = old_img.get("file_path", "")
            old_abs = os.path.join(str(config.DATA_ROOT), old_file_path)
            if os.path.exists(old_abs):
                try:
                    os.remove(old_abs)
                except OSError:
                    pass
            try:
                engine.image_delete(str(old_img["id"]))
            except Exception:
                pass
            logger.info(f"已覆盖旧图片: id={old_img['id']}", module_name=LOG_MODULE)

    # 下载并保存新图片
    saved_paths = []
    timestamp = int(time.time())
    for idx, img_data in enumerate(images_data):
        try:
            img_url = img_data.get("url", "")
            if not img_url:
                continue

            await sse.broadcast("task_progress", {
                "title": "图片生成",
                "content": f"下载第 {idx + 1}/{len(images_data)} 张图片...",
                "meta": {"progress": 60 + int((idx / max(len(images_data), 1)) * 30)}
            })

            img_resp = requests.get(img_url, timeout=60)
            img_resp.raise_for_status()

            file_name = f"{timestamp}_{idx}.png"
            file_path = os.path.join(str(config.IMAGE_DIR), file_name)
            with open(file_path, "wb") as f:
                f.write(img_resp.content)

            # 存入数据库
            from PIL import Image as PILImage
            try:
                with PILImage.open(file_path) as pil_img:
                    w, h = pil_img.size
            except Exception:
                w, h = 0, 0

            db_payload = {
                "file_name": file_name,
                "file_path": f"image/{file_name}",
                "file_size": len(img_resp.content),
                "width": w,
                "height": h,
                "image_type": "generated",
                "usage_tag": usage_tag,
            }
            attach_ownership(db_payload, session_id=session_id)
            engine.image_create(json.dumps(db_payload, ensure_ascii=False))
            saved_paths.append(f"/media/image/{file_name}")

        except Exception as e:
            logger.error(f"下载/保存第 {idx + 1} 张图片失败: {e}", module_name=LOG_MODULE)
            continue

    if not saved_paths:
        raise RuntimeError("所有图片下载失败")

    # ========== 完成 ==========
    await sse.broadcast("task_progress", {
        "title": "图片生成",
        "content": f"图片生成完成（{len(saved_paths)} 张）",
        "meta": {"progress": 100, "success": True, "image_urls": saved_paths}
    })

    return {
        "ok": True,
        "image_urls": saved_paths,
        "count": len(saved_paths),
        "usage_tag": usage_tag,
    }


@router.get("/by-chapter", summary="按章节查询图片资源")
async def get_images_by_chapter(
        session_id: str = Query(..., description="会话ID"),
        volume_index: int = Query(..., description="卷索引"),
        chapter_index: int = Query(..., description="章索引"),
        image_type: Optional[str] = Query(None, description="可选：按图片类型过滤（generated/uploaded/material）；传入时按 章节+类型 隔离；不传则查全表所有图片"),
        engine=Depends(_get_engine),
) -> Dict[str, Any]:
    """按章节查询图片资源。

    - image_type 传入（图片生成区域传 'generated'）：按 章节usage_tag + 类型 过滤，实现章节隔离。
    - image_type 不传（视频生成区域）：查全表所有图片，不限类型不限章节，供视频素材选择。
    """
    if image_type:
        usage_tag = f"novel_{session_id}_v{volume_index}_c{chapter_index}"
        matched = engine.image_list_by_usage_and_type(usage_tag, image_type)
    else:
        matched = engine.image_list_by_type(None)
    result = []
    for img in matched:
        img_id = img.get("id")
        if not img_id:
            continue
        result.append({
            "id": img_id,
            "file_name": img.get("file_name"),
            "width": img.get("width"),
            "height": img.get("height"),
            "file_size": img.get("file_size"),
            "image_type": img.get("image_type", "uploaded"),
            "url": f"/media/image/{img.get('file_name', '')}",
        })
    return {"ok": True, "images": result}


@router.get("/capabilities", summary="图像模型能力元数据（供前端按模型动态渲染控制项）")
async def get_image_model_capabilities() -> Dict[str, Any]:
    """返回所有可用图像模型的能力元数据、默认模型与图像风格预设。

    前端据此动态渲染：模型选择器、尺寸选项、批量数范围、负面提示词可见性、风格下拉框。
    """
    vendor = config.IMAGE_DEFAULT_VENDOR
    default_model = config.IMAGE_DEFAULT_MODEL
    # 仅返回三级校验通过的模型（类型+厂商+模型）
    valid_models = LLMTypeVendorModelMapping.get_models_by_type_vendor(LLMModelType.IMAGE, vendor)
    models = {
        m: get_image_capabilities(m)
        for m in valid_models
        if m in IMAGE_MODEL_CAPABILITIES
    }
    return {
        "ok": True,
        "vendor": vendor,
        "default_model": default_model,
        "models": models,
    }


@router.post("/refine-prompt", summary="图像提示词优化（仅点击优化按钮时触发，不默认执行）")
async def refine_image_prompt_endpoint(
    payload: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
    registry: GlobalSingletonRegistry = Depends(_get_registry),
) -> Dict[str, Any]:
    """前端画面提示词左下角「优化提示词」按钮专用入口。
    调用 capability_id=image_prompt_refine 的能力，返回优化后的 prompt_text。
    结果不缓存，不创建 task（由前端保存 image_prompt_refine task 用作用户输入回溯）。
    """
    session_id = payload.get("session_id")
    user_prompt = payload.get("user_prompt")
    if not isinstance(session_id, str) or not session_id.strip():
        raise HTTPException(status_code=400, detail="缺少 session_id")
    if not isinstance(user_prompt, str) or not user_prompt.strip():
        raise HTTPException(status_code=400, detail="缺少 user_prompt")
    # 长度上限校验（SSOT: VAL_IMAGE_PROMPT_MAX_CHARS，与 generate_images 接口三端统一）
    if len(user_prompt.strip()) > va.VAL_IMAGE_PROMPT_MAX_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"图像提示词超过 {va.VAL_IMAGE_PROMPT_MAX_CHARS} 字符上限，请精简后重试",
        )
    refined = await _refine_image_prompt(
        session_id.strip(),
        user_prompt.strip(),
        engine,
        registry,
    )
    return {"ok": True, "prompt_text": refined}
