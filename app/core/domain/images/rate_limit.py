"""图片生成限流 —— 每日上限 + 最小间隔 + 429 退避识别。

从 routers/image_generation.py 提取，保持行为完全一致。
"""

import time
from typing import Optional

import requests

_MAX_DAILY = 400        # 每日图片生成上限
_MIN_INTERVAL = 3       # 最小调用间隔（秒）

# 429 限流识别与退避（z-image-turbo / qwen-image-plus 串行调用专用）
INTER_BATCH_INTERVAL = 1.5          # 串行相邻两张调用间隔（秒）
RATE_LIMIT_BACKOFF_BASE = 15.0      # 429 退避基数（秒），叠加随机抖动 0~10s → 实际 15~25s
MAX_RETRIES_PER_IMAGE = 3           # 单张独立重试上限

# 运行时限流状态（内存中，单进程有效）
_rate_limit_state = {
    "timestamps": [],
    "daily_count": 0,
    "daily_date": "",
}


def check_rate_limit() -> Optional[str]:
    """检查限流状态，返回错误消息或 None。"""
    now = time.time()
    today = time.strftime("%Y-%m-%d")

    if _rate_limit_state["daily_date"] != today:
        _rate_limit_state["daily_date"] = today
        _rate_limit_state["daily_count"] = 0
        _rate_limit_state["timestamps"] = []

    if _rate_limit_state["daily_count"] >= _MAX_DAILY:
        return f"今日图片生成次数已达上限 ({_MAX_DAILY} 张)，请明天再来"

    if _rate_limit_state["timestamps"]:
        last_call = _rate_limit_state["timestamps"][-1]
        elapsed = now - last_call
        if elapsed < _MIN_INTERVAL:
            wait = _MIN_INTERVAL - elapsed
            return f"请求过于频繁，请 {wait:.0f} 秒后再试（最小间隔 {_MIN_INTERVAL} 秒）"

    return None


def record_call():
    """记录一次调用。"""
    now = time.time()
    _rate_limit_state["timestamps"].append(now)
    _rate_limit_state["daily_count"] += 1


def is_rate_limit_exception(exc: BaseException) -> bool:
    """判断是否为阿里云 429 限流异常（Throttling.RateQuota）。"""
    if isinstance(exc, requests.exceptions.HTTPError):
        resp = getattr(exc, "response", None)
        if resp is not None and resp.status_code == 429:
            return True
    return False


def extract_retry_after(exc: BaseException) -> Optional[float]:
    """从 429 响应的 Retry-After 头读取建议等待秒数；无则返回 None。"""
    if not isinstance(exc, requests.exceptions.HTTPError):
        return None
    resp = getattr(exc, "response", None)
    if resp is None:
        return None
    try:
        ra = resp.headers.get("Retry-After")
        if ra is None:
            return None
        return max(1.0, float(ra))
    except (ValueError, TypeError):
        return None
