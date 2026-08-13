"""设备授权查询路由（**用户侧仅只读**）。

权限边界：
- 用户侧只能 GET（列表 / 计数），**不开放任何自助操作**。
  "限 3 台"的约束力来自：明线 DB + 暗线双文件 + 启动时校验，用户删不掉任何一条。
- 解绑（释放配额）是作者（你）独占的本地操作：QQ 发一份一次性脚本给用户执行，
  脚本直接调 Rust 桥接的 device_delete()（明暗双删），执行完脚本自删，
  全程不走 HTTP，用户侧没有任何接口痕迹。
  脚本位置：`prose_refiner/scripts/unbind_device.py`

校验时机：后端启动 lifespan 里完成（CognitiveEngine.initialize → ensure_authorized）。
"""

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import JSONResponse

from app.common import keys as ke
from app.routers._common import _get_engine
from app.utils.logger import LoggerManager as logger

CHINESE_NAME = "设备授权"
router = APIRouter(prefix="/api", tags=["设备授权 (明暗双线)"])


@router.get("/device-auths", summary="[用户只读] 已登记设备列表（按最后使用时间倒序）")
async def list_devices(engine=Depends(_get_engine)):
    try:
        items = engine.device_list() or []
        return JSONResponse(status_code=200, content={ke.KEY_DEVICES: items})
    except Exception as e:
        logger.exception("查询设备列表失败", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"查询设备列表失败: {e}")


@router.get("/device-auths/count", summary="[用户只读] 已登记设备数量（明暗并集复活后的实际生效值）")
async def count_devices(engine=Depends(_get_engine)):
    try:
        n = engine.device_count()
        return JSONResponse(status_code=200, content={ke.KEY_COUNT: n})
    except Exception as e:
        logger.exception("查询设备数量失败", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"查询设备数量失败: {e}")
