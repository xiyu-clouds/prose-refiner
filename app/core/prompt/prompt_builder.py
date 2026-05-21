import json
import hashlib
import threading
from app.common import paths as pa
from typing import Dict, Any, Optional, List, Set
from app.common import keys as ke
from app.config.config import config
from app.utils.file_util import FileUtil
from app.utils.logger import LoggerManager as logger
from app.utils.prompt_util import wrap_static_json


class PromptBuilder:
    """通用 Prompt 组装器（单例、线程安全、支持模板变量和宪法注入）"""
    CHINESE_NAME = "Prompt 构造器"
    _instance: Optional["PromptBuilder"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "PromptBuilder":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._file_util = FileUtil()

        # 双缓存分离
        self._prompt_cache: Dict[str, Dict[str, Any]] = {}
        self._plugins_cache: Dict[str, Dict[str, Any]] = {}

        # 双索引分离
        self._prompt_ids_by_type: Dict[str, List[str]] = {}
        self._plugins_ids_by_type: Dict[str, List[str]] = {}

        self._dao_data: Dict[str, Any] = {}  # 宪法原始数据
        self._dao_hash: str = ""  # 宪法内容哈希，用于缓存失效
        self._load_dao()

        self._prompts_loaded: bool = False
        self._plugins_loaded: bool = False

    # ==================== 宪法管理 ====================
    def _load_dao(self):
        try:
            raw = self._file_util.read_file(config.PATH_FILE_THE_WAY_JSON)
            self._dao_data = json.loads(raw) if raw else {}
            self._dao_hash = hashlib.md5(raw.encode(ke.KEY_UTF_8)).hexdigest()
            logger.info(f"✅ 宪法加载成功，哈希: {self._dao_hash[:8]}", module_name=self.CHINESE_NAME)
        except Exception as e:
            logger.critical(f"❌ 宪法加载失败，将使用空宪法: {e}", module_name=self.CHINESE_NAME)
            self._dao_data = {}
            self._dao_hash = ""

    def build_dao_section(self) -> str:
        """构建宪法注入段落（仅包含核心内容，无冗余标题）"""
        dao_core = self._dao_data.get(ke.KEY_DAO, {})
        if not dao_core:
            return ""

        parts = []
        # 核心真理
        statement = dao_core.get(ke.KEY_STATEMENT)
        if statement:
            parts.append(f"**核心真理**：{statement}")

        # 阐释（可能是字符串或列表）
        elaboration = dao_core.get(ke.KEY_ELABORATION)
        if elaboration:
            if isinstance(elaboration, list):
                parts.append("**阐释**：")
                parts.extend([f"- {item}" for item in elaboration])
            else:
                parts.append(f"**阐释**：{elaboration}")

        # 存在性公理
        axioms = dao_core.get(ke.KEY_ONTOLOGICAL_AXIOMS, [])
        if axioms:
            parts.append("**存在性公理**：")
            parts.extend([f"- {ax}" for ax in axioms])

        # 最高指令
        directive = self._dao_data.get(ke.KEY_SUPREME_DIRECTIVE)
        if directive:
            parts.append("\n### 最高行动指令")
            if isinstance(directive, list):
                parts.extend(directive)
            else:
                parts.append(str(directive))

        return "\n".join(parts)

    # ==================== 缓存键生成 ====================
    def _cache_key(self, c: str) -> str:
        """缓存键 = 配置ID + 宪法哈希，宪法更新后自动失效"""
        return f"{c}:{self._dao_hash}"

    # ==================== 核心组装 ====================
    def build_prompt(self, cfg: Dict[str, Any]) -> str:
        parts = []

        # 1. 道（宪法注入）— 最顶层，全局价值观起点
        if cfg.get(ke.KEY_META_CONSTITUTION_INJECTED):
            dao_section = self.build_dao_section()
            if dao_section:
                parts.append(f"### 道\n{dao_section}")

        # 2. 角色
        role = cfg.get(ke.KEY_ROLE)
        if role:
            parts.append(f"【角色】\n{role.strip()}")

        # 3. 任务（description 注入）
        description = cfg.get("description")
        if description:
            parts.append(f"【任务】\n{description.strip()}")

        # 4. 核心原则
        info_source = cfg.get(ke.KEY_INFORMATION_SOURCE)
        if info_source:
            parts.append(f"### 核心原则\n{info_source.strip()}")

        # 5. 执行规则
        rules = cfg.get(ke.KEY_RULES, [])
        if rules:
            parts.append("### 执行规则\n" + "\n".join(rules))

        # 6. 输出前缀
        prefix = cfg.get(ke.KEY_OUTPUT_PREFIX, [])
        if prefix:
            parts.append("\n".join(prefix))

        # 7. 输出 Schema
        schema = cfg.get(ke.KEY_OUTPUT_SCHEMA)
        if schema and schema != {ke.KEY_SUCCESS: False}:
            schema_json = json.dumps(schema, ensure_ascii=False, indent=2)
            parts.append(wrap_static_json(schema_json))

        # 8. 空结果回退
        fallback = cfg.get(ke.KEY_EMPTY_RESULT_FALLBACK)
        if fallback and fallback.strip():
            parts.append(f"### 若无法生成有效结果或不存在任何标记的问题，请返回\n{wrap_static_json(fallback.strip())}")

        # 9. 输出后缀
        suffix = cfg.get(ke.KEY_OUTPUT_SUFFIX, [])
        if suffix:
            parts.append("\n".join(suffix))

        return "\n\n".join(filter(None, parts)).strip()

    # ==================== 通用加载逻辑 ====================
    def _load_config(self, path: str, ids_by_type: Dict[str, List[str]], cache: Dict[str, Dict[str, Any]]) -> bool:
        """通用配置加载逻辑，返回是否成功"""
        raw_content = self._file_util.read_file(path, auto_decode=True)
        if not raw_content.strip():
            logger.warning(f"⚠️ 配置文件为空: {path}", module_name=self.CHINESE_NAME)
            return False

        data = json.loads(raw_content)
        configs = data.get(ke.KEY_PROMPTS, [])

        cache.clear()
        ids_by_type.clear()
        valid_configs = []

        for c in configs:
            if not isinstance(c, dict):
                continue
            if ke.KEY_ID not in c or ke.KEY_TYPE not in c:
                continue
            if not c.get(ke.KEY_ENABLED, True):
                continue
            valid_configs.append(c)

        # 按 index 排序，确保执行顺序
        valid_configs.sort(key=lambda co: co.get(ke.KEY_INDEX, 9999))

        for c in valid_configs:
            pid = c[ke.KEY_ID]
            ptype = c[ke.KEY_TYPE]
            cache[pid] = c
            ids_by_type.setdefault(ptype, []).append(pid)

        return True

    def _precompile(self, cache: Dict[str, Dict[str, Any]]) -> int:
        count = 0
        for cfg in cache.values():
            if not cfg:
                continue

            pid = cfg.get("id")
            try:
                template = self.build_prompt(cfg)
                cfg[ke.KEY_PROMPT_TEMPLATE] = template
                count += 1
            except Exception as e:
                logger.error(f"❌ 配置 {pid} 组装失败：{e}", module_name=self.CHINESE_NAME)

        logger.info(f"🔨 已完成 {count} 个配置的 Prompt 预编译", module_name=self.CHINESE_NAME)
        return count

    def reload_plugins(self) -> bool:
        config.update_config_file_path(pa.FILE_PLUGINS_JSON)

        with self._lock:
            try:
                self._plugins_cache.clear()
                self._plugins_ids_by_type.clear()
                self._plugins_loaded = False

                success = self._load_config(config.PATH_FILE_PLUGINS_JSON, self._plugins_ids_by_type, self._plugins_cache)
                if not success:
                    logger.error("插件配置加载返回 False", module_name=self.CHINESE_NAME)
                    return False

                self._precompile(self._plugins_cache)
                self._plugins_loaded = True
                type_counts = {t: len(ids) for t, ids in self._plugins_ids_by_type.items()}
                logger.info(f"🔄 插件重载完成 | 类型统计: {type_counts}", module_name=self.CHINESE_NAME)
                return True
            except Exception as e:
                logger.exception(f"❌ 插件重载发生异常: {e}", module_name=self.CHINESE_NAME)
                return False

    def reload_prompts(self) -> bool:
        config.update_config_file_path(pa.FILE_PROMPTS_JSON)

        with self._lock:
            try:
                self._prompt_cache.clear()
                self._prompt_ids_by_type.clear()
                self._prompts_loaded = False

                success = self._load_config(
                    config.PATH_FILE_PROMPTS_JSON,
                    self._prompt_ids_by_type,
                    self._prompt_cache
                )
                if not success:
                    logger.error("步骤配置加载返回 False", module_name=self.CHINESE_NAME)
                    self._plugins_loaded = False
                    return False

                self._precompile(self._prompt_cache)
                self._prompts_loaded = True
                type_counts = {t: len(ids) for t, ids in self._prompt_ids_by_type.items()}
                logger.info(f"🔄 步骤重载完成 | 类型统计: {type_counts}", module_name=self.CHINESE_NAME)
                return True
            except Exception as e:
                logger.exception(f"❌ 步骤重载发生异常: {e}", module_name=self.CHINESE_NAME)
                self._prompts_loaded = False
                return False

    def reload_dao(self):
        config.update_config_file_path(pa.FILE_THE_WAY_JSON)

        with self._lock:
            try:
                self._load_dao()
                # 清空所有缓存，强制下次 get 时重建
                self._prompt_cache.clear()
                self._prompt_ids_by_type.clear()
                self._prompts_loaded = False

                self._plugins_cache.clear()
                self._plugins_ids_by_type.clear()
                self._plugins_loaded = False

                logger.info("🔄 宪法已重载，所有 Prompt 缓存已清空", module_name=self.CHINESE_NAME)
            except Exception as e:
                logger.exception(f"❌ 宪法重载异常: {e}", module_name=self.CHINESE_NAME)

    def get_ids_by_type(self, p_type: str, is_prompt: bool) -> List[str]:
        ids_by_type = self._prompt_ids_by_type if is_prompt else self._plugins_ids_by_type
        return ids_by_type.get(p_type, [])

    def get_all_types(self, is_prompt: bool) -> Set[str]:
        ids_by_type = self._prompt_ids_by_type if is_prompt else self._plugins_ids_by_type
        return set(ids_by_type.keys())

    def get_all_reasoning_types(self) -> List[str]:
        """合并步骤类型和插件类型，去重后返回, 用于渲染推理模型按类型按推理层级注入"""
        step_types = self.get_all_types(True)
        plugin_types = self.get_all_types(False)
        all_types = set(step_types) | set(plugin_types)
        return sorted(all_types)

    def get_full_config(self, id: str, is_prompt: bool) -> Optional[Dict[str, Any]]:
        cache = self._prompt_cache if is_prompt else self._plugins_cache
        return cache.get(id)

    def get_configs_by_type(self, p_type: str, is_prompt: bool) -> List[Dict[str, Any]]:
        ids = self.get_ids_by_type(p_type, is_prompt)
        cache = self._prompt_cache if is_prompt else self._plugins_cache
        return [cache[pid] for pid in ids if pid in cache]

    def get_compiled_prompt(self, id: str, is_prompt: bool) -> Optional[str]:
        """
        获取预编译后的 Prompt 模板。

        Args:
            id: 配置 ID
            is_prompt: True 获取步骤配置，False 获取插件配置

        Returns:
            编译好的 Prompt 字符串，若配置不存在则返回 None
        """
        cache = self._prompt_cache if is_prompt else self._plugins_cache
        cfg = cache.get(id)

        if not cfg:
            logger.warning(f"⚠️ 配置 {id} 不存在", module_name=self.CHINESE_NAME)
            return None

        return cfg.get(ke.KEY_PROMPT_TEMPLATE)

    def initialize(self) -> bool:
        """
        启动时调用，加载并预编译所有配置（步骤 + 插件）。
        """
        logger.info("🚀 开始初始化 PromptBuilder", module_name=self.CHINESE_NAME)

        # 加载并预编译步骤配置
        step_success = self.reload_prompts()
        if not step_success:
            logger.error("❌ 步骤配置初始化失败", module_name=self.CHINESE_NAME)
            return False

        # 加载并预编译插件配置
        plugin_success = self.reload_plugins()
        if not plugin_success:
            logger.error("❌ 插件配置初始化失败", module_name=self.CHINESE_NAME)
            return False

        logger.info("✅ PromptBuilder 初始化完成", module_name=self.CHINESE_NAME)
        return True
