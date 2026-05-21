import asyncio
import time
from typing import Any, Dict, Optional, List
from collections import OrderedDict
from app.common import keys as ke
from app.config.config import config
from app.cache.base import BaseCache
from app.utils.logger import LoggerManager as logger


class LLMCache(BaseCache):
    CHINESE_NAME = "LLM 内存缓存中枢"
    DEFAULT_MAX_SIZE = int(config.LLM_CACHE_MAX_SIZE)

    def __init__(
            self,
            max_size: int = DEFAULT_MAX_SIZE,
            ttl_seconds: Optional[int] = None,
    ):
        self.cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()
        self._cache_hits = 0
        self._cache_misses = 0
        logger.info(
            f"🔌 首次使用 {config.STORAGE_BACKEND} 缓存，连接信息: "
            f"local://{config.STORAGE_BACKEND}:{config.LLM_CACHE_MAX_SIZE}/{config.LLM_CACHE_TTL}, "
        )

    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        if self.ttl_seconds is None or ke.KEY_TIMESTAMP not in entry:
            return False
        return (time.time() - entry[ke.KEY_TIMESTAMP]) > self.ttl_seconds

    @staticmethod
    def _key_summary(key: str) -> str:
        return key[:8] + "..." if len(key) > 8 else key

    # ========== 实现异步抽象方法 ==========
    async def _aget_raw(self, key: str) -> Optional[Dict[str, Any]]:
        key_sum = self._key_summary(key)
        async with self._lock:
            entry = self.cache.get(key)
            if entry is None:
                self._cache_misses += 1
                logger.warning(f"[LLM缓存] 未命中 (键名={key_sum})")
                return None
            if self._is_expired(entry):
                del self.cache[key]
                self._cache_misses += 1
                logger.warning(f"[LLM缓存] 已过期并移除 (键名={key_sum})")
                return None
            self.cache.move_to_end(key)
            self._cache_hits += 1
            logger.info(f"[LLM缓存] 命中 (键名={key_sum})")
            return entry[ke.KEY_VALUE]

    async def _aset_raw(self, key: str, value: Dict[str, Any]) -> None:
        key_sum = self._key_summary(key)
        async with self._lock:
            entry = {ke.KEY_VALUE: value, ke.KEY_TIMESTAMP: time.time()}
            if key in self.cache:
                logger.info(f"[LLM缓存] 更新 (键名={key_sum})")
                del self.cache[key]
            else:
                logger.info(f"[LLM缓存] 设置 (键名={key_sum})")
            self.cache[key] = entry
            while len(self.cache) > self.max_size:
                evicted_key, _ = self.cache.popitem(last=False)
                logger.info(f"[LLM缓存] 驱逐 (键名={self._key_summary(evicted_key)})")

    async def _adelete_raw(self, key: str) -> None:
        key_sum = self._key_summary(key)
        async with self._lock:
            if key in self.cache:
                del self.cache[key]
                logger.info(f"[LLM缓存] 删除 (键名={key_sum})")

    async def _aclear_raw(self) -> None:
        async with self._lock:
            count = len(self.cache)
            self.cache.clear()
            self._cache_hits = 0
            self._cache_misses = 0
            logger.info(f"[LLM缓存] 清空 {count} 条目")

    async def _akeys_raw(self) -> List[str]:
        async with self._lock:
            valid_keys = []
            for k, v in list(self.cache.items()):
                if not self._is_expired(v):
                    valid_keys.append(k)
                else:
                    del self.cache[k]
            return valid_keys

    def stats(self) -> str:
        total = self._cache_hits + self._cache_misses
        if total == 0:
            return "📊 LLM 缓存: 无调用"
        hit_rate = self._cache_hits / total
        return (
            f"📊 LLM 缓存命中率: {hit_rate:.2%} | "
            f"命中={self._cache_hits} | 未命中={self._cache_misses} | "
            f"当前大小={len(self.cache)} / {self.max_size}"
        )
