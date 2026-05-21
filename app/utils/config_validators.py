from typing import Optional, Dict, Tuple, Any


class ConfigValidator:
    """通用配置校验工具（无状态，全部为静态方法）"""

    # ==================== 基础类型校验 ====================

    @staticmethod
    def type_check(errors: list, d: dict, key: str, expected_type: type) -> None:
        v = d.get(key)
        if v is not None and not isinstance(v, expected_type):
            errors.append(f"{key} 必须是 {expected_type.__name__} 类型")

    @staticmethod
    def int_check(errors: list, d: dict, key: str, min_val: Optional[int] = None,
                  max_val: Optional[int] = None) -> None:
        v = d.get(key)
        if v is not None:
            if not isinstance(v, int):
                errors.append(f"{key} 必须是整数")
            else:
                if min_val is not None and v < min_val:
                    errors.append(f"{key} 不能小于 {min_val}")
                if max_val is not None and v > max_val:
                    errors.append(f"{key} 不能大于 {max_val}")

    @staticmethod
    def float_check(errors: list, d: dict, key: str, min_val: Optional[float] = None,
                    max_val: Optional[float] = None) -> None:
        v = d.get(key)
        if v is not None:
            if not isinstance(v, (int, float)):
                errors.append(f"{key} 必须是数字")
            else:
                if min_val is not None and v < min_val:
                    errors.append(f"{key} 不能小于 {min_val}")
                if max_val is not None and v > max_val:
                    errors.append(f"{key} 不能大于 {max_val}")

    @staticmethod
    def bool_check(errors: list, d: dict, key: str) -> None:
        v = d.get(key)
        if v is not None and not isinstance(v, bool):
            errors.append(f"{key} 必须是布尔值")

    @staticmethod
    def str_check(errors: list, d: dict, key: str) -> None:
        v = d.get(key)
        if v is not None and not isinstance(v, str):
            errors.append(f"{key} 必须是字符串")

    @staticmethod
    def list_check(errors: list, d: dict, key: str) -> None:
        v = d.get(key)
        if v is not None and not isinstance(v, list):
            errors.append(f"{key} 必须是列表")

    @staticmethod
    def dict_check(errors: list, d: dict, key: str) -> None:
        v = d.get(key)
        if v is not None and not isinstance(v, dict):
            errors.append(f"{key} 必须是字典")

    # ==================== 特定场景校验 ====================

    @staticmethod
    def model_valid_check(errors: list, d: dict, key: str, valid_set: set) -> None:
        """校验值是否在合法集合中"""
        v = d.get(key)
        if v is not None and isinstance(v, str) and v not in valid_set:
            errors.append(f"{key} 不是合法值，当前可用：{sorted(valid_set)}")

    @staticmethod
    def comma_separated_str_list_check(errors: list, d: dict, key: str) -> None:
        """校验逗号分隔的字符串列表（每个元素必须是非空字符串）"""
        v = d.get(key)
        if v is None:
            return
        if not isinstance(v, list):
            errors.append(f"{key} 必须是列表")
            return
        for item in v:
            if not isinstance(item, str) or not item.strip():
                errors.append(f"{key} 的列表项必须是非空字符串")

    @staticmethod
    def channels_valid_check(errors: list, d: dict, key: str, valid_set: set) -> None:
        """校验通知渠道列表是否合法"""
        v = d.get(key)
        if v is None:
            return
        if not isinstance(v, list):
            errors.append(f"{key} 必须是列表")
            return
        for ch in v:
            if ch not in valid_set:
                errors.append(f"无效的通知渠道 '{ch}'，可选: {valid_set}")

    # ==================== 批量执行入口 ====================

    @staticmethod
    def run_checks(errors: list, d: dict, checks: list) -> None:
        """
        批量执行校验规则。
        checks 中每一项为 (method, args) 或 (method, args, kwargs)。
        """
        for check in checks:
            method = check[0]
            args = check[1] if len(check) > 1 else ()
            kwargs = check[2] if len(check) > 2 else {}
            method(errors, d, *args, **kwargs)

    @staticmethod
    def structure_check(errors: list, d: dict, key: str, rules: Dict[str, Tuple[type, bool]]) -> Any:
        """
        通用结构化校验。
        rules: 字典，键是字段名，值是 (期望类型, 是否必填)。
        返回该字段的值，若校验失败则返回 None。
        """
        item = d.get(key)
        if item is None:
            if any(req for _, req in rules.values()):
                errors.append(f"缺少 '{key}' 字段")
            return None
        if not isinstance(item, dict):
            errors.append(f"'{key}' 必须是对象")
            return None

        for field, (expected_type, required) in rules.items():
            if field not in item:
                if required:
                    errors.append(f"'{key}.{field}' 不能为空")
                continue
            value = item[field]
            if not isinstance(value, expected_type):
                errors.append(f"'{key}.{field}' 必须是 {expected_type.__name__} 类型")
        return item
