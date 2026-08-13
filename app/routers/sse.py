import asyncio

from fastapi import APIRouter
from starlette.responses import StreamingResponse

from app.config.config import config
from app.core.services.sse_manager import get_sse_manager
from app.utils.logger import LoggerManager as logger

CHINESE_NAME = "SSE推送"

router = APIRouter(prefix="/api", tags=["SSE 推送"])


@router.get("/sse", summary="SSE 实时推送（客户端直接接入）")
async def sse_endpoint():
    sse = get_sse_manager()
    queue = sse.register()
    logger.info("SSE 端点已连接", module_name=CHINESE_NAME)

    heartbeat = config.SSE_HEARTBEAT_INTERVAL

    async def event_generator():
        try:
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                    yield message
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
        except asyncio.CancelledError:
            logger.info("SSE 连接被取消", module_name="SSE接口")
        finally:
            sse.unregister(queue)
            logger.info("SSE 端点已断开", module_name="SSE接口")

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/sse/history", summary="获取 SSE 事件历史记录（用于跨页面恢复）")
async def get_sse_history():
    sse = get_sse_manager()
    history = sse.get_event_history()
    return {"ok": True, "history": history}