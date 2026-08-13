"""filter_complex 构建：图片播放顺序、scale+pad/crop、单图铅笔画预处理、xfade 转场链。"""
import random
from typing import Any, Dict, List, Tuple

# ========== 工具函数 ==========

def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ========== 1. 画面尺寸解析 ==========

def resolve_video_size(config: Dict[str, Any], images: List) -> Tuple[int, int]:
    """解析视频尺寸：auto | 比例串 | WxH 串 | [W,H] 元组。

    Args:
        config: 用户配置，含 'video_size' 键
        images: 图片路径列表（auto 时按首图比例判定）

    Returns:
        (width, height)
    """
    from .media_probe import get_image_size
    size = config["video_size"]
    if isinstance(size, (list, tuple)) and len(size) == 2:
        return int(size[0]), int(size[1])
    if isinstance(size, str):
        if size == "auto":
            w, h = get_image_size(images[0])
            ratio = h / w
            if ratio > 1.3:
                return 1080, 1920
            elif ratio < 0.75:
                return 1920, 1080
            else:
                return 1080, 1080
        lower = size.lower()
        if "x" in lower:
            parts = lower.split("x")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return int(parts[0]), int(parts[1])
        presets = {
            "9:16": (1080, 1920), "16:9": (1920, 1080),
            "1:1": (1080, 1080), "4:3": (1440, 1080), "3:4": (1080, 1440),
        }
        if size in presets:
            return presets[size]
    return 1080, 1920


# ========== 2. 图片播放顺序 ==========

def build_image_order(n_images: int, order_mode: str, seed: int) -> List[int]:
    """构建图片播放顺序（不含末尾重复）。

    Args:
        n_images: 图片数量
        order_mode: 'sequential' 或 'shuffle'
        seed: shuffle 随机种子（可复现）

    Returns:
        图片索引列表（长度 n_images）
    """
    order = list(range(n_images))
    if order_mode == "shuffle":
        random.Random(seed).shuffle(order)
    return order


# ========== 3. 统一的 scale+pad/crop+fps 滤镜 ==========

def build_scale_pad(width: int, height: int, fit_mode: str, fps: int) -> str:
    """统一的 scale+pad/crop+fps 滤镜。

    Args:
        width: 目标宽度
        height: 目标高度
        fit_mode: 'contain'（等比留黑边）或 'cover'（等比裁剪填充）
        fps: 目标帧率
    """
    if fit_mode == "cover":
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={fps}"
        )
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:-1:-1:color=black,"
        f"setsar=1,fps={fps}"
    )


# ========== 4. 单图预处理 filter（含铅笔画） ==========

def build_image_filter(
    input_idx: int,
    img_idx: int,
    width: int,
    height: int,
    effects: Dict[str, Any],
    seg_dur: float,
    fps: int,
    fit_mode: str = "contain",
) -> Tuple[List[str], str]:
    """为单张图片构建预处理 filter。

    Args:
        input_idx: 循环序列中的位置（唯一命名标签）
        img_idx:   实际图片索引（查 apply_to，与播放顺序无关）
        width:     目标宽度
        height:    目标高度
        effects:   effects dict（含 pencil_sketch）
        seg_dur:   单图显示秒数
        fps:       帧率
        fit_mode:  contain/cover

    Returns:
        (filter_lines, output_label)
    """
    sp = build_scale_pad(width, height, fit_mode, fps)
    sketch = effects.get("pencil_sketch", {})
    pfx = f"i{input_idx}"
    v = f"v{input_idx}"

    # 铅笔画效果：当 apply_to 为空时默认应用到全部图片
    apply_to_list = sketch.get("apply_to", [])
    apply_all = len(apply_to_list) == 0

    if sketch.get("enabled") and (apply_all or img_idx in apply_to_list):
        bs = int(clamp(sketch.get("blur_size", 9), 1, 21))
        # boxblur 参数：radius ≈ blur_size * 0.75，power=2（三次 boxblur 近似一次高斯）
        # boxblur 比 gblur 快很多（尤其在 1080p+ 大图上），视觉效果接近
        blur_radius = max(1, int(bs * 0.75))
        direction = sketch.get("direction", "sketch_to_real")
        trans_dur = min(float(sketch.get("transition_duration", 5)), seg_dur)
        # sketch_to_real（素描→原图）方向：保留至少 25% 尾段稳定显示彩色原图，
        # 避免过渡时长等于单图时长导致彩色仅在最后一帧出现。
        if direction == "sketch_to_real":
            trans_dur = min(trans_dur, seg_dur * 0.75)
        intensity = clamp(float(sketch.get("intensity", 0.80)), 0.0, 1.0)
        sharpen = clamp(float(sketch.get("sharpen", 0.65)), 0.0, 2.0)

        cp = f"{pfx}_cp"    # color path（彩色原图）
        skp = f"{pfx}_sp"   # sketch path（素描输入）
        ga = f"{pfx}_ga"    # gray a（灰度原图）
        gb = f"{pfx}_gb"    # gray b（灰度反色）
        bn = f"{pfx}_bn"    # blurred negate（反色+模糊）
        sk = f"{pfx}_sk"    # sketch（dodge 素描结果）
        ss = f"{pfx}_ss"    # sketch scaled（素描路最终输出）
        base = f"{pfx}_base"

        sharpen_filter = (
            f"unsharp=5:5:{sharpen:.2f}:5:5:0," if sharpen > 0.0 else ""
        )

        # blend all_expr 按帧计数混合彩色与素描，完全绕过 alpha 通道。
        # 关键修复：使用 N（帧计数）替代 T（输出帧 PTS 时间）
        # 原因：T 是基于 dst->pts 的全局时间，在多段 filter_complex 中
        # 后续段的 T 不会从 0 开始（而是接续前段 PTS），导致表达式判断失效。
        # N 是每个滤镜实例独立的帧计数器（frame_count_out），始终从 0 开始。
        # 用单引号 '...' 包裹表达式，防止 ffmpeg 把逗号解析为 filtergraph 分隔符。
        transition_frames = int(trans_dur * fps)
        if direction == "sketch_to_real":
            # 素描→原图：N<trans_frames 时素描(B)渐隐、彩色(A)渐显；N>=trans_frames 时全彩色(A)
            expr = (
                f"if(lt(N,{transition_frames}),"
                f"A*(N/{transition_frames})+B*{intensity:.3f}*(1-N/{transition_frames}),"
                f"A)"
            )
        else:
            # 原图→素描：N<trans_frames 时彩色(A)渐隐、素描(B)渐显；N>=trans_frames 时全素描(B)
            expr = (
                f"if(lt(N,{transition_frames}),"
                f"A*{intensity:.3f}*(1-N/{transition_frames})+B*(N/{transition_frames}),"
                f"B)"
            )

        # 性能优化要点：
        # 1. 素描路先 scale 到目标尺寸再做模糊/混合，避免在原图大尺寸上做 boxblur（性能关键）
        # 2. boxblur 替代 gblur：计算量大幅降低，视觉效果接近
        # 3. 素描路已在目标尺寸，最终 blend 前无需重复 scale
        lines = [
            # 1. 原图 split（原始尺寸，不 scale）
            f"[{input_idx}:v]split=2[{cp}][{skp}]",
            # 2. 彩色路 scale+crop/pad+fps，转 gbrp（planar RGB）
            f"[{cp}]{sp},format=gbrp[{base}]",
            # 3. 素描路先 scale 到目标尺寸，再做灰度 → split → 反色+boxblur
            #    （先 scale 是性能关键：避免在 4K 原图上做模糊）
            f"[{skp}]{sp},format=gray,split=2[{ga}][{gb}]",
            f"[{gb}]negate,boxblur={blur_radius}:2[{bn}]",
            # 4. dodge 混合 → 素描效果（与 cv2 divide 算法等价）
            f"[{ga}][{bn}]blend=all_mode=dodge[{sk}]",
            # 5. 素描锐化，转 gbrp（素描路已在目标尺寸，无需再 scale）
            f"[{sk}]{sharpen_filter}format=gbrp[{ss}]",
            # 6. blend all_expr 按时间表达式混合彩色(A)与素描(B)，输出转 yuv420p 供编码
            f"[{base}][{ss}]blend=all_expr='{expr}',format=yuv420p[{v}]",
        ]
        return lines, v
    else:
        return [f"[{input_idx}:v]{sp},format=yuv420p[{v}]"], v


# ========== 5. xfade 转场链 ==========

def build_xfade_chain(
    labels: List[str],
    seg_dur: float,
    trans_type: str,
    trans_dur: float,
) -> Tuple[List[str], str, float]:
    """构建 xfade 转场链。

    Args:
        labels:     预处理后的输出标签列表
        seg_dur:    单段显示秒数（无转场时实际段长）
        trans_type: xfade transition 类型
        trans_dur:  转场时长（秒），0 表示使用 concat

    Returns:
        (filter_lines, output_label, total_duration)
    """
    if len(labels) == 1:
        return [], labels[0], seg_dur
    if trans_dur <= 0:
        ci = "".join(f"[{l}]" for l in labels)
        n = len(labels)
        return [f"{ci}concat=n={n}:v=1:a=0[vout_base]"], "vout_base", seg_dur * n

    lines = []
    prev = labels[0]
    accumulated = seg_dur

    for i in range(1, len(labels)):
        offset = accumulated - trans_dur
        out = f"vt{i:02d}" if i < len(labels) - 1 else "vout_base"
        lines.append(
            f"[{prev}][{labels[i]}]xfade=transition={trans_type}"
            f":duration={trans_dur}:offset={offset:.2f}[{out}]"
        )
        prev = out
        accumulated += seg_dur - trans_dur

    return lines, prev, accumulated
