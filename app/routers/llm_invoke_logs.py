import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.routers._common import _get_engine
from app.utils.logger import LoggerManager as logger

LOG_MODULE = "大模型调用日志接口"

router = APIRouter(prefix="/api/llm-invoke-logs", tags=["大模型调用日志 (LLM Invoke Logs)"])


@router.get("/", summary="查询大模型调用日志（按作品隔离）")
async def list_llm_invoke_logs(
    session_id: str = Query(..., description="作品会话 ID（必填）"),
    task_id: Optional[str] = Query(None, description="可选：按任务 ID 进一步过滤"),
    capability_id: Optional[str] = Query(None, description="可选：按能力 ID 进一步过滤"),
    engine=Depends(_get_engine),
) -> Any:
    summary = f"session_id={session_id!r}, task_id={task_id!r}, capability_id={capability_id!r}"
    try:
        logger.info(f"查询 LLM 调用日志 {summary}", module_name=LOG_MODULE)
        data = engine.llm_invoke_log_list(session_id, task_id, capability_id)
        count = len(data) if isinstance(data, (list, tuple)) else -1
        logger.info(
            f"查询 LLM 调用日志成功 {summary}，共 {count} 条（prompt/response 已按原始存储读取，调用方应自行遮蔽敏感内容）",
            module_name=LOG_MODULE,
        )
        return data
    except Exception as e:
        logger.error(
            f"查询 LLM 调用日志失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="查询 LLM 调用日志失败，请查看后端日志获取详细信息")


@router.get("/stat/token-cost", summary="统计作品累计 token 消耗")
async def sum_llm_token_cost(
    session_id: str = Query(..., description="作品会话 ID"),
    task_id: Optional[str] = Query(None, description="可选：仅统计某任务内累计消耗"),
    engine=Depends(_get_engine),
) -> Any:
    summary = f"session_id={session_id!r}, task_id={task_id!r}"
    try:
        logger.info(f"统计 token 消耗 {summary}", module_name=LOG_MODULE)
        total = engine.llm_invoke_log_sum_token_cost(session_id, task_id)
        logger.info(f"统计 token 消耗成功 {summary} total={total}", module_name=LOG_MODULE)
        return {"total_cost": total}
    except Exception as e:
        logger.error(
            f"统计 token 消耗失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="统计 token 消耗失败，请查看后端日志获取详细信息")


@router.get("/{id}", summary="查询单条大模型调用日志")
async def get_llm_invoke_log(id: str, engine=Depends(_get_engine)) -> Any:
    summary = f"id={id!r}"
    try:
        logger.info(f"查询单条 LLM 调用日志 {summary}", module_name=LOG_MODULE)
        data = engine.llm_invoke_log_get(id)
        token_cost = -1
        caps_id = None
        if isinstance(data, dict):
            token_cost = data.get("token_cost") if isinstance(data.get("token_cost"), int) else -1
            caps_id = data.get("capability_id")
        logger.info(
            f"查询单条 LLM 调用日志成功 {summary} capability_id={caps_id!r} token_cost={token_cost}",
            module_name=LOG_MODULE,
        )
        return data
    except Exception as e:
        logger.error(
            f"查询单条 LLM 调用日志失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="查询 LLM 调用日志失败，请查看后端日志获取详细信息")


@router.post("/", summary="创建大模型调用日志")
async def create_llm_invoke_log(
    payload: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    sid = payload.get("session_id")
    caps_id = payload.get("capability_id")
    task_id = payload.get("task_id")
    token_cost = payload.get("token_cost")
    prompt_len = len(payload.get("prompt")) if isinstance(payload.get("prompt"), str) else -1
    resp_len = len(payload.get("response")) if isinstance(payload.get("response"), str) else -1
    error_preview: Optional[str] = None
    if isinstance(payload.get("error"), str):
        error_preview = payload["error"]
        if len(error_preview) > 120:
            error_preview = error_preview[:120] + f"...({len(payload['error'])}字符)"
    summary = (
        f"session_id={sid!r}, capability_id={caps_id!r}, task_id={task_id!r}, "
        f"token_cost={token_cost}, prompt_len={prompt_len}, response_len={resp_len}"
        + (f", error={error_preview!r}" if error_preview else "")
    )
    try:
        logger.info(f"创建 LLM 调用日志 {summary}", module_name=LOG_MODULE)
        engine.llm_invoke_log_create(json.dumps(payload, ensure_ascii=False))
        logger.info(f"创建 LLM 调用日志成功 {summary}", module_name=LOG_MODULE)
        return {"ok": True}
    except Exception as e:
        logger.error(
            f"创建 LLM 调用日志失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="创建 LLM 调用日志失败，请查看后端日志获取详细信息")


@router.patch("/{id}", summary="更新大模型调用日志")
async def update_llm_invoke_log(
    id: str,
    patch: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    keys = sorted(list(patch.keys()))
    token_cost = patch.get("token_cost") if "token_cost" in patch else None
    summary = f"id={id!r} updated_keys={keys}"
    if token_cost is not None:
        summary += f" token_cost={token_cost}"
    try:
        logger.info(f"更新 LLM 调用日志 {summary}", module_name=LOG_MODULE)
        engine.llm_invoke_log_update(id, json.dumps(patch, ensure_ascii=False))
        logger.info(f"更新 LLM 调用日志成功 {summary}", module_name=LOG_MODULE)
        return {"ok": True}
    except Exception as e:
        logger.error(
            f"更新 LLM 调用日志失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="更新 LLM 调用日志失败，请查看后端日志获取详细信息")


@router.delete("/{id}", summary="删除大模型调用日志")
async def delete_llm_invoke_log(id: str, engine=Depends(_get_engine)) -> Any:
    summary = f"id={id!r}"
    try:
        logger.info(f"删除 LLM 调用日志 {summary}", module_name=LOG_MODULE)
        engine.llm_invoke_log_delete(id)
        logger.info(f"删除 LLM 调用日志成功 {summary}", module_name=LOG_MODULE)
        return {"ok": True}
    except Exception as e:
        logger.error(
            f"删除 LLM 调用日志失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="删除 LLM 调用日志失败，请查看后端日志获取详细信息")
