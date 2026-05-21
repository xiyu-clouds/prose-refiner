from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo
from app.common import keys as ke
from app.common import values as va
from app.utils.logger import LoggerManager as logger

CHINESE_NAME = "时间戳格式化"


def format_timestamp_with_weekday(timestamp: Optional[float] = None) -> str:
    """
    将 Unix 时间戳（秒）格式化为 "YYYY-MM-DD HH:MM:SS.mmm 星期X" 的字符串。
    若不传入 timestamp，则使用当前系统时间。
    时区固定为 UTC
    例如: 2026-04-02 13:31:02.123 星期四
    """
    tz = ZoneInfo(ke.KEY_UP_UTC)

    try:
        if timestamp is None:
            dt = datetime.now(tz)
        else:
            dt = datetime.fromtimestamp(timestamp, tz=tz)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)

        # 星期
        weekday = va.VAL_WEEKDAY[dt.weekday()]

        # 格式化日期时间，保留毫秒（三位）
        base_time = dt.strftime("%Y-%m-%d %H:%M:%S") + f".{int(dt.microsecond / 1000):03d}"
        return f"{base_time} {weekday}"
    except Exception as e:
        logger.warning(
            f"🕒 格式化时间戳失败: {e}",
            module_name=CHINESE_NAME,
            extra={ke.KEY_TIMESTAMP: timestamp}
        )
        return "未知"
