"""
视频合成模块 — 基于 ffmpeg 的组件化视频合成

组件清单（各自独立开关/参数）：
  1. 图片序列组件：image_order(顺序/随机) + image_interval + shuffle_seed
  2. 转场组件：    effects.transition（图片间过渡）
  3. 铅笔画组件：  effects.pencil_sketch（方向统一，不自动混合）
  4. 画面组件：    video_size + fit_mode + quality

用法：
  from app.core.video_synthesis import synthesize_video
  synthesize_video(audio_path, image_paths, output_path, config)
"""
from .synthesizer import synthesize_video, synthesize_video_async, VideoSynthError
from .generator import generate_video_for_chapter

__all__ = ["synthesize_video", "synthesize_video_async", "VideoSynthError", "generate_video_for_chapter"]
