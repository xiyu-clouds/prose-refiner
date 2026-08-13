"""主合成器：synthesize_video(audio_path, image_paths, output_path, config)。

两步走：
  Step 1: 生成循环片段（图片序列 + 铅笔画 + 转场）→ loop_segment.mp4（临时唯一文件名）
  Step 2: -stream_loop -1 循环片段 + 音频流 → 最终视频 output_path

统一使用 CPU libx264 编码，不再依赖 GPU 资源。
铅笔画效果通过 OpenCV 预处理完成，只生成过渡帧，稳定段用单张图片 + FFmpeg -loop。
"""
import asyncio
import io
import os
import subprocess
import tempfile
import threading
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from app.utils.logger import LoggerManager as logger

_LOG_MODULE = "视频合成器"

from .filter_builder import (
    build_image_order,
    build_image_filter,
    build_xfade_chain,
    resolve_video_size,
)
from .media_probe import MediaProbeError, get_audio_duration, get_image_size, run_ffprobe
from .quality import resolve_quality
from .pencil_sketch_preprocessor import generate_frames_to_pipe


class VideoSynthError(Exception):
    """视频合成失败。"""
    pass


ProgressCb = Optional[Callable[[int, str], None]]  # (progress_percent, message)


def _drain_stderr_async(proc: subprocess.Popen, sink: io.BytesIO) -> threading.Thread:
    """后台线程消费 Popen.stderr，避免 64KB pipe buffer 写满阻塞 FFmpeg。

    实际依据（不猜）：Linux pipe 默认 64KB，FFmpeg 默认会持续把编码进度
    写到 stderr（即便成功编码）。如果主流程在写入 stdin 的数秒到数十秒
    期间未调用 communicate（会启动 reader 线程），stderr 管道很容易积满
    → FFmpeg write(stderr) 阻塞 → FFmpeg 无法继续 read(stdin) → Python
    侧 proc.stdin.write() 卡住或出现"管道破裂/flush of closed file"
    这种无排查价值的错误。
    """
    def _reader():
        try:
            while True:
                chunk = proc.stderr.read(65536)
                if not chunk:
                    break
                sink.write(chunk)
        except (ValueError, OSError):
            # 管道已被另一侧关闭，读线程静默结束
            pass

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    return t


def _is_valid_media(path: Path) -> bool:
    """检查媒体文件是否完整可用（ffprobe 可解析时长且文件非空）。"""
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        dur = run_ffprobe([
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ])
        return float(dur) > 0
    except (MediaProbeError, ValueError):
        return False


# ========== Step 1: 生成循环片段 ==========

def _generate_loop_segment(
    images: List[Path],
    width: int,
    height: int,
    fps: int,
    config: Dict[str, Any],
    work_dir: Path,
    loop_file: Path,
    progress_cb: ProgressCb = None,
) -> float:
    """生成循环片段，返回片段时长（秒）。失败抛 VideoSynthError。

    支持两种路径：
    1. 铅笔画效果开启时，使用 OpenCV 预处理生成过渡帧 + FFmpeg concat。
    2. 其他情况（铅笔画关闭），使用原有的 FFmpeg filter_complex 滤镜链。
    """
    seg_dur = float(config.get("image_interval", 8))
    effects = config.get("effects", {}) or {}
    trans = effects.get("transition", {}) or {}
    trans_en = bool(trans.get("enabled", False))
    trans_type = str(trans.get("type", "fade"))
    trans_dur = float(trans.get("duration", 0.8)) if trans_en else 0
    fit_mode = str(config.get("fit_mode", "contain"))
    pencil_sketch_en = bool(effects.get("pencil_sketch", {}).get("enabled", False))

    crf, enc_preset, _, _ = resolve_quality(config)

    # ========== OpenCV 管道路径（铅笔画效果开启时）==========
    if pencil_sketch_en:
        logger.info(
            "使用 OpenCV 管道方式生成铅笔画过渡帧，直接传给 FFmpeg 编码",
            module_name=_LOG_MODULE
        )

        # 图片序列组件
        order_mode = str(config.get("image_order", "sequential"))
        seed = int(config.get("shuffle_seed", 42))
        order = build_image_order(len(images), order_mode, seed)
        cycle = order + [order[0]]
        ordered_images = [images[i] for i in cycle]

        total_duration = len(ordered_images) * seg_dur

        if progress_cb:
            progress_cb(10, "开始生成铅笔画帧并编码")

        # 构建 FFmpeg 管道命令：从 stdin 读取 rawvideo BGR 像素数据
        cmd: List[str] = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "-",
            "-c:v", "libx264", "-preset", enc_preset,
            "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-t", f"{total_duration:.3f}",
            str(loop_file),
        ]

        logger.info(
            f"rawvideo 管道命令: images={len(ordered_images)}, "
            f"size={width}x{height}, duration={total_duration:.2f}s, "
            f"encoder=libx264, preset={enc_preset}, crf={crf}",
            module_name=_LOG_MODULE
        )

        # 超时设置
        base_timeout = 30
        per_second = 2.5
        max_timeout = 600
        timeout_sec = min(base_timeout + total_duration * per_second, max_timeout)

        # 启动 FFmpeg 进程
        logger.info(
            f"[probe] 启动 FFmpeg rawvideo 子进程: workdir={work_dir}, "
            f"cmd={' '.join(cmd)}",
            module_name=_LOG_MODULE
        )
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            cwd=str(work_dir),
        )
        logger.info(f"[probe] FFmpeg pid={proc.pid}", module_name=_LOG_MODULE)

        # ⚠️ 关键：立即启动后台线程消费 stderr，避免 64KB Linux pipe 缓冲区
        # 积满阻塞 FFmpeg 主循环（否则 20s+ 长任务里 FFmpeg 经常会卡在
        # write(stderr)，连带 stdin 读也停掉，最终管道"莫名其妙"破裂）。
        stderr_sink = io.BytesIO()
        drain_thread = _drain_stderr_async(proc, stderr_sink)
        logger.info("[probe] stderr drain 线程已启动", module_name=_LOG_MODULE)

        # 逐帧生成并写入管道
        expected_frame_size = width * height * 3  # bgr24: 每像素 3 字节
        write_error: Optional[Exception] = None
        write_idx = 0
        last_probe_ts = 0.0
        try:
            logger.info(f"[probe] 进入帧循环，expected_frame_size={expected_frame_size}", module_name=_LOG_MODULE)
            # 把 pencils 的 (frame_idx, total_frames) 进度折算成视频总体的 10~45% 段
            def _wrap_pencil_progress(cb, seg_start_pct=10, seg_end_pct=45):
                if not cb:
                    return None
                def _wrapped(frame_idx: int, total_frames: int):
                    if total_frames <= 0:
                        return
                    p = seg_start_pct + int((seg_end_pct - seg_start_pct) * min(1.0, frame_idx / total_frames))
                    try:
                        cb(p, f"铅笔画帧处理 {frame_idx}/{total_frames}")
                    except Exception:
                        # progress_cb 失败永远不阻塞帧写入
                        pass
                return _wrapped

            for frame_bytes in generate_frames_to_pipe(
                images=ordered_images,
                width=width,
                height=height,
                fps=fps,
                effects=effects,
                seg_dur=seg_dur,
                progress_cb=_wrap_pencil_progress(progress_cb),
            ):
                write_idx += 1
                # 基于 rawvideo 语义做长度校验（有实际逻辑支撑，不靠猜测）：
                #   FFmpeg -f rawvideo -pix_fmt bgr24 -s WxH 逐帧读取时，每帧
                #   严格需要 W*H*3 字节。多/少字节会导致后续所有帧错位，FFmpeg
                #   编码一段时间后才报错（stderr 可能隐晦）。这里提前发现，
                #   主动 kill + 抛错，避免走到 communicate 时才出现"管道断裂/flush
                #   of closed file"这种对排查无帮助的症状。
                if len(frame_bytes) != expected_frame_size:
                    write_error = VideoSynthError(
                        f"rawvideo 帧尺寸异常（帧序={write_idx}）："
                        f"期望 {expected_frame_size} bytes，实际 {len(frame_bytes)} bytes"
                        f"（图像尺寸与命令行 -s {width}x{height} 不匹配）"
                    )
                    logger.error(
                        f"[probe] 帧 {write_idx} 长度不匹配，kill ffmpeg",
                        module_name=_LOG_MODULE
                    )
                    proc.kill()
                    break
                try:
                    proc.stdin.write(frame_bytes)
                except BrokenPipeError:
                    # FFmpeg 已关闭读端（通常是编码出错或输入校验失败）
                    # 不马上抛，保存现场以便 communicate 拿完整 stderr
                    write_error = BrokenPipeError(
                        f"FFmpeg 管道读端已关闭（帧序={write_idx}，可能编码/校验出错）"
                    )
                    logger.error(
                        f"[probe] BrokenPipeError 帧 {write_idx}", exc_info=True,
                        module_name=_LOG_MODULE
                    )
                    break
                except (ValueError, OSError) as e:
                    # e.g. ValueError("flush of closed file")：管道对端被强制关
                    # 闭而 stdin BufferedWriter 已经 close 标记；或 OSError(EPIPE)
                    write_error = e
                    logger.error(
                        f"[probe] stdin.write ValueError/OSError 帧 {write_idx}: "
                        f"{type(e).__name__}: {e}", exc_info=True,
                        module_name=_LOG_MODULE
                    )
                    break
                # 每 2 秒打一个 probe 日志，便于区分"死循环"还是"编码慢"
                import time
                now = time.monotonic()
                if now - last_probe_ts > 2.0:
                    last_probe_ts = now
                    logger.info(
                        f"[probe] 帧写入进度: idx={write_idx}, "
                        f"proc.alive={proc.poll() is None}",
                        module_name=_LOG_MODULE
                    )
            logger.info(
                f"[probe] 帧循环退出: written={write_idx}, "
                f"write_error={type(write_error).__name__ if write_error else None}, "
                f"proc.poll()={proc.poll()}",
                module_name=_LOG_MODULE
            )
        except Exception as e:
            logger.error(
                f"[probe] 帧生成外层异常: {type(e).__name__}: {e}\n{traceback.format_exc()}",
                exc_info=True, module_name=_LOG_MODULE
            )
            try:
                proc.kill()
            except Exception:
                pass
            raise VideoSynthError(f"铅笔画帧生成失败（帧序={write_idx}）: {e}") from e

        # 关闭管道并等待 FFmpeg 完成
        logger.info("[probe] 准备 proc.stdin.close()", module_name=_LOG_MODULE)
        try:
            proc.stdin.close()
            logger.info("[probe] proc.stdin.close() 完成", module_name=_LOG_MODULE)
        except (BrokenPipeError, ValueError, OSError) as e:
            logger.warning(
                f"[probe] stdin.close 忽略异常: {type(e).__name__}: {e}",
                module_name=_LOG_MODULE
            )

        # ⚠️ 关键：使用 proc.wait() 而非 proc.communicate()
        # 因为 communicate() 内部会尝试 flush 已关闭的 stdin，导致 ValueError
        # stderr 已由 drain_thread 消费，stdin 已关闭，只需等待进程结束
        logger.info(f"[probe] 等待 drain_thread & proc.wait，timeout={timeout_sec}s", module_name=_LOG_MODULE)
        try:
            drain_thread.join(timeout=max(30, int(timeout_sec)))
            proc.wait(timeout=timeout_sec)
            stderr_bytes = stderr_sink.getvalue()
        except subprocess.TimeoutExpired:
            logger.error(f"[probe] wait 超时，kill ffmpeg", module_name=_LOG_MODULE)
            proc.kill()
            try:
                proc.wait(timeout=10)
            except Exception:
                pass
            stderr_bytes = stderr_sink.getvalue()
            if _is_valid_media(loop_file):
                if progress_cb:
                    progress_cb(45, "循环片段已生成（超时但文件完整）")
                logger.warning(
                    f"[probe] 超时但输出文件合法: size={loop_file.stat().st_size}",
                    module_name=_LOG_MODULE
                )
                return total_duration
            err_tail = stderr_bytes.decode('utf-8', errors='replace')[-1200:] if stderr_bytes else ""
            raise VideoSynthError(
                f"管道编码超时（{timeout_sec}秒）且输出文件不完整：\n{err_tail}"
            )

        logger.info(
            f"[probe] wait 完成: returncode={proc.returncode}, "
            f"stderr_bytes={len(stderr_bytes)}",
            module_name=_LOG_MODULE
        )
        if proc.returncode != 0:
            err_tail = stderr_bytes.decode('utf-8', errors='replace')[-1200:] if stderr_bytes else ""
            # 合成 write_error 的上下文（如果之前在 write 阶段就已报错），
            # 避免出现只看到"returncode != 0"却不知为何管道提前断。
            ctx = ""
            if write_error is not None:
                ctx = f"\n[写入阶段异常] {type(write_error).__name__}: {write_error}"
            logger.error(
                f"FFmpeg 管道编码失败: returncode={proc.returncode}, ctx={ctx}, error={err_tail}",
                module_name=_LOG_MODULE
            )
            raise VideoSynthError(f"管道编码失败：{ctx}\n{err_tail}")

        # returncode == 0 但若之前管道 write 阶段已报错，输出可能缺帧，仍视为失败。
        if write_error is not None and not _is_valid_media(loop_file):
            raise VideoSynthError(
                f"管道写入异常（returncode 被对端吞掉）："
                f"{type(write_error).__name__}: {write_error}"
            )

        logger.info(
            f"管道编码完成: duration={total_duration:.2f}s, output_size={loop_file.stat().st_size if loop_file.exists() else 0}",
            module_name=_LOG_MODULE
        )

        if progress_cb:
            progress_cb(45, "循环片段生成完成")

        return total_duration

    # ========== 原始 FFmpeg filter_complex 路径（铅笔画关闭时）==========
    order_mode = str(config.get("image_order", "sequential"))
    seed = int(config.get("shuffle_seed", 42))
    order = build_image_order(len(images), order_mode, seed)
    cycle = order + [order[0]]

    logger.info(
        f"图片播放顺序: mode={order_mode}, seed={seed}, n_images={len(images)}, "
        f"order={order}, cycle={cycle}",
        module_name=_LOG_MODULE
    )

    # 构建每张图的预处理 filter
    all_lines: List[str] = []
    labels: List[str] = []
    for i, img_idx in enumerate(cycle):
        lines, label = build_image_filter(
            i, img_idx, width, height, effects, seg_dur, fps, fit_mode
        )
        all_lines.extend(lines)
        labels.append(label)

    # xfade 转场链 或 concat
    xfade_lines, out_label, total = build_xfade_chain(
        labels, seg_dur, trans_type, trans_dur
    )
    all_lines.extend(xfade_lines)

    filter_str = ";".join(all_lines)

    logger.info(
        f"Step1 filter_complex: seg_dur={seg_dur}, trans_dur={trans_dur}, "
        f"n_cycle={len(cycle)}, encoder=libx264, enc_preset={enc_preset}, crf={crf}, "
        f"filter_complex={filter_str}",
        module_name=_LOG_MODULE
    )

    cmd: List[str] = ["ffmpeg", "-y"]
    for img_idx in cycle:
        cmd.extend([
            "-loop", "1", "-framerate", str(fps),
            "-t", str(seg_dur),
            "-i", str(images[img_idx]),
        ])
    cmd.extend([
        "-filter_complex", filter_str,
        "-map", f"[{out_label}]",
        "-c:v", "libx264", "-preset", enc_preset,
        "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-t", f"{total:.3f}",
        str(loop_file),
    ])

    # 超时计算
    base_timeout = 60
    per_segment = 30
    max_timeout = 900
    timeout_sec = min(base_timeout + len(cycle) * per_segment, max_timeout)

    logger.info(
        f"Step1 超时设置: segments={len(cycle)}, timeout={timeout_sec}秒",
        module_name=_LOG_MODULE
    )
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(work_dir), timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        if _is_valid_media(loop_file):
            if progress_cb:
                progress_cb(45, "循环片段已生成（超时但文件完整）")
            return total
        raise VideoSynthError(
            f"循环片段生成超时（{timeout_sec}秒）且输出文件不完整，"
            f"请减少图片数量或增加超时时间"
        )
    if r.returncode != 0:
        tail = "\n".join([l.strip() for l in r.stderr.split("\n")[-20:] if l.strip()])
        raise VideoSynthError(f"循环片段生成失败:\n{tail}")

    return total


# ========== Step 2: 循环片段 + 音频 ==========

def _merge_with_audio(
    loop_file: Path,
    loop_dur: float,
    audio_path: Path,
    total_dur: float,
    output_path: Path,
    config: Dict[str, Any],
    work_dir: Path,
    progress_cb: ProgressCb = None,
) -> None:
    """循环片段 + 音频 → 最终视频。流复制视频避免重编码，超时后检查输出文件。"""
    _, _, audio_bitrate, _ = resolve_quality(config)
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(loop_file),
        "-i", str(audio_path),
        "-map", "0:v", "-map", "1:a",
        "-t", f"{total_dur:.3f}",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", audio_bitrate,
        "-movflags", "+faststart",
        str(output_path),
    ]

    timeout_sec = min(int(total_dur * 0.1) + 30, 300)

    p = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, universal_newlines=True, cwd=str(work_dir),
    )
    total_frames_est = int(total_dur * float(config.get("fps", 25)))
    last_pct = 0
    try:
        for line in p.stdout or []:
            s = line.strip()
            if s.startswith("frame=") and total_frames_est > 0 and progress_cb is not None:
                try:
                    frame_part = s.split("fps=")[0].replace("frame=", "").strip()
                    frame_n = int(frame_part)
                    pct = min(99, int(50 + 0.49 * frame_n / max(1, total_frames_est) * 100))
                    if pct > last_pct:
                        last_pct = pct
                        progress_cb(pct, "合并音频与视频")
                except (ValueError, IndexError):
                    pass
        p.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
        if _is_valid_media(output_path):
            if progress_cb:
                progress_cb(99, "视频已生成（超时但文件完整）")
            return
        raise VideoSynthError("音频与视频合并超时且输出文件不完整")
    if p.returncode != 0:
        if _is_valid_media(output_path):
            if progress_cb:
                progress_cb(99, "视频已生成")
            return
        raise VideoSynthError("音频与视频合并失败 (ffmpeg non-zero exit)")


# ========== 对外入口 ==========

def synthesize_video(
    audio_path: Union[str, os.PathLike],
    image_paths: List[Union[str, os.PathLike]],
    output_path: Union[str, os.PathLike],
    config: Optional[Dict[str, Any]] = None,
    work_dir: Optional[Union[str, os.PathLike]] = None,
    progress_cb: ProgressCb = None,
) -> Path:
    """组件化视频合成主入口。

    Args:
        audio_path:   已存在的音频文件路径（绝对或相对 work_dir）
        image_paths:  图片路径列表（长度 ≥ 1）
        output_path:  最终输出 mp4 路径
        config:       组件配置
        work_dir:     工作目录（存放临时文件）
        progress_cb:  可选回调：(percent: int, message: str) → None

    Returns:
        实际写入的 output_path（Path）

    Raises:
        VideoSynthError: 资源检查、ffprobe、ffmpeg 任一步骤失败
    """
    if config is None:
        config = {}

    audio_p = Path(audio_path)
    images_p = [Path(p) for p in image_paths]
    output_p = Path(output_path)

    # ---- 资源检查 ----
    if not audio_p.exists():
        raise VideoSynthError(f"音频文件不存在: {audio_p}")
    if not images_p:
        raise VideoSynthError("图片列表不能为空")
    for img in images_p:
        if not img.exists():
            raise VideoSynthError(f"图片不存在: {img}")

    # ---- 工作目录与临时文件 ----
    if work_dir is None:
        work_p = output_p.parent
    else:
        work_p = Path(work_dir)
    work_p.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix="video_synth_", dir=str(work_p)))
    loop_file = tmp_dir / "loop_segment.mp4"
    try:
        fps = int(config.get("fps", 25))

        if progress_cb:
            progress_cb(5, "探测资源信息")

        # ---- 探测尺寸 / 时长 ----
        try:
            for i, img in enumerate(images_p):
                _w, _h = get_image_size(img)
                _ = _w, _h
            total_dur = get_audio_duration(audio_p)
        except MediaProbeError as e:
            raise VideoSynthError(f"资源探测失败: {e}") from e

        width, height = resolve_video_size(config, images_p)
        crf, enc_preset, audio_bitrate, encoder = resolve_quality(config)

        if progress_cb:
            progress_cb(10, "开始生成循环片段")

        # ---- Step 1: 循环片段 ----
        loop_dur = _generate_loop_segment(
            images_p, width, height, fps, config, tmp_dir, loop_file, progress_cb
        )
        if loop_dur <= 0 or not loop_file.exists():
            raise VideoSynthError("循环片段生成失败：无输出文件")

        if progress_cb:
            progress_cb(50, "合并音频")

        # ---- Step 2: 循环 + 音频 ----
        _merge_with_audio(
            loop_file, loop_dur, audio_p, total_dur, output_p,
            config, tmp_dir, progress_cb,
        )

        if not output_p.exists() or output_p.stat().st_size == 0:
            raise VideoSynthError("最终视频输出为空")

        if progress_cb:
            progress_cb(100, "视频合成完成")

        return output_p
    finally:
        # 清理临时文件（递归清理子目录）
        if loop_file.exists():
            try:
                loop_file.unlink()
            except OSError:
                pass
        try:
            if tmp_dir.exists():
                for item in tmp_dir.rglob("*"):
                    try:
                        if item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            item.rmdir()
                    except OSError:
                        pass
                tmp_dir.rmdir()
        except OSError:
            pass


# ========== async 包装：避免阻塞事件循环 ==========

async def synthesize_video_async(
    audio_path: Union[str, os.PathLike],
    image_paths: List[Union[str, os.PathLike]],
    output_path: Union[str, os.PathLike],
    config: Optional[Dict[str, Any]] = None,
    work_dir: Optional[Union[str, os.PathLike]] = None,
    progress_cb: ProgressCb = None,
) -> Path:
    """async 版本：将同步 ffmpeg 调用放到线程池，避免阻塞 asyncio 事件循环。"""
    return await asyncio.to_thread(
        synthesize_video,
        audio_path, image_paths, output_path, config, work_dir, progress_cb,
    )
