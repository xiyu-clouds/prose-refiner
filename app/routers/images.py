import io
import json
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from PIL import Image

from app.common import keys as ke
from app.config.config import config
from app.core.domain.media.cascade_cleaner import attach_ownership
from app.core.services.sse_manager import get_sse_manager
from app.routers._common import _get_engine
from app.utils.logger import LoggerManager as logger
import app.utils.cache_manager as cache_manager

router = APIRouter(prefix="/api/images", tags=["图片 (Images)"])

SUPPORTED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}
LOG_MODULE = "图片接口"


def _sync_image_count_to_global_config(engine) -> None:
    try:
        # 仅统计背景图（uploaded 横图）数量，排除素材竖图和生成图
        image_count = engine.image_count("uploaded", None)
        current_config = engine.global_config_get_full()
        if current_config.get("XINHAI_IMAGE_COUNT") != image_count:
            current_config["XINHAI_IMAGE_COUNT"] = image_count
            payload = json.dumps(current_config, ensure_ascii=False)
            engine.global_config_update(payload)
            cache_manager.invalidate(cache_manager.CK_META_CARD_CONFIG)
            logger.info(f"同步背景图数量到全局配置: XINHAI_IMAGE_COUNT={image_count}", module_name=LOG_MODULE)
    except Exception as e:
        logger.error(f"同步图片数量到全局配置失败: {e}", module_name=LOG_MODULE, exc_info=True)


@router.get("/", summary="查询全部图片资源列表")
async def list_images(
    image_type: Optional[str] = Query(None, description="可选：按图片类型过滤（uploaded背景图/material素材/generated生成）"),
    engine=Depends(_get_engine),
) -> Any:
    return engine.image_list_by_type(image_type)


@router.get("/stat/count", summary="统计图片数量")
async def count_images(
    image_type: Optional[str] = Query(None, description="可选：按图片类型过滤（uploaded背景图/material素材/generated生成）"),
    usage_tag: Optional[str] = Query(None, description="可选：按用途标签过滤（cover/scene/character 等）"),
    engine=Depends(_get_engine),
) -> Any:
    return {ke.KEY_COUNT: engine.image_count(image_type, usage_tag)}


@router.get("/available-ids", summary="获取所有可用的上传图片 ID 列表（用于前端随机选择背景图）")
async def get_available_image_ids(engine=Depends(_get_engine)) -> Any:
    images = engine.image_list_by_type("uploaded")
    ids = [int(img.get("id", 0)) for img in images if img.get("id")]
    ids.sort()
    return {"ids": ids, "count": len(ids)}


@router.get("/{id}", summary="查询单个图片资源")
async def get_image(id: str, engine=Depends(_get_engine)) -> Any:
    return engine.image_get(id)


@router.post("/", summary="创建图片资源")
async def create_image(payload: Dict[str, Any] = Body(...), engine=Depends(_get_engine)) -> Any:
    attach_ownership(payload)
    engine.image_create(json.dumps(payload, ensure_ascii=False))
    return {"ok": True}


@router.patch("/{id}", summary="更新图片资源")
async def update_image(
    id: str,
    patch: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    engine.image_update(id, json.dumps(patch, ensure_ascii=False))
    return {"ok": True}


@router.delete("/{id}", summary="删除图片资源及物理文件")
async def delete_image(id: str, engine=Depends(_get_engine)) -> Any:
    image = engine.image_get(id)
    if image:
        file_path = image.get("file_path", "")
        if file_path:
            abs_path = os.path.join(str(config.DATA_ROOT), file_path)
            if os.path.exists(abs_path):
                os.remove(abs_path)
    engine.image_delete(id)
    _sync_image_count_to_global_config(engine)
    return {"ok": True}


@router.post("/upload", summary="上传图片文件")
async def upload_image(
    file: UploadFile = File(...),
    usage_tag: Optional[str] = Query("unspecified", description="用途标签"),
    engine=Depends(_get_engine),
) -> Any:
    sse = get_sse_manager()
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()

    await sse.broadcast("upload_progress", {
        ke.KEY_TITLE: "图片上传",
        ke.KEY_CONTENT: f"开始上传: {filename}",
        ke.KEY_META: {"progress": 0, "file_name": filename}
    })

    if ext not in SUPPORTED_IMAGE_EXT:
        await sse.broadcast("upload_progress", {
            ke.KEY_TITLE: "图片上传",
            ke.KEY_CONTENT: f"不支持的格式: {ext}",
            ke.KEY_META: {"progress": 100, "success": False, "file_name": filename}
        })
        raise HTTPException(status_code=400, detail=f"不支持的图片格式: {ext}")

    content = await file.read()
    if not content:
        await sse.broadcast("upload_progress", {
            ke.KEY_TITLE: "图片上传",
            ke.KEY_CONTENT: "上传文件为空",
            ke.KEY_META: {"progress": 100, "success": False, "file_name": filename}
        })
        raise HTTPException(status_code=400, detail="上传文件为空")

    await sse.broadcast("upload_progress", {
        ke.KEY_TITLE: "图片上传",
        ke.KEY_CONTENT: "解析图片中...",
        ke.KEY_META: {"progress": 20, "file_name": filename}
    })

    try:
        img = Image.open(io.BytesIO(content))
        img = img.convert("RGB")
        width, height = img.size
    except Exception as e:
        await sse.broadcast("upload_progress", {
            ke.KEY_TITLE: "图片上传",
            ke.KEY_CONTENT: f"图片解析失败: {str(e)}",
            ke.KEY_META: {"progress": 100, "success": False, "file_name": filename}
        })
        raise HTTPException(status_code=400, detail=f"图片解析失败: {str(e)}")

    await sse.broadcast("upload_progress", {
        ke.KEY_TITLE: "图片上传",
        ke.KEY_CONTENT: "写入数据库...",
        ke.KEY_META: {"progress": 50, "file_name": filename, "width": width, "height": height}
    })

    placeholder = f"_pending_{os.getpid()}_{hash(content) % 1000000}.png"
    # 竖图（宽<高）标记为素材 material，用于 9:16 视频；横图标记为背景图 uploaded
    image_type = "material" if width < height else "uploaded"
    payload = {
        "file_name": placeholder,
        "file_path": f"image/{placeholder}",
        "file_size": len(content),
        "width": width,
        "height": height,
        "image_type": image_type,
        "usage_tag": usage_tag,
    }
    attach_ownership(payload)
    try:
        new_id = engine.image_create(json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        logger.error(f"图片数据库写入失败: {e}", module_name=LOG_MODULE, exc_info=True)
        await sse.broadcast("upload_progress", {
            ke.KEY_TITLE: "图片上传",
            ke.KEY_CONTENT: f"数据库写入失败: {str(e)}",
            ke.KEY_META: {"progress": 100, "success": False, "file_name": filename}
        })
        raise HTTPException(status_code=500, detail=f"数据库写入失败: {str(e)}")

    if not new_id:
        await sse.broadcast("upload_progress", {
            ke.KEY_TITLE: "图片上传",
            ke.KEY_CONTENT: "引擎未返回新图片 ID",
            ke.KEY_META: {"progress": 100, "success": False, "file_name": filename}
        })
        raise HTTPException(status_code=500, detail="引擎未返回新图片 ID，请确认引擎已重新编译")

    await sse.broadcast("upload_progress", {
        ke.KEY_TITLE: "图片上传",
        ke.KEY_CONTENT: "保存图片文件...",
        ke.KEY_META: {"progress": 70, "file_name": filename, "id": new_id}
    })

    final_name = f"{new_id}.png"
    final_path = os.path.join(str(config.IMAGE_DIR), final_name)
    try:
        img.save(final_path, "PNG")
    except Exception as e:
        try:
            engine.image_delete(str(new_id))
        except Exception:
            pass
        logger.error(f"图片保存失败: {e}", module_name=LOG_MODULE, exc_info=True)
        await sse.broadcast("upload_progress", {
            ke.KEY_TITLE: "图片上传",
            ke.KEY_CONTENT: f"图片保存失败: {str(e)}",
            ke.KEY_META: {"progress": 100, "success": False, "file_name": filename}
        })
        raise HTTPException(status_code=500, detail=f"图片保存失败: {str(e)}")

    await sse.broadcast("upload_progress", {
        ke.KEY_TITLE: "图片上传",
        ke.KEY_CONTENT: "更新数据库记录...",
        ke.KEY_META: {"progress": 90, "file_name": filename, "id": new_id}
    })

    update_payload = {
        "file_name": final_name,
        "file_path": f"image/{final_name}",
    }
    try:
        engine.image_update(str(new_id), json.dumps(update_payload, ensure_ascii=False))
    except Exception as e:
        try:
            if os.path.exists(final_path):
                os.remove(final_path)
            engine.image_delete(str(new_id))
        except Exception:
            pass
        logger.error(f"图片数据库回填失败: {e}", module_name=LOG_MODULE, exc_info=True)
        await sse.broadcast("upload_progress", {
            ke.KEY_TITLE: "图片上传",
            ke.KEY_CONTENT: f"数据库更新失败: {str(e)}",
            ke.KEY_META: {"progress": 100, "success": False, "file_name": filename}
        })
        raise HTTPException(status_code=500, detail=f"数据库更新失败: {str(e)}")

    _sync_image_count_to_global_config(engine)

    await sse.broadcast("upload_progress", {
        ke.KEY_TITLE: "图片上传",
        ke.KEY_CONTENT: f"上传成功: {final_name} ({width}x{height})",
        ke.KEY_META: {"progress": 100, "success": True, "file_name": final_name, "id": new_id, "width": width, "height": height}
    })

    logger.info(f"图片上传成功: id={new_id}, file_name={final_name}", module_name=LOG_MODULE)

    return {"ok": True, "id": new_id, "file_name": final_name, "file_path": f"/media/image/{final_name}"}


@router.delete("/{id}/file", summary="删除图片资源及物理文件")
async def delete_image_file(id: str, engine=Depends(_get_engine)) -> Any:
    image = engine.image_get(id)
    if not image:
        raise HTTPException(status_code=404, detail="图片不存在")

    file_path = image.get("file_path", "")
    if file_path:
        abs_path = os.path.join(str(config.DATA_ROOT), file_path)
        if os.path.exists(abs_path):
            os.remove(abs_path)

    engine.image_delete(id)
    _sync_image_count_to_global_config(engine)
    return {"ok": True}
