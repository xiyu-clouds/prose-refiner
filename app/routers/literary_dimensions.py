from typing import Any

from fastapi import APIRouter, Depends

from app.routers._common import _get_engine

router = APIRouter(prefix="/api/literary-dimensions", tags=["文学感知维度 (Literary Dimensions)"])


@router.get("/", summary="查询文学感知向量的 12 个固化维度定义")
async def list_literary_dimensions(engine=Depends(_get_engine)) -> Any:
    return engine.literary_dimensions_list()
