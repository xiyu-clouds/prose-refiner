from typing import Dict, Any
from app.common import paths as pa
from app.config.config import config
from app.utils.file_util import FileUtil
from app.utils.logger import LoggerManager as logger


class ConfigLoader:
    """文本配置加载器（单例）"""
    CHINESE_NAME = "文本配置加载器"

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache = {}
            cls._instance._file_util = FileUtil()
        return cls._instance

    def get_punctuation_rules(self) -> Dict[str, Any]:
        """获取标点规则配置"""
        return self._load(pa.FILE_PUNCTUATION_RULES_JSON)

    def get_spell_rules(self) -> Dict[str, Any]:
        """获取拼写规则配置"""
        return self._load(pa.FILE_SPELL_RULES_JSON)

    def get_analysis_rules(self) -> Dict[str, Any]:
        """获取分析规则配置"""
        return self._load(pa.FILE_ANALYSIS_RULES_JSON)

    def _load(self, filename: str) -> Dict[str, Any]:
        """加载配置，优先从缓存读取"""
        if filename not in self._cache:
            real_path = config.get_config_path(filename)
            logger.debug(f"加载配置文件到缓存: {real_path} (Key: {filename})", module_name=self.CHINESE_NAME)
            self._cache[filename] = self._file_util.read_json_file(real_path)
        return self._cache[filename]

    def clear(self, filename: str = None):
        """根据文件名清除缓存"""
        if filename:
            self._cache.pop(filename, None)
            logger.info(f"已清除配置缓存 (Key: {filename})", module_name=self.CHINESE_NAME)
        else:
            self._cache.clear()
            logger.info("已清除所有配置缓存", module_name=self.CHINESE_NAME)

    def reload(self, filename: str) -> None:
        """
        热重载配置：清除指定路径的缓存，并重新加载。
        """
        self.clear(filename)
        self._load(filename)
        logger.info(f"已热重载配置 (Key: {filename})", module_name=self.CHINESE_NAME)
