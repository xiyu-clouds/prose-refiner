from typing import List, Optional, Dict, Any
from aiocache import Cache
from app.common import keys as ke
from app.common import values as va
from app.cache.base import BaseCache
from app.cache.serializer import UTF8JsonSerializer
from app.utils.logger import LoggerManager as logger


class RedisLLMCache(BaseCache):
    CHINESE_NAME = "Redis LLM 缓存后端"

    def __init__(
            self,
            config,
            default_ttl: Optional[int] = None,
    ):
        try:
            import redis
        except ImportError:
            raise RuntimeError(
                "Redis 缓存需要安装 'redis' 包。请在 requirements-runtime.txt 中添加 'redis' 并重建镜像。"
            )

        self.config = config
        self.default_ttl = default_ttl or int(config.LLM_CACHE_TTL)
        if not isinstance(self.default_ttl, int) or self.default_ttl < 0:
            raise ValueError("default_ttl 必须是非负整数")

        self._cache = Cache(
            Cache.REDIS,
            endpoint=config.REDIS_HOST,
            port=config.REDIS_PORT,
            db=config.REDIS_DB,
            password=config.REDIS_PASSWORD or None,
            timeout=config.REDIS_TIMEOUT,
            serializer=UTF8JsonSerializer(),
            namespace=va.VAL_REDIS_NAMESPACE,
        )

        self._disabled = False
        self._cache_hits = 0
        self._cache_misses = 0
        logger.info(
            f"使用 Redis 缓存后端，连接: redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}, "
            f"{ke.KEY_NAMESPACE}={self._cache.namespace}, {ke.KEY_SERIALIZER}={self._cache.serializer.__class__.__name__}"
        )

    # ========== 实现 BaseCache 的异步抽象方法 ==========
    async def _aget_raw(self, key: str) -> Optional[Dict[str, Any]]:
        if self._disabled:
            self._cache_misses += 1
            return None
        try:
            value = await self._cache.get(key)
            if value is not None:
                self._cache_hits += 1
                return value
            else:
                self._cache_misses += 1
                return None
        except Exception as e:
            if not self._disabled:
                logger.warning(f"Redis 获取数据失败（已标记临时禁用，后续跳过）(键名={key}): {e}")
                self._disabled = True
            self._cache_misses += 1
            return None

    async def _aset_raw(self, key: str, value: Dict[str, Any]) -> None:
        if self._disabled:
            return
        try:
            await self._cache.set(key, value, ttl=self.default_ttl)
        except Exception as e:
            if not self._disabled:
                logger.warning(f"Redis 写入数据失败（已标记临时禁用，后续跳过）(键名={key}): {e}")
                self._disabled = True

    async def _adelete_raw(self, key: str) -> None:
        if self._disabled:
            return
        try:
            await self._cache.delete(key)
        except Exception as e:
            logger.warning(f"Redis 删除数据失败 (键名={key}): {e}")

    async def _aclear_raw(self) -> None:
        if self._disabled:
            return
        try:
            await self._cache.clear()
        except Exception as e:
            if not self._disabled:
                logger.warning(f"Redis 清空缓存失败（已标记临时禁用，后续跳过）: {e}")
                self._disabled = True

    async def _akeys_raw(self) -> List[str]:
        if self._disabled:
            return []
        try:
            redis_client = self._cache.client
            namespace = self._cache.namespace or ""
            pattern = f"{namespace}:*" if namespace else "*"
            keys = []
            cursor = b'0'
            while cursor:
                cursor, batch = await redis_client.scan(cursor, match=pattern, count=100)
                keys.extend([k.decode(ke.KEY_UTF_8) for k in batch])
            prefix_len = len(namespace) + 1 if namespace else 0
            return [k[prefix_len:] for k in keys]
        except Exception as e:
            logger.warning(f"获取 Redis 键名列表失败: {e}")
            return []

    def stats(self) -> str:
        total = self._cache_hits + self._cache_misses
        status = "（已临时禁用：连接异常）" if self._disabled else ""
        if total == 0:
            return f"Redis LLM 缓存: 无本地调用统计{status}"
        hit_rate = self._cache_hits / total
        return (
            f"Redis 缓存命中率（本地统计）: {hit_rate:.2%} | 命中={self._cache_hits} | "
            f"未命中={self._cache_misses}{status}"
        )
