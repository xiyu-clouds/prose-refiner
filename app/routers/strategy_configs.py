from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from app.routers._common import _get_engine

router = APIRouter(prefix="/api/strategy-configs", tags=["策略配置 (Strategy Configs)"])


@router.get("/config/get", summary="获取策略配置（快捷单例接口，entry_id 不传则返回整体）")
async def get_strategy_config_shortcut(
    session_id: str = Query(..., description="作品会话 ID"),
    entry_id: Optional[str] = Query(None, description="可选：策略条目 ID；不传则返回整个配置实体"),
    engine=Depends(_get_engine),
) -> Any:
    return engine.strategy_config_get(session_id, entry_id)


@router.get("/", summary="查询作品策略配置列表（自动初始化默认值）")
async def list_strategy_configs(
    session_id: str = Query(..., description="作品会话 ID"),
    engine=Depends(_get_engine),
) -> Any:
    return engine.strategy_config_list(session_id)


@router.get("/{session_id}", summary="查询策略配置（单条或整体）")
async def get_strategy_config(
    session_id: str,
    entry_id: Optional[str] = Query(None, description="可选：策略条目 ID；不传则返回整个配置实体"),
    engine=Depends(_get_engine),
) -> Any:
    return engine.strategy_config_get(session_id, entry_id)
