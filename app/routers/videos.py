import json
import os
from typing import Any, Dict, Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from app.common import keys as ke
from app.config.config import config
from app.core.domain.media.cascade_cleaner import attach_ownership
from app.core.video_synthesis import VideoSynthError, generate_video_for_chapter
from app.routers._common import _get_engine
from app.utils.logger import LoggerManager as logger

router = APIRouter(prefix="/api/videos", tags=["视频 (Videos)"])


# ============================================================
# 基础 CRUD
# ============================================================

@router.get("/", summary="查询全部视频资源列表")
async def list_videos(engine=Depends(_get_engine)) -> Any:
    return engine.video_list()


@router.get("/stat/count", summary="统计视频数量")
async def count_videos(
        file_format: Optional[str] = Query(None, description="可选：按文件格式过滤（mp4等）"),
        video_type: Optional[str] = Query(None, description="可选：按视频类型过滤（generated/uploaded）"),
        engine=Depends(_get_engine),
) -> Any:
    return {ke.KEY_COUNT: engine.video_count(file_format, video_type)}


# ⚠️ 固定路径端点必须定义在 /{id} 之前，否则 FastAPI 会把固定路径当作路径参数匹配
@router.get("/by-chapter", summary="按章节查询已生成视频")
async def get_video_by_chapter(
        session_id: str = Query(..., description="会话ID"),
        volume_index: int = Query(..., description="卷索引"),
        chapter_index: int = Query(..., description="章索引"),
        engine=Depends(_get_engine),
) -> Any:
    """按章节查询已生成视频（一篇正文一条视频）。"""
    title = f"{session_id} 第{volume_index + 1}卷第{chapter_index + 1}章"
    all_videos = engine.video_list()
    for video in all_videos:
        if video.get("video_type") == "generated" and video.get("title") == title:
            return {
                "ok": True,
                "video_url": f"/media/video/{video['file_name']}",
                "file_name": video["file_name"],
                "duration": video.get("duration", 0),
                "width": video.get("width"),
                "height": video.get("height"),
                "file_size": video.get("file_size", 0),
            }
    return {"ok": False}


@router.get("/{id}", summary="查询单个视频资源")
async def get_video(id: str, engine=Depends(_get_engine)) -> Any:
    return engine.video_get(id)


@router.post("/", summary="创建视频资源")
async def create_video(payload: Dict[str, Any] = Body(...), engine=Depends(_get_engine)) -> Any:
    attach_ownership(payload)
    engine.video_create(json.dumps(payload, ensure_ascii=False))
    return {"ok": True}


@router.post("/generate", summary="生成视频（音频 + 图片 + 组件参数）")
async def generate_video(
        payload: Dict[str, Any] = Body(...),
        engine=Depends(_get_engine),
) -> Any:
    """
    使用已合成的 TTS 音频 + 用户选定的图片，基于 ffmpeg 组装视频。

    请求体 (JSON):
        - session_id: 会话ID
        - volume_index: 卷索引
        - chapter_index: 章索引
        - image_ids:  图片 ID 列表（通过 /api/images/ 查询到）
        - video_size: auto | 9:16 | 16:9 | 1:1 | 4:3 | 3:4 | "1080x1920"
        - fit_mode:   contain | cover
        - quality:    low | medium | high | ultra
        - fps:        默认 25
        - image_interval: 每张图显示秒数，默认 8
        - image_order:    sequential | shuffle
        - shuffle_seed:   shuffle 随机种子，默认 42
        - effects.transition.enabled / type / duration
        - effects.pencil_sketch.enabled / apply_to / direction /
          transition_duration / blur_size / intensity / sharpen
    """
    try:
        return await generate_video_for_chapter(payload, engine)
    except ValueError as e:
        # ValueError 在业务层有两类来源：
        #   A) generator.py 参数校验（session_id 空、图片列表空、音频不存在等）→ 400
        #   B) 内部管道/IO 错误冒泡的 ValueError（如 "flush of closed file"）→ 500
        # 这里通过关键字区分，并把堆栈完整打出来，避免下次再看到"只有一行 flush of closed file
        # 完全没日志"的窘境。
        import traceback as _tb
        msg = str(e)
        _param_hint_keywords = ("不能为空", "不存在", "解析失败", "无法识别", "非法", "缺少", "必须")
        is_param_error = any(k in msg for k in _param_hint_keywords)
        if is_param_error:
            # A) 400 参数校验
            logger.warning(
                f"视频生成参数校验失败（转 HTTP 400）: {msg}\n{_tb.format_exc()}",
                module_name="视频路由"
            )
            raise HTTPException(status_code=400, detail=msg)
        else:
            # B) 非预期 ValueError：一定是管道/IO/传输层出问题，必须打 ERROR + 完整栈 + 转 500
            logger.error(
                f"视频生成链路抛非预期 ValueError（转 HTTP 500）: {type(e).__name__}: {msg}\n"
                f"{_tb.format_exc()}",
                module_name="视频路由",
                exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=f"视频生成失败（内部管道异常）：{msg}"
            )
    except VideoSynthError as e:
        logger.error(f"视频合成失败: {e}", module_name="视频路由", exc_info=True)
        raise HTTPException(status_code=500, detail=f"视频合成失败: {e}")
    except Exception as e:
        logger.error(f"视频生成异常: {e}", module_name="视频路由", exc_info=True)
        raise HTTPException(status_code=500, detail=f"视频生成失败: {e}")


@router.put("/{id}", summary="更新视频资源")
async def update_video(
        id: str,
        patch: Dict[str, Any] = Body(...),
        engine=Depends(_get_engine),
) -> Any:
    engine.video_update(id, json.dumps(patch, ensure_ascii=False))
    return {"ok": True}


@router.delete("/{id}", summary="删除视频资源及物理文件")
async def delete_video(id: str, engine=Depends(_get_engine)) -> Any:
    video = engine.video_get(id)
    if video:
        file_path = video.get("file_path", "")
        if file_path:
            abs_path = os.path.join(str(config.DATA_ROOT), file_path)
            if os.path.exists(abs_path):
                try:
                    os.remove(abs_path)
                except OSError:
                    pass
    engine.video_delete(id)
    return {"ok": True}


@router.delete("/{id}/file", summary="仅删除视频物理文件（保留记录）")
async def delete_video_file(id: str, engine=Depends(_get_engine)) -> Any:
    video = engine.video_get(id)
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")
    file_path = video.get("file_path", "")
    if not file_path:
        return {"ok": True, "deleted": False, "reason": "无关联文件"}
    abs_path = os.path.join(str(config.DATA_ROOT), file_path)
    deleted = False
    if os.path.exists(abs_path):
        try:
            os.remove(abs_path)
            deleted = True
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"删除文件失败: {e}")
    return {"ok": True, "deleted": deleted}
