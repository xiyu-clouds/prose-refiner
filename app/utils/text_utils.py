"""
文本工具函数集。
目前主要存放中英文逗号统一处理的公共函数，未来可扩展分词、清洗、格式规范化等通用文本逻辑。
"""
import json
from typing import Any, FrozenSet, List

# ------------------------------
# 全局 list 类型配置键（SSOT）——只包含「逗号分隔的字符串列表」字段。
# 所有「逗号分隔 → list[str]」字段必须在此登记，未登记的普通字符串不会被自动 split。
#
# ⚠️  对象数组类型的字段**绝对不能**加入此集合！
#     例如 XINHAI_LOCAL_MODELS_DEFINITION 是 [{name,modality,...}] 的对象数组，
#     parse_comma_list 会把对象 str() 成垃圾字符串，导致前端渲染失败且污染配置文件。
#
# 登记清单与 app/config/config.py Config._load() 中 cast=list 的字段一一对应：
#   - 通知组（4 个）：NOTIFICATION_CHANNELS / EMAIL_TO / FEISHU_AT_USER_IDS / WECOM_AT_USER_IDS
#   - 本地轻量模型（1 个）：TEXT_ANALYSIS_TASKS（纯字符串任务名列表）
#   - 明确排除：XINHAI_LOCAL_MODELS_DEFINITION（对象数组类型，禁止逗号 split）
# ------------------------------
LIST_FIELD_KEYS: FrozenSet[str] = frozenset({
    "XINHAI_NOTIFICATION_CHANNELS",
    "XINHAI_EMAIL_TO",
    "XINHAI_FEISHU_AT_USER_IDS",
    "XINHAI_WECOM_AT_USER_IDS",
    "XINHAI_TEXT_ANALYSIS_TASKS",
})


def parse_comma_list(value: Any, *, item_strip: bool = True, drop_empty: bool = True) -> List[str]:
    """
    把「逗号分隔的字符串 / JSON 数组字符串 / Python list」统一规范成纯 list[str]。

    **核心特性：自动识别并兼容中英文逗号**
    - 支持的分隔符：英文 `,`、中文 `，`、全角 `、` （顿号，中文用户经常误输入）
    - 输入类型兼容：
        * list：直接遍历每个元素 → str 化 → strip → 去空
        * str 看起来像 JSON 数组 `["a","b"]`：先 json.loads 解析，失败兜底按逗号 split
        * str 纯逗号分隔 `"a,b,c"` / `"a，b，c"` / `"a、b、c"`：按分隔符 split

    **参数**
    - item_strip：每个元素是否 strip() 前后空白，默认 True
    - drop_empty：是否丢弃空字符串元素，默认 True

    **返回**
    - 永远返回 list[str]（哪怕输入 None / 空串 / 解析失败都返回空列表，不抛异常）
    - 所有分隔符最终都会被规范化为英文逗号的等价分割结果，入库永远是干净的 list

    例：
        parse_comma_list("foo，bar、baz, qux ")     -> ["foo", "bar", "baz", "qux"]
        parse_comma_list(["a", "", "  b  "])        -> ["a", "b"]
        parse_comma_list('["x", "y"]')              -> ["x", "y"]
        parse_comma_list(None)                      -> []
    """
    if value is None:
        return []

    # ---- 已经是 list：直接每个元素 str 化 + strip + 去空 ----
    if isinstance(value, list):
        out: List[str] = []
        for item in value:
            s = "" if item is None else str(item)
            if item_strip:
                s = s.strip()
            if not drop_empty or s:
                out.append(s)
        return out

    if not isinstance(value, str):
        try:
            s = str(value)
        except Exception:
            return []
    else:
        s = value

    s = s.strip()
    if not s:
        return []

    # ---- 看起来像 JSON 数组：先尝试解析（兼容引擎误返回 JSON 字符串的场景）----
    stripped_left = s.lstrip()
    if stripped_left.startswith("["):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return parse_comma_list(parsed, item_strip=item_strip, drop_empty=drop_empty)
        except (json.JSONDecodeError, ValueError):
            pass

    # ---- 最后兜底：按「英文逗号 / 中文逗号 / 全角顿号」任一分割 ----
    # 先把中文逗号、顿号统一替换成英文逗号，再一次性 split，避免多次 pass
    normalized = s.replace("，", ",").replace("、", ",")
    parts = normalized.split(",")

    out: List[str] = []
    for p in parts:
        if item_strip:
            p = p.strip()
        if not drop_empty or p:
            out.append(p)
    return out


def format_comma_list(items: Any, *, separator: str = ", ") -> str:
    """
    与 parse_comma_list 成对：把 list[str] 序列化成用户可读的「英文逗号 + 空格」连接的字符串。
    用于前端展示、日志打印等场景。

    例：
        format_comma_list(["foo", "bar"]) -> "foo, bar"
        format_comma_list(None)           -> ""
    """
    if items is None:
        return ""
    if isinstance(items, str):
        return items
    if not isinstance(items, (list, tuple)):
        try:
            items = list(items)
        except Exception:
            return str(items)
    cleaned = [str(x) for x in items if x is not None and str(x).strip() != ""]
    return separator.join(cleaned)
