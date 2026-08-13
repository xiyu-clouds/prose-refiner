"""视频生成编排：解析资源 → 清理旧视频 → 组装配置 → 合成 → 解析元数据 → 入库。

路由层仅负责参数解析与统一异常响应，编排逻辑集中于此。
core 层抛业务异常（ValueError / VideoSynthError），由路由层统一转 HTTPException。
"""
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from app.common import keys as ke
from app.config.config import config
from app.core.domain.media.cascade_cleaner import attach_ownership
from app.core.services.sse_manager import get_sse_manager
from .media_probe import MediaProbeError, get_audio_duration, run_ffprobe
from .synthesizer import synthesize_video_async
from app.utils.logger import LoggerManager as logger

_MODULE_NAME = "视频生成编排"


def _pick(d: Dict, keys: List[str], default=None):
    """扁平/嵌套字段兼容取值。"""
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _resolve_image_paths(image_ids: List[int], engine) -> List[str]:
    """根据前端传入的图片 ID 列表，通过引擎查 file_path，返回绝对路径列表。

    若 file_path 以 audio/、video/、image/ 开头，则与 DATA_ROOT 拼接；
    否则按资源目录规则补全前缀 image/。
    """
    paths: List[str] = []
    for iid in image_ids:
        img = engine.image_get(str(iid))
        if not img:
            continue
        fp = img.get("file_path") or ""
        if not fp:
            fn = img.get("file_name") or ""
            if fn:
                fp = f"image/{fn}"
            else:
                continue
        if os.path.isabs(fp):
            paths.append(fp)
        else:
            paths.append(os.path.join(str(config.DATA_ROOT), fp))
    return paths


def _resolve_audio_path(session_id: str, volume_index: int, chapter_index: int, engine) -> Optional[str]:
    """按章节查询 TTS 音频，返回绝对路径；找不到返回 None。"""
    title = f"{session_id} 第{volume_index + 1}卷第{chapter_index + 1}章"
    all_audios = engine.audio_list()
    for audio in all_audios:
        if audio.get("audio_type") == "tts" and audio.get("title") == title:
            fp = audio.get("file_path") or ""
            if not fp:
                continue
            if os.path.isabs(fp):
                return fp
            return os.path.join(str(config.DATA_ROOT), fp)
    return None


def _collect_chapter_images(session_id: str, volume_index: int, chapter_index: int, engine) -> List[int]:
    """前端未勾选 image_ids 时，按章节 usage_tag 默认取本章节所有已生成图片。"""
    usage_tag = f"novel_{session_id}_v{volume_index}_c{chapter_index}"
    image_ids: List[int] = []
    try:
        all_imgs = engine.image_list_by_type("generated")
        for img in all_imgs:
            if img.get("usage_tag") == usage_tag:
                img_id = img.get("id")
                if isinstance(img_id, (int, float)) and not image_ids.count(int(img_id)):
                    image_ids.append(int(img_id))
    except Exception:
        pass
    return image_ids


def _build_synth_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    """组装合成模块配置（扁平/嵌套字段兼容归一化）。

    注：fit_mode 强制使用 cover（等比裁剪填充），确保视频无黑边。
    编码统一使用 CPU libx264，不再依赖 GPU 资源。
    """
    effects = payload.get("effects") or {}
    return {
        "video_size": _pick(payload, ["video_size"], "auto"),
        "fit_mode": "cover",  # 强制使用 cover 模式，避免黑边
        "quality": _pick(payload, ["quality"], "high"),
        "encoder": _pick(payload, ["encoder"], "auto"),
        "fps": int(_pick(payload, ["fps"], 25)),
        "image_interval": float(_pick(payload, ["image_interval"], 8)),
        "image_order": _pick(payload, ["image_order"], "sequential"),
        "shuffle_seed": int(_pick(payload, ["shuffle_seed"], 42)),
        "effects": {
            "transition": {
                "enabled": bool(_pick(effects.get("transition") or {}, ["enabled"], False)),
                "type": str(_pick(effects.get("transition") or {}, ["type"], "fade")),
                "duration": float(_pick(effects.get("transition") or {}, ["duration"], 0.8)),
            },
            "pencil_sketch": {
                "enabled": bool(_pick(effects.get("pencil_sketch") or {}, ["enabled"], False)),
                # apply_to 为空时默认应用到全部图片
                "apply_to": [int(x) for x in (_pick(effects.get("pencil_sketch") or {}, ["apply_to"], []) or [])],
                "direction": str(_pick(effects.get("pencil_sketch") or {}, ["direction"], "sketch_to_real")),
                "transition_duration": float(_pick(effects.get("pencil_sketch") or {}, ["transition_duration"], 5)),
                "blur_size": int(_pick(effects.get("pencil_sketch") or {}, ["blur_size"], 15)),
                "intensity": float(_pick(effects.get("pencil_sketch") or {}, ["intensity"], 0.80)),
                "sharpen": float(_pick(effects.get("pencil_sketch") or {}, ["sharpen"], 0.65)),
            },
        },
    }


def _overwrite_existing_video(title: str, engine) -> None:
    """覆盖同标题旧视频（删除物理文件 + 删除记录）。"""
    all_videos = engine.video_list()
    for video in all_videos:
        if video.get("video_type") == "generated" and video.get("title") == title:
            old_file_name = video.get("file_name", "")
            if old_file_name:
                old_file_path = os.path.join(str(config.VIDEO_DIR), old_file_name)
                if os.path.exists(old_file_path):
                    try:
                        os.remove(old_file_path)
                    except OSError:
                        pass
            engine.video_delete(str(video["id"]))
            logger.info(
                f"已覆盖旧视频: id={video['id']}, file={old_file_name}",
                module_name=_MODULE_NAME
            )
            break


def _probe_output_metadata(out: str) -> Tuple[float, Optional[int], Optional[int]]:
    """探测输出视频元数据（时长/宽高）。失败返回 (0.0, None, None) 不阻塞流程。"""
    duration = 0.0
    width: Optional[int] = None
    height: Optional[int] = None
    try:
        duration = get_audio_duration(Path(out))
        out_wh = run_ffprobe([
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0", str(out),
        ])
        parts = out_wh.split(",")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            width = int(parts[0])
            height = int(parts[1])
    except (MediaProbeError, ValueError):
        # 元数据解析失败不阻塞整体流程，入库默认空值
        pass
    return duration, width, height


def _make_progress_cb(sse) -> Callable[[int, str], None]:
    """构造同步 progress_cb：用 run_coroutine_threadsafe 投递 SSE 广播回事件循环。

    synthesize_video_async 的 progress_cb 在 asyncio.to_thread 线程内同步调用，
    不能直接 await，故通过 run_coroutine_threadsafe 投递回事件循环。

    注意（以实际逻辑支撑）：广播失败（如 SSE 连接已被关闭导致的
    "flush of closed file"、客户端断连）只影响进度通知展示，不影响
    视频合成结果，因此这里统一吞掉异常，避免异常通过
    run_coroutine_threadsafe 的 Future 被 loop exception handler
    打印"未捕获异常"的噪音日志。
    """
    async def _broadcast(pct: int, msg: str):
        try:
            await sse.broadcast("task_progress", {
                "title": "视频生成",
                "content": msg,
                "meta": {"progress": pct}
            })
        except Exception:
            # 通知层失败永远不冒泡到业务
            pass

    def sync_progress_cb(pct: int, msg: str):
        try:
            loop = asyncio.get_running_loop()
            fut = asyncio.run_coroutine_threadsafe(_broadcast(pct, msg), loop)
            # 不让 Future 的未捕获异常跑到 event loop handler
            def _log_and_suppress(_f):
                try:
                    _f.result()
                except Exception:
                    pass
            fut.add_done_callback(_log_and_suppress)
        except RuntimeError:
            # 非运行中的 loop（比如 shutdown 阶段），静默跳过即可
            pass

    return sync_progress_cb


async def _fire_and_forget_progress(sse, payload: Dict[str, Any]) -> None:
    """最佳努力广播 SSE 进度，永不冒泡异常。

    语义（基于实际链路，不靠猜测）：SSE broadcast 只是把消息放进队列，
    正常情况下不会失败；但如果广播期间或后续 StreamResponse 写入传输
    时因为客户端已经断连而触发"flush of closed file"等 IO 异常，这些
    异常只影响"通知界面刷新"，不应该影响业务主流程。这里统一吞掉，
    避免视频生成成功却因通知失败而被当成 400/500 返回给前端。
    """
    try:
        await sse.broadcast("task_progress", payload)
    except Exception:
        pass


async def generate_video_for_chapter(payload: Dict[str, Any], engine) -> Dict[str, Any]:
    """视频生成编排：解析资源 → 清理旧视频 → 组装配置 → 合成 → 解析元数据 → 入库。

    Args:
        payload: 请求体（session_id / volume_index / chapter_index / image_ids / 组件参数）。
        engine: Rust 桥接引擎实例。

    Returns:
        生成结果（ok / video_url / file_name / duration / file_size / width / height）。

    Raises:
        ValueError: 参数或资源校验失败（session_id 空、图片列表空、TTS 音频不存在、图片路径解析失败）。
        VideoSynthError: ffmpeg 合成失败。
    """
    sse = get_sse_manager()

    session_id = str(payload.get("session_id", ""))
    volume_index = int(payload.get("volume_index", 0))
    chapter_index = int(payload.get("chapter_index", 0))
    image_ids: List[int] = [int(x) for x in (payload.get("image_ids") or [])]

    if not session_id:
        raise ValueError("session_id 不能为空")

    # 前端未勾选 image_ids 时，按章节 usage_tag 默认取本章节所有已生成图片
    if not image_ids:
        image_ids = _collect_chapter_images(session_id, volume_index, chapter_index, engine)
    if not image_ids:
        raise ValueError("图片列表不能为空，请先生成或勾选至少一张图片")

    # ---- 1. 解析音频（按章节匹配 TTS） ----
    audio_path = _resolve_audio_path(session_id, volume_index, chapter_index, engine)
    if not audio_path or not os.path.exists(audio_path):
        raise ValueError("对应章节的 TTS 音频不存在，请先生成音频")

    # ---- 2. 解析图片路径 ----
    image_paths = _resolve_image_paths(image_ids, engine)
    if not image_paths:
        raise ValueError("图片路径解析失败，请检查 image_ids")

    # ---- 3. 组装合成模块配置（提前组装，用于日志） ----
    synth_config = _build_synth_config(payload)

    logger.info(
        f"开始视频合成: session={session_id}, volume={volume_index}, "
        f"chapter={chapter_index}, images={len(image_paths)}, "
        f"image_order={synth_config.get('image_order')}, "
        f"shuffle_seed={synth_config.get('shuffle_seed')}, "
        f"pencil_sketch={synth_config['effects']['pencil_sketch']['enabled']}",
        module_name=_MODULE_NAME
    )

    title = f"{session_id} 第{volume_index + 1}卷第{chapter_index + 1}章"

    # ---- 4. 覆盖旧视频 ----
    _overwrite_existing_video(title, engine)

    await _fire_and_forget_progress(sse, {
        "title": "视频生成",
        "content": f"开始合成（{len(image_paths)} 张图，{synth_config['quality']} 质量）",
        "meta": {"progress": 5}
    })

    # ---- 5. 输出文件 ----
    timestamp = int(time.time())
    output_filename = f"{session_id}_v{volume_index}_c{chapter_index}_{timestamp}.mp4"
    output_path = os.path.join(str(config.VIDEO_DIR), output_filename)
    os.makedirs(str(config.VIDEO_DIR), exist_ok=True)

    # ---- 6. 心跳任务：合成期间每 5 秒推送一次进度，避免长时间无反馈 ----
    import threading
    heartbeat_stop = threading.Event()
    main_loop = asyncio.get_running_loop()  # 主线程事件循环，传给心跳线程

    def _heartbeat():
        """心跳线程：合成期间定期推送 SSE，让前端知道仍在处理。"""
        cycle = 0
        while not heartbeat_stop.wait(5.0):
            cycle += 1
            fut = asyncio.run_coroutine_threadsafe(
                sse.broadcast("task_progress", {
                    "title": "视频生成",
                    "content": f"正在合成视频...（已等待 {cycle * 5} 秒）",
                    "meta": {"progress": min(90, 10 + cycle * 2)}
                }),
                main_loop
            )
            # 同 progress_cb：心跳广播失败（客户端断连/transport flush 失败）
            # 绝对不能冒泡到主链路，静默吞掉
            def _suppress(_f):
                try:
                    _f.result()
                except Exception:
                    pass
            fut.add_done_callback(_suppress)

    hb_thread = threading.Thread(target=_heartbeat, daemon=True)
    hb_thread.start()

    # ---- 7. 执行合成 ----
    try:
        out = await synthesize_video_async(
            audio_path=audio_path,
            image_paths=image_paths,
            output_path=output_path,
            config=synth_config,
            work_dir=str(config.VIDEO_DIR),
            progress_cb=_make_progress_cb(sse),
        )
    finally:
        heartbeat_stop.set()
        hb_thread.join(timeout=1.0)

    file_size = os.path.getsize(out) if os.path.exists(out) else 0

    await _fire_and_forget_progress(sse, {
        "title": "视频生成",
        "content": "解析视频元数据",
        "meta": {"progress": 95}
    })

    # ---- 8. 元数据解析（时长/宽高） ----
    duration, width, height = _probe_output_metadata(str(out))

    # ---- 9. 持久化 ----
    payload_data = {
        "file_name": output_filename,
        "file_path": f"video/{output_filename}",
        "video_type": "generated",
        "title": title,
        "file_size": file_size,
        "duration": duration or None,
        "width": width,
        "height": height,
        "file_format": "mp4",
    }
    attach_ownership(payload_data, session_id=session_id)
    engine.video_create(json.dumps(payload_data, ensure_ascii=False))

    video_url = f"/media/video/{output_filename}"

    await _fire_and_forget_progress(sse, {
        "title": "视频生成",
        "content": "视频生成完成",
        "meta": {"progress": 100, "success": True, "video_url": video_url}
    })

    logger.info(
        f"视频生成完成: {output_path}, duration={duration}s, size={file_size}bytes, {width}x{height}",
        module_name=_MODULE_NAME
    )

    return {
        "ok": True,
        ke.KEY_VIDEO_URL: video_url,
        "file_name": output_filename,
        "duration": duration,
        "file_size": file_size,
        "width": width,
        "height": height,
    }
