"""ffprobe 封装：获取图片尺寸、音频时长、视频时长。"""
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple


class MediaProbeError(Exception):
    """ffprobe 探测失败异常。"""
    pass


def run_ffprobe(args: List[str], cwd: Optional[Path] = None) -> str:
    r = subprocess.run(
        ["ffprobe", "-v", "error"] + args,
        capture_output=True, text=True,
        cwd=str(cwd) if cwd else None,
    )
    if r.returncode != 0:
        raise MediaProbeError(f"ffprobe failed: {r.stderr.strip()}")
    return r.stdout.strip()


def get_image_size(img_path: Path) -> Tuple[int, int]:
    """返回 (width, height)。"""
    out = run_ffprobe([
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0", str(img_path),
    ])
    parts = out.split(",")
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise MediaProbeError(f"无法解析图片尺寸: {img_path}, raw={out}")
    return int(parts[0]), int(parts[1])


def get_audio_duration(audio_path: Path) -> float:
    """返回音频时长（秒）。"""
    out = run_ffprobe([
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path),
    ])
    try:
        return float(out)
    except (TypeError, ValueError) as e:
        raise MediaProbeError(f"无法解析音频时长: {audio_path}, raw={out}") from e


def get_video_duration(video_path: Path) -> float:
    """返回视频容器时长（秒）。用于生成后自身校验。"""
    out = run_ffprobe([
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video_path),
    ])
    try:
        return float(out)
    except (TypeError, ValueError) as e:
        raise MediaProbeError(f"无法解析视频时长: {video_path}, raw={out}") from e
