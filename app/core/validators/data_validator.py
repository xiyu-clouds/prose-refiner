import re
from typing import Any, Callable, Dict, TypeVar

# =============================
# 1. 类型变量与泛型支持
# =============================

T = TypeVar('T')


# =============================
# 2. 基础类型校验器生成器
# =============================


def type_validator(expected_type: type) -> Callable[[Any], bool]:
    """
    生成一个类型校验器。
    示例: IS_STR = type_validator(str)
    """

    def validator(value: Any) -> bool:
        return isinstance(value, expected_type)

    validator.__name__ = f"is_{expected_type.__name__}"
    return validator


# 基础类型校验器
IS_STR = type_validator(str)
IS_FLOAT = type_validator(float)
IS_INT = type_validator(int)
IS_BOOL = type_validator(bool)
IS_LIST = type_validator(list)
IS_DICT = type_validator(dict)


# =============================
# 3. 组合式校验器（逻辑操作）
# =============================

def all_of(*validators: Callable[[Any], bool]) -> Callable[[Any], bool]:
    """
    所有校验器都通过才算通过。
    """

    def combined_validator(value: Any) -> bool:
        for i, v in enumerate(validators):
            if not v(value):
                combined_validator.last_failure = f"Failed at validator[{i}]: {get_validator_name(v)}"
                return False
        return True

    combined_validator.__name__ = f"all_of({', '.join(get_validator_name(v) for v in validators)})"
    combined_validator.last_failure = None
    return combined_validator


def any_of(*validators: Callable[[Any], bool]) -> Callable[[Any], bool]:
    """
    任一校验器通过即通过。
    """

    def combined_validator(value: Any) -> bool:
        return any(v(value) for v in validators)

    combined_validator.__name__ = f"any_of({', '.join(get_validator_name(v) for v in validators)})"
    return combined_validator


def none_of(*validators: Callable[[Any], bool]) -> Callable[[Any], bool]:
    """
    所有校验器都不通过才算通过（反向校验）。
    """
    return lambda x: not any(v(x) for v in validators)


# =============================
# 4. 工具函数
# =============================

def get_validator_name(v: Callable) -> str:
    """安全获取校验器名称"""
    return getattr(v, '__name__', str(v))


# =============================
# 5. 字符串校验器
# =============================

# 基础字符串
NON_EMPTY_STRING = all_of(IS_STR, lambda s: len(s.strip()) > 0)
IS_ASCII = all_of(IS_STR, lambda s: s.isascii())
IS_PRINTABLE = all_of(IS_STR, lambda s: s.isprintable())
IS_ALPHANUMERIC = all_of(IS_STR, lambda s: s.isalnum())

# 安全文本（防注入、长度限制）
IS_SAFE_TEXT = all_of(
    IS_STR,
    lambda s: len(s.strip()) > 0,
    lambda s: '\x00' not in s,  # 防空字符
    lambda s: len(s) < 10_000  # 防超长文本
)


# 正则匹配
def matches_regex(pattern: str) -> Callable[[Any], bool]:
    return lambda x: isinstance(x, str) and bool(re.match(pattern, x))


# 邮箱
IS_EMAIL = matches_regex(r'^[^@]+@[^@]+\.[^@]+$')

# UUID v4
IS_UUID = matches_regex(
    r'^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$'
)


# =============================
# 6. 数值校验器
# =============================

def min_value(min_val: float) -> Callable[[Any], bool]:
    return lambda x: isinstance(x, (int, float)) and x >= min_val


def max_value(max_val: float) -> Callable[[Any], bool]:
    return lambda x: isinstance(x, (int, float)) and x <= max_val


def in_range(min_val: float, max_val: float) -> Callable[[Any], bool]:
    return all_of(min_value(min_val), max_value(max_val))


# 常用数值范围
POSITIVE_FLOAT = all_of(IS_FLOAT, lambda x: x > 0)
NON_NEGATIVE_INT = all_of(IS_INT, lambda x: x >= 0)
PERCENTAGE = in_range(0.0, 1.0)  # 0.0 ~ 1.0
PROBABILITY = PERCENTAGE
CLIPPED_FLOAT_1 = in_range(-1.0, 1.0)  # 如 valence
CLIPPED_FLOAT_5 = in_range(0.0, 5.0)  # 如评分
TWO_DEC_FLOAT = all_of(IS_FLOAT, lambda x: abs(x - round(x, 2)) < 1e-9)


# 高精度浮点校验（防浮点误差）
def is_precise_decimal(precision: int = 2) -> Callable[[Any], bool]:
    from decimal import Decimal, InvalidOperation

    def validate(f):
        try:
            d = Decimal(str(f))
            return d.as_tuple().exponent >= -precision
        except (InvalidOperation, TypeError):
            return False

    return all_of(IS_FLOAT, validate)


PRECISE_2DEC = is_precise_decimal(2)


# =============================
# 7. 时间校验器
# =============================

def is_valid_iso8601_zoned(timestamp: str) -> bool:
    if not isinstance(timestamp, str):
        return False
    # 匹配 ±hh:mm 时区格式
    pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$'
    if not re.match(pattern, timestamp):
        return False
    try:
        from datetime import datetime
        datetime.fromisoformat(timestamp)
        return True
    except Exception:
        return False


ISO8601_TIMESTAMP = all_of(IS_STR, is_valid_iso8601_zoned)
ISO8601_TIMESTAMP_STRICT = all_of(
    ISO8601_TIMESTAMP,
    lambda s: s.endswith('Z') or '+00:00' in s  # 强制 UTC
)

# =============================
# 8. 结构化数据校验器
# =============================

# 非空结构
NON_EMPTY_LIST = all_of(IS_LIST, lambda lst: len(lst) > 0)
NON_EMPTY_DICT = all_of(IS_DICT, lambda d: len(d) > 0)


# 键存在性
def has_keys(*required_keys: str) -> Callable[[Any], bool]:
    return lambda x: isinstance(x, dict) and all(k in x for k in required_keys)


def has_nested_field(*path: str) -> Callable[[Any], bool]:
    """检查嵌套字段是否存在"""

    def validator(data):
        curr = data
        for key in path:
            if not isinstance(curr, dict) or key not in curr:
                return False
            curr = curr[key]
        return True

    return validator


# 字典键白名单（防字段注入）
def strict_keys(*allowed_keys: str) -> Callable[[Any], bool]:
    return lambda d: isinstance(d, dict) and all(k in allowed_keys for k in d.keys())


# 列表元素类型统一
def LIST_OF(item_validator: Callable[[Any], bool]) -> Callable[[Any], bool]:
    return all_of(
        IS_LIST,
        lambda lst: all(item_validator(item) for item in lst)
    )


# 字典值结构校验
def DICT_OF(schema: Dict[str, Callable[[Any], bool]]) -> Callable[[Any], bool]:
    """
    schema: {"field": validator}
    """

    def validate(d):
        if not isinstance(d, dict):
            return False
        return all(
            key in d and validator(d[key])
            for key, validator in schema.items()
        )

    return validate


# =============================
# 9. 防御性校验器（防攻击/DoS）
# =============================

def max_depth(max_d: int = 5) -> Callable[[Any], bool]:
    """防止深度嵌套导致栈溢出"""

    def check(obj, depth=0):
        if depth > max_d:
            return False
        if isinstance(obj, dict):
            return all(check(v, depth + 1) for v in obj.values())
        elif isinstance(obj, list):
            return all(check(item, depth + 1) for item in obj)
        return True

    return lambda obj: check(obj)


def max_length(n: int) -> Callable[[Any], bool]:
    """限制列表长度"""
    return all_of(IS_LIST, lambda lst: len(lst) <= n)


def max_keys(n: int) -> Callable[[Any], bool]:
    """限制字典键数量"""
    return all_of(IS_DICT, lambda d: len(d) <= n)


# =============================
# 10. 枚举与语义校验器
# =============================

def enum(*values) -> Callable[[Any], bool]:
    """枚举值校验"""
    return lambda x: x in values
