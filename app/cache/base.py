from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import hashlib
import json
from app.common import keys as ke
from app.utils.logger import LoggerManager as logger


class BaseCache(ABC):
    CHINESE_NAME = "抽象基类缓存器"

    @staticmethod
    def make_key(name: str, **kwargs) -> str:
        try:
            normalized_vars = {}
            for k, v in kwargs.items():
                if v is None:
                    v = ke.KEY_NONE
                elif isinstance(v, bool):
                    v = str(v).lower()
                elif isinstance(v, (int, float)):
                    if isinstance(v, float):
                        v = round(v, 10)
                elif isinstance(v, (list, dict)):
                    v = json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
                elif isinstance(v, str):
                    # 对所有字符串统一处理：超过 512 字符则摘要
                    if len(v) > 512:
                        digest = hashlib.blake2b(v.encode(ke.KEY_UTF_8), digest_size=16).hexdigest()
                        v = f"__HEART_SEA__{digest}"
                else:
                    v = str(v)
                normalized_vars[k] = v

            sorted_items = tuple(sorted(normalized_vars.items()))
            repr_str = f"{name}||{sorted_items}"
            return hashlib.blake2b(repr_str.encode(ke.KEY_UTF_8), digest_size=20).hexdigest()
        except Exception as e:
            logger.warning(f"生成缓存键失败，使用备用方案: {e}")
            return hashlib.blake2b(name.encode(ke.KEY_UTF_8), digest_size=20).hexdigest()

    # ========== 异步底层存储接口（子类必须实现）==========
    @abstractmethod
    async def _aget_raw(self, key: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def _aset_raw(self, key: str, value: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    async def _adelete_raw(self, key: str) -> None:
        pass

    @abstractmethod
    async def _aclear_raw(self) -> None:
        pass

    async def _akeys_raw(self) -> List[str]:
        raise NotImplementedError

    # ========== 统一高层异步接口（子类无需重写）==========
    async def get(self, key: str) -> Dict[str, Any]:
        try:
            data = await self._aget_raw(key)
            return {ke.KEY_SUCCESS: True, ke.KEY_DATA: data, ke.KEY_ERROR: None}
        except Exception as e:
            logger.error(f"从缓存获取数据失败，键名: {key}, 错误详情: {e}")
            return {ke.KEY_SUCCESS: False, ke.KEY_DATA: None, ke.KEY_ERROR: str(e)}

    async def set(self, key: str, value: Dict[str, Any]) -> Dict[str, Any]:
        try:
            await self._aset_raw(key, value)
            return {ke.KEY_SUCCESS: True, ke.KEY_DATA: None, ke.KEY_ERROR: None}
        except Exception as e:
            logger.error(f"向缓存写入数据失败，键名: {key}, 错误详情: {e}")
            return {ke.KEY_SUCCESS: False, ke.KEY_DATA: None, ke.KEY_ERROR: str(e)}

    async def delete(self, key: str) -> Dict[str, Any]:
        try:
            await self._adelete_raw(key)
            return {ke.KEY_SUCCESS: True, ke.KEY_DATA: None, ke.KEY_ERROR: None}
        except Exception as e:
            logger.error(f"删除缓存数据失败，键名: {key}, 错误详情: {e}")
            return {ke.KEY_SUCCESS: False, ke.KEY_DATA: None, ke.KEY_ERROR: str(e)}

    async def clear(self) -> Dict[str, Any]:
        try:
            await self._aclear_raw()
            return {ke.KEY_SUCCESS: True, ke.KEY_DATA: None, ke.KEY_ERROR: None}
        except Exception as e:
            logger.error(f"清空缓存失败，错误详情: {e}")
            return {ke.KEY_SUCCESS: False, ke.KEY_DATA: None, ke.KEY_ERROR: str(e)}
