"""健康检查路由。

返回说明：
- 200：LLM 配置就绪（TEXT_DEFAULT_VENDOR 合法）
- 503：配置不完整或引擎未成功初始化

响应体字段（均通过 common/keys SSOT 定义）：
- KEY_STATUS   → "ready" / "not_ready"
- KEY_MESSAGE  → 人类可读说明（仅 503 时返回）
- KEY_DEVICE_AUTH → 设备授权完整状态（verdict + 已用设备数 + 上限 + 当前设备 + 已登记列表 + 超限原因）
  - 该字段的**数据来源**：启动时 lifespan 中已调用 init_device_auth_on_startup()
    完成明暗双线校验并缓存结果，本路由通过 probe_device_auth() 直接读取缓存，
    不会触发新的授权检查或暗线读写。
  - 超限/正常/新注册等 verdict 完全由引擎 initialize 时的 ensure_authorized 决定。
  - probe_device_auth() 优先返回启动期缓存，降级为 30s 内存缓存。
"""

from fastapi import APIRouter
from starlette.responses import JSONResponse

from app.common import keys as ke
from app.common.llm_constants import LLMVendor
from app.config.config import config
from app.core.domain.device_auth.auth_probe import probe_device_auth

router = APIRouter(tags=["健康检查 (Health)"])


def is_service_ready() -> bool:
    return (
        hasattr(config, "TEXT_DEFAULT_VENDOR")
        and config.TEXT_DEFAULT_VENDOR in LLMVendor.all()
    )


@router.get("/api/healthz", summary="健康检查（含设备授权状态）")
async def health_check():
    ready = is_service_ready()
    body = {}
    if ready:
        body[ke.KEY_STATUS] = ke.KEY_READY
    else:
        body[ke.KEY_STATUS] = "not_ready"
        body["message"] = "TEXT_DEFAULT_VENDOR 未配置或不在合法枚举中"

    auth = probe_device_auth()
    if auth is not None:
        body[ke.KEY_DEVICE_AUTH] = auth

    return JSONResponse(status_code=200 if ready else 503, content=body)
