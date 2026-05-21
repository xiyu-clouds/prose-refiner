from datetime import datetime, date
from typing import Any, Optional, Set
import json
from app.common import values as va


def serialize_datetime_objects(data: Any, remove_keys: Optional[Set[str]] = None) -> Any:
    """
    递归清洗数据：
    1. 将 datetime/date 对象转换为 ISO 8601 字符串。
    2. 删除指定键名的字段（如 '_request'）。

    Args:
        data: 任意嵌套的数据结构。
        remove_keys: 需要删除的键名集合，默认为 None（表示不删除任何键）。

    Returns:
        清洗后的数据副本。
    """
    if isinstance(data, dict):
        # 先删除指定键
        if remove_keys:
            filtered_data = {k: v for k, v in data.items() if k not in remove_keys}
        else:
            filtered_data = data.copy()
        # 递归处理值
        return {k: serialize_datetime_objects(v, remove_keys) for k, v in filtered_data.items()}
    elif isinstance(data, list):
        return [serialize_datetime_objects(item, remove_keys) for item in data]
    elif isinstance(data, (datetime, date)):
        return data.isoformat()
    else:
        return data


def safe_json_dumps(data: Any, **kwargs) -> str:
    """
    封装 json.dumps，自动处理 datetime 序列化。
    """
    clean_data = serialize_datetime_objects(data, remove_keys=va.VAL_REMOVE_KEYS)
    return json.dumps(clean_data, ensure_ascii=False, **kwargs)
