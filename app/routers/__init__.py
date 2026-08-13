"""路由器入口 —— 24 个路由模块：7 个基础服务（pages/healthz/meta/files/sse/unsplash/pexels）+ 17 个引擎控制器。"""

from importlib import import_module

from fastapi import FastAPI

_ROUTER_MODULES = [
    "pages",
    "healthz",
    "meta",
    "files",
    "sse",
    "unsplash",
    "pexels",
    "works",
    "tasks",
    "session_memories",
    "strategy_configs",
    "text_correction_configs",
    "audios",
    "image_generation",
    "capabilities",
    "capability_configs",
    "dao_configs",
    "global_configs",
    "images",
    "label_configs",
    "label_selections",
    "literary_dimensions",
    "llm_invoke_logs",
    "lyrics",
    "punctuation_configs",
    "quotes",
    "semantic_vocabularies",
    "translations",
    "videos",
    "device_auths",
]

__all__ = [*_ROUTER_MODULES, "register_all_routers"]


def register_all_routers(app: FastAPI) -> None:
    for name in _ROUTER_MODULES:
        mod = import_module(f"app.routers.{name}")
        router = getattr(mod, "router", None)
        if router is None:
            raise RuntimeError(
                f"[routers] 模块 app.routers.{name} 缺少 `router = APIRouter()` 声明"
            )
        app.include_router(router)
