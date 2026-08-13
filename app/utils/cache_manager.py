import threading
import time
from typing import Any, Dict, Optional, Tuple

_CACHE_STORE: Dict[str, Tuple[Any, float]] = {}
_LOCK = threading.Lock()

DEFAULT_TTL_STATIC = 3600
DEFAULT_TTL_CONFIG = 1800

CK_META_VENDOR_MODEL = "meta:vendor_model"
CK_META_REASONING_TYPES = "meta:reasoning_types"
CK_META_CARD_CONFIG = "meta:card_config"
CK_META_FRONTEND_THRESHOLDS = "meta:frontend_thresholds"
CK_CONFIG_PUNCTUATION = "config:punctuation"
CK_CONFIG_TEXT_CORRECTION = "config:text_correction"


def get(key: str) -> Optional[Any]:
    with _LOCK:
        entry = _CACHE_STORE.get(key)
    if entry is None:
        return None
    value, expire_ts = entry
    if 0 < expire_ts < time.time():
        with _LOCK:
            _CACHE_STORE.pop(key, None)
        return None
    return value


def set_value(key: str, value: Any, ttl_seconds: int = DEFAULT_TTL_CONFIG) -> None:
    expire_ts = 0 if ttl_seconds <= 0 else (time.time() + ttl_seconds)
    with _LOCK:
        _CACHE_STORE[key] = (value, expire_ts)


def invalidate(*keys: str) -> None:
    if not keys:
        return
    with _LOCK:
        for k in keys:
            _CACHE_STORE.pop(k, None)


def clear() -> None:
    with _LOCK:
        _CACHE_STORE.clear()
