from fastapi import HTTPException

from app.core.registry.global_singleton_registry import GlobalSingletonRegistry


async def _get_engine():
    """路由层共用依赖：返回全局 Rust CognitiveEngine 实例。
    优先取已初始化值；若未初始化则懒加载兜底一次；都失败返回 503。
    """
    registry = await GlobalSingletonRegistry.get_instance()
    engine = registry.get_cognitive_engine()
    if engine is None:
        engine = registry.get_or_initialize_cognitive_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="引擎未初始化，请检查 cognitor 包是否安装")
    return engine


__all__ = ["_get_engine"]
