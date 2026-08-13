import hashlib
import json
import threading
from typing import Dict, Any, List, Union, Tuple, FrozenSet, Optional, Set, Callable
from app.common import keys as ke
from app.common import values as va
from app.common.enums import ValidationRule
from app.utils.logger import LoggerManager as logger


class UniversalDataValidator:
    """
    轻量级数据校验引擎

    核心职责：
    1. 路径解析：支持点号 (.) 和通配符 (*)。
    2. 自动修复：标量转列表、字符串转数字等。
    3. 语义清理：动态过滤无意义占位符。
    4. 类型校验：严格类型检查。
    5. 业务适配：通过回调机制透明调用外部逻辑。
    """

    CHINESE_NAME = "通用数据校验引擎"

    # --- 单例工厂相关 ---
    _instances: Dict[str, 'UniversalDataValidator'] = {}
    _lock = threading.Lock()

    DEFAULT_SEMANTIC_NULLS: FrozenSet[str] = frozenset([
        "未提及", "未知", "待定", "不清楚", "无", "没有", "暂无", "不详", "未说明",
        "无明确描述", "无描述", "没有描述", "没有描述内容", "null",
        "none", "unknown", "unspecified", "n/a", "na", "—", "-", "…", "...", ""
    ])

    def __init__(self, auto_repair: bool = True,
                 semantic_nulls: Optional[Union[Set[str], FrozenSet[str], List[str]]] = None):
        """
        初始化校验器。

        :param auto_repair: 是否启用自动修复模式（默认 True）。
        :param semantic_nulls: 自定义的“语义空值”集合。
                               如果传入，将覆盖默认值；如果为 None，则使用默认值。
                               用于过滤模型生成的“无信息”占位符（如 "未知", "N/A" 等）。
        """
        self.auto_repair = auto_repair
        # 统一转换为 frozenset 以提高查找效率
        if semantic_nulls is not None:
            self.semantic_nulls = frozenset(semantic_nulls)
        else:
            self.semantic_nulls = self.DEFAULT_SEMANTIC_NULLS

        logger.info(f"校验引擎初始化完成 | 自动修复={auto_repair} | 语义空值规则数={len(self.semantic_nulls)}",
                    module_name=self.CHINESE_NAME)

    @classmethod
    def _generate_cache_key(cls, auto_repair: bool,
                            semantic_nulls: Optional[Union[Set[str], FrozenSet[str], List[str]]]) -> str:
        """
        生成稳定的缓存 Key。
        策略：将配置序列化为字符串，计算 MD5 前 8 位。
        优点：跨进程稳定，内容相同则 Key 相同，避免 hash() 随机化问题。
        """
        # 1. 处理 auto_repair
        ar_str = "1" if auto_repair else "0"

        # 2. 处理 semantic_nulls
        if semantic_nulls is None:
            # 使用默认值的指纹
            # 注意：这里我们直接标记为 "DEFAULT"，因为默认值是类常量，不会变
            ns_hash = "DEFAULT"
        else:
            # 将集合转为排序后的元组，确保 {A, B} 和 {B, A} 生成相同指纹
            try:
                sorted_items = tuple(sorted(list(semantic_nulls)))
                # 序列化为字符串
                content_str = json.dumps(sorted_items, ensure_ascii=False, sort_keys=True)
                # 计算 MD5 并取前 8 位 (足够唯一且短)
                ns_hash = hashlib.md5(content_str.encode(ke.KEY_UTF_8)).hexdigest()[:8]
            except TypeError:
                # 极端情况：包含不可序列化对象， fallback 到 id (不推荐但保底)
                ns_hash = f"OBJ_{id(semantic_nulls)}"

        return f"v1_ar{ar_str}_ns{ns_hash}"

    @classmethod
    def get_instance(cls, auto_repair: bool = True,
                     semantic_nulls: Optional[Union[Set[str],FrozenSet[str], List[str]]] = None) -> 'UniversalDataValidator':
        """
        【唯一入口】根据配置获取单例。
        """
        # 生成稳定 Key
        cache_key = cls._generate_cache_key(auto_repair, semantic_nulls)

        with cls._lock:
            if cache_key not in cls._instances:
                count = len(semantic_nulls) if semantic_nulls else len(cls.DEFAULT_SEMANTIC_NULLS)
                logger.info(f"初始化校验引擎实例 [Key:{cache_key}] | 修复={auto_repair} | 空值数={count}",
                            module_name=cls.CHINESE_NAME)
                cls._instances[cache_key] = cls(auto_repair=auto_repair, semantic_nulls=semantic_nulls)

            return cls._instances[cache_key]

    @classmethod
    def clear_cache(cls):
        """【测试专用】清空所有缓存实例"""
        with cls._lock:
            cls._instances.clear()
        logger.warning("校验引擎单例缓存已重置", module_name=cls.CHINESE_NAME)

    # --- 工具方法 ---
    @staticmethod
    def _split_path(path: str) -> tuple:
        """将 'a.b.c' 或 'list.*.id' 分割为元组"""
        return tuple(path.split('.'))

    def deep_get(self, data: Any, path: str) -> Any:
        """
        深度获取数据。支持通配符 '*' 遍历列表。
        如果路径不存在或中途类型不匹配，返回 None。
        """
        keys = self._split_path(path)
        for key in keys:
            try:
                if isinstance(data, dict):
                    if key in data:
                        data = data[key]
                    else:
                        return None
                elif isinstance(data, list):
                    if key == '*':
                        # 通配符：递归获取剩余路径并收集结果
                        next_vals = []
                        rest = '.'.join(keys[keys.index('*') + 1:])
                        for item in data:
                            sub_val = self.deep_get(item, rest)
                            next_vals.append(sub_val)
                        return next_vals
                    else:
                        # 列表需要整数索引，这里收到字符串且非 '*'，视为无效
                        return None
                else:
                    # 当前值不是容器，无法继续深入
                    return None
            except Exception as e:
                return None
        return data

    def expand_wildcard_paths(self, data: Any, path: str) -> List[Tuple[str, Any]]:
        """
        展开通配符路径，返回所有匹配的具体路径和值的列表。
        返回格式：[ ("key[0].subkey", value), ("key[1].subkey", value), ... ]
        """

        def _recurse(current_data, keys, current_path):
            if not keys:
                return [(current_path, current_data)]
            key, rest_keys = keys[0], keys[1:]
            results = []
            if key == '*':
                if isinstance(current_data, list):
                    for i, item in enumerate(current_data):
                        # 构建新路径：如果是根路径直接 [i]，否则追加 .[i]
                        new_path = f"{current_path}[{i}]" if current_path else f"[{i}]"
                        results.extend(_recurse(item, rest_keys, new_path))
            else:
                if isinstance(current_data, dict) and key in current_data:
                    new_path = f"{current_path}.{key}" if current_path else key
                    results.extend(_recurse(current_data[key], rest_keys, new_path))
            return results

        keys = self._split_path(path)
        return _recurse(data, keys, "")

    def deep_set(self, data: Any, path: str, value: Any) -> None:
        """
        【核心功能】深度设置数据值。

        作用：
        根据点号分隔的路径（如 'user.profile.name' 或 'items[0].id'），
        在嵌套的字典/列表结构中修改或创建节点，并赋值为 value。

        特性：
        1. 自动创建中间缺失的字典节点。
        2. 支持列表整数索引访问。
        3. 遇到类型不匹配或越界时，记录中文警告并安全退出，不抛出异常。

        :param data: 根数据对象 (dict 或 list)
        :param path: 路径字符串 (e.g., "a.b[0].c")
        :param value: 要设置的值
        """
        keys = self._split_path(path)
        current = data

        # 遍历除了最后一个 key 之外的所有层级，目的是“导航”到父容器
        for i, key in enumerate(keys[:-1]):
            next_key = key
            is_int_key = False

            # --- 处理列表索引 ---
            if isinstance(current, list):
                try:
                    idx = int(key)
                    if 0 <= idx < len(current):
                        next_key = idx
                        is_int_key = True
                    else:
                        # 列表索引越界
                        logger.warning(
                            f"deep_set 中止：列表索引越界 '{key}' (路径：{path})。当前列表长度：{len(current)}",
                            module_name=self.CHINESE_NAME
                        )
                        return
                except ValueError:
                    # 试图用非数字字符串访问列表
                    logger.warning(
                        f"deep_set 中止：无法使用非整数键 '{key}' 访问列表 (路径：{path})",
                        module_name=self.CHINESE_NAME
                    )
                    return
            # --- 导航到下一层 ---
            if isinstance(current, dict):
                if next_key not in current:
                    # 关键节点缺失：保守创建一个空字典作为占位，以便后续写入
                    # 注意：如果最终目标是列表，这里创建字典可能会导致结构错误，但通常 LLM 输出以 dict 为主
                    current[next_key] = {}
                current = current[next_key]
            elif isinstance(current, list) and is_int_key:
                # 已进入列表内部，移动到该元素
                current = current[next_key]
            else:
                # 类型不匹配：例如当前是字符串，却还想继续深入访问
                logger.warning(
                    f"deep_set 中止：在路径 '{key}' 处遇到不支持的容器类型 (当前类型：{type(current).__name__}, 路径：{path})",
                    module_name=self.CHINESE_NAME
                )
                return

        # --- 设置最终值 ---
        final_key = keys[-1]
        if isinstance(current, dict):
            current[final_key] = value
        elif isinstance(current, list):
            try:
                idx = int(final_key)
                if 0 <= idx < len(current):
                    current[idx] = value
                else:
                    logger.warning(
                        f"deep_set 失败：最终索引越界 '{final_key}' (路径：{path})",
                        module_name=self.CHINESE_NAME
                    )
            except ValueError:
                logger.warning(
                    f"deep_set 失败：无法使用非整数键 '{final_key}' 设置列表值 (路径：{path})",
                    module_name=self.CHINESE_NAME
                )
        else:
            logger.warning(
                f"deep_set 失败：目标路径的父节点不是容器 (类型：{type(current).__name__}, 路径：{path})",
                module_name=self.CHINESE_NAME
            )

    def _is_semantic_empty(self, value: Any) -> bool:
        """
        判断值是否为“语义空”。
        利用构造函数注入的 self.semantic_nulls 进行动态判断。
        """
        if value is None:
            return True
        if isinstance(value, str):
            s = value.strip()
            return s == "" or s in self.semantic_nulls
        if isinstance(value, (list, dict)) and len(value) == 0:
            return True
        return False

    def _is_empty(self, value: Any) -> bool:
        return self._is_semantic_empty(value)

    def remove_nulls(self, data: Any) -> Any:
        """
        递归清理数据中的语义空值。
        - 字符串若在黑名单中 -> 变为 None
        - 空列表/字典 -> 变为 None
        - 字典/列表中若子元素变为 None -> 移除该子元素
        """
        if isinstance(data, (str, int, float, bool)):
            return None if self._is_semantic_empty(data) else data

        if isinstance(data, dict):
            cleaned = {
                k: self.remove_nulls(v)
                for k, v in data.items()
            }
            cleaned = {k: v for k, v in cleaned.items() if v is not None}
            return cleaned if cleaned else None

        if isinstance(data, list):
            cleaned = [self.remove_nulls(item) for item in data]
            cleaned = [x for x in cleaned if x is not None]
            return cleaned if cleaned else None

        return None if self._is_semantic_empty(data) else data

    @staticmethod
    def remove_meta_fields(data: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in data.items() if not k.startswith("__")}

    def _maybe_repair_value(self, value: Any, field_path: str, validator: Any) -> Any:
        """
        尝试根据期望的校验器类型，自动修复值。
        仅当 self.auto_repair 为 True 时生效。
        """
        if not self.auto_repair or value is None:
            return value

        # 获取 validator 名称
        validator_name = getattr(validator, '__name__', str(validator))

        # --- 期望是 LIST ---
        if validator_name == ke.KEY_IS_LIST:
            if isinstance(value, list):
                return value
            # 标量或单对象包装为列表
            if isinstance(value, (str, int, float, bool, dict)):
                logger.debug(f"自动修复 [{field_path}]: 将单一值包装为列表", module_name=self.CHINESE_NAME)
                return [value]
            if isinstance(value, tuple):
                logger.debug(f"自动修复 [{field_path}]: 将元组转换为列表", module_name=self.CHINESE_NAME)
                return list(value)
            return value

        # --- 期望是 STR ---
        if validator_name == ke.KEY_IS_STR:
            if isinstance(value, str):
                return value
            if isinstance(value, (int, float, bool)):
                logger.debug(f"自动修复 [{field_path}]: 将数值/布尔转换为字符串", module_name=self.CHINESE_NAME)
                return str(value)
            return value

        # --- 期望是 INT ---
        if validator_name == ke.KEY_IS_INT:
            if isinstance(value, int) and not isinstance(value, bool):
                return value
            if isinstance(value, str):
                try:
                    # 去除空格并尝试转换
                    clean_s = value.strip()
                    if clean_s.isdigit() or (clean_s.startswith('-') and clean_s[1:].isdigit()):
                        repaired = int(clean_s)
                        logger.debug(f"自动修复 [{field_path}]: 将字符串 '{clean_s}' 转换为整数", module_name=self.CHINESE_NAME)
                        return repaired
                except Exception:
                    pass
            return value

        # --- 期望是 FLOAT ---
        if validator_name == ke.KEY_IS_FLOAT:
            if isinstance(value, float):
                return value
            if isinstance(value, (int, str)) and not isinstance(value, bool):
                try:
                    repaired = float(value)
                    logger.debug(f"自动修复 [{field_path}]: 转换为浮点数", module_name=self.CHINESE_NAME)
                    return repaired
                except Exception:
                    pass
            return value

        # --- 期望是 BOOL ---
        if validator_name == ke.KEY_IS_BOOL:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                v_lower = value.strip().lower()
                if v_lower in {ke.KEY_TRUE, ke.KEY_1, ke.KEY_YES, ke.KEY_ON}:
                    logger.debug(f"自动修复 [{field_path}]: 将字符串识别为 True", module_name=self.CHINESE_NAME)
                    return True
                elif v_lower in {ke.KEY_FALSE, ke.KEY_0, ke.KEY_NO, ke.KEY_OFF}:
                    logger.debug(f"自动修复 [{field_path}]: 将字符串识别为 False", module_name=self.CHINESE_NAME)
                    return False
            return value

        return value

    def _validate_single_field(self, value: Any, path: str, required: bool, validator: Any) -> List[str]:
        errors = []
        if required:
            if value is None or (isinstance(value, list) and len(value) == 0):
                errors.append(f"[{path}] 必填项缺失或为空")
                return errors

        if not required and self._is_semantic_empty(value):
            return errors

        try:
            if isinstance(validator, type):
                if validator == int:
                    valid = isinstance(value, int) and not isinstance(value, bool)
                elif validator == bool:
                    valid = isinstance(value, bool)
                else:
                    valid = isinstance(value, validator)
            elif callable(validator):
                valid = validator(value)
            else:
                errors.append(f"[{path}] 校验器配置错误")
                return errors

            if not valid:
                exp = getattr(validator, '__name__', str(validator))
                act = type(value).__name__
                val_repr = repr(value)[:50] + "..." if len(repr(value)) > 50 else repr(value)
                errors.append(f"[{path}] 类型不匹配：期望<{exp}>，实际<{act}> (值：{val_repr})")
        except Exception as e:
            errors.append(f"[{path}] 校验异常：{e}")
        return errors

    def _extract_value_from_wrapped_dict(self, wrapped_value: Dict[str, Any], expected_type_str: str) -> Any:
        """
        【分层优先级版】尝试从包裹型字典中提取符合期望类型的真实值。

        执行顺序：
        1. 扫描 HIGH_PRIORITY_KEYS (命中即返回)
        2. 扫描 MEDIUM_PRIORITY_KEYS (命中即返回)
        3. 扫描 LOW_PRIORITY_KEYS (仅在单键字典且类型匹配时返回)
        4. 兜底：如果是单键字典 (无论键名)，且类型匹配，强制解包 (防漏网之鱼)
        """
        if not isinstance(wrapped_value, dict):
            return wrapped_value

        # 如果 wrapped_value 本身已经符合期望类型，直接返回，避免多余解包
        if self._matches_type(wrapped_value, expected_type_str):
            return wrapped_value

        # --- 步骤 1: 检查高优先级键 (纯容器) ---
        for key in va.VAL_HIGH_PRIORITY_KEYS:
            if key in wrapped_value:
                candidate = wrapped_value[key]
                if self._matches_type(candidate, expected_type_str):
                    return candidate  # 直接返回，不再检查后续

        # --- 步骤 2: 检查中优先级键 (类型标记) ---
        for key in va.VAL_MEDIUM_PRIORITY_KEYS:
            if key in wrapped_value:
                candidate = wrapped_value[key]
                if self._matches_type(candidate, expected_type_str):
                    return candidate  # 直接返回

        # --- 步骤 3: 检查低优先级键 (语义业务词) ---
        # 策略更保守：只有当这个键是字典里唯一的键，或者值看起来非常像目标类型时才提取
        for key in va.VAL_LOW_PRIORITY_KEYS:
            if key in wrapped_value:
                candidate = wrapped_value[key]
                # 额外检查：如果是多键字典，且键是低优先级的，我们倾向于认为它是业务字段，不解包
                # 除非它是单键字典
                if len(wrapped_value) == 1 and self._matches_type(candidate, expected_type_str):
                    return candidate

                # 或者：如果该键对应的值类型匹配，且其他键都是明显的元数据 (这里简化处理，主要靠单键判断)
                # 为了安全，低优先级键主要依赖“单键字典”策略

        # --- 步骤 4: 兜底策略 (单键字典强力解包) ---
        # 如果上面都没命中，但字典只有一个元素，且值类型匹配 -> 强制解包
        # 这能捕获那些键名不在列表里的奇葩情况 (如 {'confidence_val': 0.85})
        if len(wrapped_value) == 1:
            key, candidate = next(iter(wrapped_value.items()))
            if self._matches_type(candidate, expected_type_str):
                # 再次确认：如果键名看起来像复杂的业务对象 (可选过滤)，可以跳过
                # 但为了最大化修复率，这里直接返回
                return candidate

        # --- 步骤 5: 递归解包 (防御嵌套) ---
        # 如果提取出的值（或者原字典）还是个 dict，且我们要的不是 dict，试着再解一层
        # 注意：这里只对原字典进行递归尝试，避免死循环
        if expected_type_str != ke.KEY_DICT:
            # 尝试对原字典的所有值进行递归检查 (防止嵌套在未知键里)
            # 这是一个比较激进的尝试，仅当所有上述策略都失败时
            for k, v in wrapped_value.items():
                if isinstance(v, dict):
                    deeper = self._extract_value_from_wrapped_dict(v, expected_type_str)
                    if deeper != v and self._matches_type(deeper, expected_type_str):
                        return deeper

        # 无法提取，返回原字典
        return wrapped_value

    @staticmethod
    def _matches_type(value: Any, type_str: str) -> bool:
        """辅助函数：判断值是否符合期望的类型字符串"""
        # 处理 None 情况
        if value is None:
            return False

        if type_str == ke.KEY_STR:
            return isinstance(value, str)
        elif type_str == ke.KEY_INT:
            return isinstance(value, int) and not isinstance(value, bool)
        elif type_str == ke.KEY_FLOAT:
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        elif type_str == ke.KEY_BOOL:
            return isinstance(value, bool)
        elif type_str == ke.KEY_DICT:
            return isinstance(value, dict)
        elif type_str == ke.KEY_LIST:
            return isinstance(value, list)
        elif type_str == ke.KEY_ANY:
            return True

        return False

    def _recursive_smart_fix_internal(self, data: Any, config: Dict[str, str], current_path: str = "") -> None:
        """
        递归遍历数据结构，原地修复被过度包装的字段。

        :param data: 当前处理的数据节点 (dict, list, or primitive)
        :param current_path: 当前路径字符串 (用于日志调试)
        """
        if isinstance(data, dict):
            # 先处理当前层级的键
            for key in list(data.keys()):
                value = data[key]
                path = f"{current_path}.{key}" if current_path else key

                # 1. 检查是否在监控列表中 (使用传入的 config)
                if key in config:
                    expected_type = config[key]
                    original_val = value

                    # 尝试修复
                    if isinstance(value, dict):  # 只有字典才需要解包
                        fixed_val = self._extract_value_from_wrapped_dict(value, expected_type)

                        if fixed_val is not original_val:
                            logger.info(f"[解包修复] 路径 '{path}': {original_val} -> {fixed_val}", module_name=self.CHINESE_NAME)
                            data[key] = fixed_val
                            value = fixed_val

                # 2. 无论是否修复，都要递归进入子结构
                if isinstance(value, dict):
                    self._recursive_smart_fix_internal(value, config, path)
                elif isinstance(value, list):
                    for idx, item in enumerate(value):
                        item_path = f"{path}[{idx}]"
                        if isinstance(item, (dict, list)):
                            self._recursive_smart_fix_internal(item, config, item_path)

        elif isinstance(data, list):
            for idx, item in enumerate(data):
                item_path = f"{current_path}[{idx}]"
                if isinstance(item, (dict, list)):
                    self._recursive_smart_fix_internal(item, config, item_path)

    # --- 对外接口 ---
    def validate(
            self,
            data: Dict[str, Any],
            rules: List[ValidationRule],
            monitored_fields_config: Optional[Dict[str, str]] = None,
            pre_process_callback: Optional[Callable[[Dict], None]] = None,
            post_process_callback: Optional[Callable[[Dict], None]] = None,
            force_post_process: bool = False
    ) -> Dict[str, Any]:
        """
        纯净校验入口。

        :param data: 待校验数据
        :param rules: 校验规则列表 (由调用方直接提供)
        :param monitored_fields_config: 监控字段 (由调用方直接提供，用于前置进行解包)
        :param pre_process_callback: 前置处理 (如清洗)
        :param post_process_callback: 后置处理 (如去重)
        :param force_post_process: 即使校验失败也执行后置处理
        """
        if data is None:
            logger.error("输入数据为 None", module_name=self.CHINESE_NAME)
            return {ke.KEY_IS_VALID: False, ke.KEY_ERRORS: ["输入数据为 None"], ke.KEY_CLEANED_DATA: None}

        # 基础清理，递归移除空值，与校验规则必填冲突了
        # cleaned_data = self.remove_nulls(data)

        if monitored_fields_config:
            logger.debug(f"[通用解包] 开始扫描 (监控字段: {list(monitored_fields_config.keys())})", module_name=self.CHINESE_NAME)
            # 调用内置的递归修复函数
            self._recursive_smart_fix_internal(data, monitored_fields_config)
            logger.debug("[通用解包] 扫描完成。", module_name=self.CHINESE_NAME)

        # 前置处理 (清洗引号等)
        if pre_process_callback:
            try:
                pre_process_callback(data)
            except Exception as e:
                logger.error(f"前置处理回调失败：{e}", module_name=self.CHINESE_NAME)

        all_errors = []

        # 核心循环
        for rule in rules:
            field_path = rule.path
            required = rule.required
            validator = rule.validator

            # 展开通配符或单点获取
            if '*' in field_path:
                concrete_items = self.expand_wildcard_paths(data, field_path)
                for concrete_path, value in concrete_items:
                    # 路径格式化
                    dot_path = concrete_path.replace('[', '.').replace(']', '')

                    # 自动修复
                    repaired_value = self._maybe_repair_value(value, concrete_path, validator)
                    if repaired_value != value:
                        self.deep_set(data, dot_path, repaired_value)
                        value = repaired_value

                    # 校验
                    field_errors = self._validate_single_field(value, dot_path, required, validator)
                    all_errors.extend(field_errors)
            else:
                value = self.deep_get(data, field_path)

                # 自动修复
                repaired_value = self._maybe_repair_value(value, field_path, validator)
                if repaired_value != value:
                    self.deep_set(data, field_path, repaired_value)
                    value = repaired_value

                # 校验
                field_errors = self._validate_single_field(value, field_path, required, validator)
                all_errors.extend(field_errors)

        is_valid = len(all_errors) == 0

        # 后置处理 (去重统计)
        should_run_post = (post_process_callback is not None) and (force_post_process or is_valid)

        if should_run_post:
            try:
                post_process_callback(data)
            except Exception as e:
                logger.error(f"后置处理回调失败：{e}", module_name=self.CHINESE_NAME)
                if not force_post_process:
                    all_errors.append(f"后置处理异常：{e}")
                    is_valid = False

        # 日志
        if is_valid:
            logger.info("校验通过", module_name=self.CHINESE_NAME)
        else:
            logger.warning(f"校验失败 ({len(all_errors)} 错误)", module_name=self.CHINESE_NAME)
            for err in all_errors[:3]:
                logger.debug(f"   - {err}", module_name=self.CHINESE_NAME)

        return {
            ke.KEY_IS_VALID: is_valid,
            ke.KEY_ERRORS: all_errors,
            ke.KEY_CLEANED_DATA: data
        }
