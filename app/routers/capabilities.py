import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from app.routers._common import _get_engine
from app.core.domain.capabilities.core import (
    LOG_MODULE,
    logger,
    _get_registry,
    _parse_task_id,
    _invoke_capability_single,
    _resolve_capability,
    _load_compiled_prompt,
    _build_executor,
    build_preview_injection,
)

router = APIRouter(prefix="/api/capabilities", tags=["能力执行 (Capabilities)"])


@router.post("/invoke", summary="调用能力执行（单次；多文件并发请使用 /invoke-batch）")
async def invoke_capability(
        payload: Dict[str, Any] = Body(...),
        engine=Depends(_get_engine),
        registry=Depends(_get_registry),
) -> Any:
    session_id: Optional[str] = payload.get("session_id")
    capability_id: Optional[str] = payload.get("capability_id")
    variables: Dict[str, Any] = payload.get("variables") or {}
    task_id: Optional[int] = _parse_task_id(payload)
    return await _invoke_capability_single(
        session_id or "",
        capability_id or "",
        variables,
        engine,
        registry,
        task_id=task_id,
    )


@router.post("/preview-injection", summary="注入预览：拿全量候选+自动选中分区+匹配度，供用户决策最终注入数据")
async def preview_injection_endpoint(
        payload: Dict[str, Any] = Body(...),
        engine=Depends(_get_engine),
) -> Any:
    session_id: Optional[str] = payload.get("session_id")
    capability_id: Optional[str] = payload.get("capability_id")
    variables: Dict[str, Any] = payload.get("variables") or {}
    summary = (
        f"session_id={session_id!r}, capability_id={capability_id!r}, "
        f"variables_keys={sorted(list(variables.keys())) if isinstance(variables, dict) else []}"
    )

    if not session_id or not isinstance(session_id, str) or not session_id.strip():
        logger.warning(
            f"[预览注入参数非法] {summary}：session_id 必须为非空字符串",
            module_name=LOG_MODULE,
        )
        raise HTTPException(status_code=400, detail="session_id 必须为非空字符串")
    if not capability_id or not isinstance(capability_id, str) or not capability_id.strip():
        logger.warning(
            f"[预览注入参数非法] {summary}：capability_id 必须为非空字符串",
            module_name=LOG_MODULE,
        )
        raise HTTPException(status_code=400, detail="capability_id 必须为非空字符串")
    if not isinstance(variables, dict):
        logger.warning(
            f"[预览注入参数非法] {summary}：variables 必须为对象",
            module_name=LOG_MODULE,
        )
        raise HTTPException(status_code=400, detail="variables 必须为对象")

    return build_preview_injection(session_id, capability_id, variables, engine)


@router.post("/invoke-batch", summary="并发调用同一能力多次（如每个文件一个 source_text 并发提取）")
async def invoke_capability_batch(
        payload: Dict[str, Any] = Body(...),
        engine=Depends(_get_engine),
        registry=Depends(_get_registry),
) -> Any:
    session_id: Optional[str] = payload.get("session_id")
    capability_id: Optional[str] = payload.get("capability_id")
    batch_raw: Any = payload.get("batch")
    task_id: Optional[int] = _parse_task_id(payload)
    if not isinstance(batch_raw, list):
        raise HTTPException(status_code=400, detail="batch 必须为数组，每项是一个 variables 对象")
    batch: List[Dict[str, Any]] = [
        (item if isinstance(item, dict) else {}) for item in batch_raw
    ]
    summary_batch = (
        f"session_id={session_id!r}, capability_id={capability_id!r}, "
        f"batch_size={len(batch)}, task_id={task_id!r}"
    )
    if not session_id or not capability_id:
        raise HTTPException(status_code=400, detail="session_id 和 capability_id 均为必填")
    if len(batch) == 0:
        raise HTTPException(status_code=400, detail="batch 为空")

    logger.info(
        f"开始能力并发执行 {summary_batch}",
        module_name=LOG_MODULE,
    )

    # 预加载：能力配置、compiled prompt、executor 全部在并发前只做一次
    single_summary = f"session_id={session_id!r}, capability_id={capability_id!r}, variables_keys=[]"
    cap = await _resolve_capability(session_id, capability_id, engine, single_summary)
    compiled_prompt = _load_compiled_prompt(session_id, capability_id, engine, single_summary)
    executor, expect_json = await _build_executor(cap, registry, single_summary)

    # ---------- 并发执行每个 variables 项 ----------
    # 注意：并发任务内部会写 session_memory 和 llm_invoke_log；SQLite 锁已由互斥保护
    # 若调用方顶层传了 task_id，则所有子调用共享同一个 task_id（适用于「同一任务内多次 LLM 调用」场景）；
    # 否则 extract_session_memory 会自己预创建独立 task。
    tasks = [
        _invoke_capability_single(
            session_id,
            capability_id,
            variables,
            engine,
            registry,
            task_id=task_id,
            pre_resolved_cap=cap,
            pre_compiled_prompt=compiled_prompt,
            shared_executor=executor,
            shared_expect_json=expect_json,
        )
        for variables in batch
    ]

    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    total_token = 0
    total_memories_count = 0
    total_memories_created = 0

    done, pending = await asyncio.wait(
        [asyncio.create_task(t) for t in tasks],
        return_when=asyncio.ALL_COMPLETED,
    )
    del pending
    for idx, fut in enumerate(done):
        try:
            res = fut.result()
            results.append(res)
            total_token += int(res.get("token_cost") or 0)
            inner = res.get("result") if isinstance(res, dict) else None
            if isinstance(inner, dict):
                total_memories_count += int(inner.get("memories_count") or 0)
                total_memories_created += int(inner.get("memories_created") or 0)
        except HTTPException as e:
            errors.append({"index": idx, "status": e.status_code, "detail": e.detail})
        except (ValueError, TypeError) as e:
            errors.append({"index": idx, "status": 500, "detail": f"{type(e).__name__}: {e}"})

    success_cnt = len(results)
    fail_cnt = len(errors)
    logger.info(
        f"能力并发执行完成 {summary_batch}: success={success_cnt}, fail={fail_cnt}, "
        f"token_total={total_token}, memories_created_total={total_memories_created}",
        module_name=LOG_MODULE,
    )

    return {
        "ok": True,
        "session_id": session_id,
        "capability_id": capability_id,
        "batch_size": len(batch),
        "task_id": task_id,
        "success": success_cnt,
        "failed": fail_cnt,
        "errors": errors[:10],
        "results": results,
        "aggregation": {
            "token_total": total_token,
            "memories_count_total": total_memories_count,
            "memories_created_total": total_memories_created,
        },
    }
