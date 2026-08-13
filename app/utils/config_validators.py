import copy
import json
import re
from typing import Optional, Dict, Tuple, Any

from app.utils.text_utils import LIST_FIELD_KEYS, parse_comma_list


# ==================== 脱敏 / 占位拦截常量 ====================

SENSITIVE_TOKENS = ("API_KEY", "PASSWORD", "SECRET", "TOKEN")

ALL_STARS_RE = re.compile(r"^\*{3,}$")

PLACEHOLDER_RE_CN = re.compile(r"请(?:输入|填写|选择|设置|替换)")
PLACEHOLDER_RE_EN = re.compile(
    r"<your[-_]|(?<![a-zA-Z])your[-_]|<todo>|(?<![a-zA-Z])todo(?![a-zA-Z])",
    re.IGNORECASE,
)

BOOL_TRUE_VALUES = {"1", "true", "yes", "y", "on", "是", "启用", "开启", "t"}
BOOL_FALSE_VALUES = {"0", "false", "no", "n", "off", "否", "禁用", "关闭", "f"}

MASK_STR = "***"


# ==================== 通用配置校验工具（无状态）====================

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
        """
        校验逗号分隔的字符串列表（每个元素必须是非空字符串）。

        校验前会自动做 in-place 标准化：如果 d[key] 是 str（或任何非 list），
        会先调用 parse_comma_list 转成干净的 list[str]，再继续校验。
        """
        v = d.get(key)
        if v is None:
            return
        # 自动标准化：str / list / JSON 数组字符串 → list[str]
        if not isinstance(v, list):
            normalized = parse_comma_list(v)
            d[key] = normalized
            v = normalized
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


# ==========================================================================
# 敏感字段判定 + 脱敏 + 占位拦截（SSOT，所有路由层禁止重新实现散写版本）
# ==========================================================================


def is_sensitive_key(key: str) -> bool:
    """
    按「underscore 分隔的整词」判断是否为敏感字段。
    例：
      API_KEY → 把 key 按下划线切开，词集合包含 API_KEY → True
      PASSWORD → True
      TOKEN    → 词集合包含 TOKEN（但不会匹配 TOKENS）→ False
      MAX_TOKENS_EXPANSION_FACTOR → 词集合 {MAX,TOKENS,EXPANSION,FACTOR}，
          包含 TOKENS 不包含 TOKEN → False，不会遮蔽成 ***
    """
    if not isinstance(key, str) or not key:
        return False
    upper = key.strip().upper()
    tokens: set = {t for t in re.split(r"_+", upper) if t}
    return any(tok in tokens for tok in SENSITIVE_TOKENS)


def is_all_stars_placeholder(value: Any) -> bool:
    """
    只有「全星号 + 至少 3 个」的字符串才算敏感占位符（来自 GET 端 MASK_STR 遮蔽），
    拒绝写回引擎，避免把假掩码当真实值入库。
    """
    if not isinstance(value, str):
        return False
    s = value.strip()
    if not s:
        return False
    return ALL_STARS_RE.match(s) is not None


def contains_placeholder(value: Any) -> bool:
    """
    递归检测值中是否含占位符关键词（仅用于敏感字段拦截，调用方自行判断 key 是否敏感）。
    两条合并正则覆盖中文（请输入/填写/选择/设置/替换）与英文（your-/<your-/TODO/todo/<todo>）。
    """
    if value is None or isinstance(value, (bool, int, float)):
        return False
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return False
        return PLACEHOLDER_RE_CN.search(s) is not None or PLACEHOLDER_RE_EN.search(s) is not None
    if isinstance(value, list):
        return any(contains_placeholder(i) for i in value)
    if isinstance(value, dict):
        return any(contains_placeholder(v) for v in value.values())
    try:
        s = str(value)
        return PLACEHOLDER_RE_CN.search(s) is not None or PLACEHOLDER_RE_EN.search(s) is not None
    except Exception:
        return False


def mask_sensitive(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    返回深拷贝后的 data，**仅命中整词敏感规则且含有真实非空非占位符值**的字段才替换为 ***。

    判定"没有真实值"（返回空字符串，让前端显示 placeholder 让用户知道要填）的条件：
      - None / 空字符串 / 仅空白
      - 纯星号占位符 (***)
      - 含占位符关键词（请输入/请填写/请选择/请设置/请替换/your-/<your-/TODO/<todo> 等）

    这样：
      - DeepSeek API 密钥没填 / 腾讯 SECRET_ID 只是默认占位 "请输入腾讯云SecretId" → 前端显示 "⚠️ 未设置，请输入"
      - 真填了密钥 sk-xxx → 前端显示 🔐 已保存真实密钥（掩码显示）
    """
    out: Dict[str, Any] = copy.deepcopy(data) if isinstance(data, dict) else {}
    for k, v in out.items():
        if not is_sensitive_key(k):
            continue
        if contains_placeholder(v):
            out[k] = ""
            continue
        if v is None:
            out[k] = ""
            continue
        if isinstance(v, str):
            s = v.strip()
            if not s:
                out[k] = ""
                continue
            if is_all_stars_placeholder(s):
                out[k] = ""
                continue
        out[k] = MASK_STR
    return out


# ==========================================================================
# 类型 cast + 标准化辅助（PATCH 侧写回用）
# ==========================================================================


def cast_bool(value: Any) -> Any:
    """布尔通用 cast（失败抛 ValueError，调用方汇总成 422）"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in BOOL_TRUE_VALUES:
            return True
        if s in BOOL_FALSE_VALUES:
            return False
    raise ValueError(
        f"布尔值非法：{value!r}。合法值：true/false/1/0/是/否/启用/禁用..."
    )


def light_cast_for_patch(raw_value: Any) -> Any:
    """
    PATCH 侧：通用轻量 cast（不依赖字段名）。
    - dict/list/None/int/float/bool：直接通过；
    - 空字符串：原样返回（上层决定是否写入空）；
    - 非空字符串：优先尝试 JSON 解析（dict/list/数字），失败返回 str 原样；
      数字字符串（看起来像 int/float）不做自动 cast → 交给 validate_global_config 按范围规则报错
      （否则 "abc" 误传 7200 到 list 字段会静默通过）。
    """
    if isinstance(raw_value, (dict, list, int, float, bool)) or raw_value is None:
        return raw_value
    if not isinstance(raw_value, str):
        try:
            return str(raw_value)
        except Exception:
            raise ValueError(f"无法识别的配置值类型：{type(raw_value).__name__}")
    s = raw_value.strip()
    if not s:
        return ""
    # 只有看起来像 JSON 的才尝试解析（list/dict/JSON 数字），避免 "7200" 这种被误转成 int
    if s.startswith("{") or s.startswith("["):
        try:
            return json.loads(s)
        except (json.JSONDecodeError, ValueError):
            pass
    return raw_value


def normalize_config(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET 侧规范化（失败兜底，绝不抛错）：
    1) 通用：字符串若看起来像 JSON（以 {/[ 开头）则尝试解析成 dict/list；
    2) 对 LIST_FIELD_KEYS 中声明的 list 字段：统一调用 parse_comma_list，
       无论来源是 JSON 字符串、英文逗号、中文逗号、顿号、还是 list 本身，
       最终都输出干净的 list[str]（空值、空白项会被去除）。
    3) 调用 validate_global_config 做 in-place float 标准化（特定字段 int→float）；
       validate 的错误 GET 侧忽略（GET 必须稳定返回，错误只在 PATCH 侧拦截）。
    """
    normalized: Dict[str, Any] = {}
    if not isinstance(data, dict):
        return normalized
    for k, v in data.items():
        if k in LIST_FIELD_KEYS:
            normalized[k] = parse_comma_list(v)
            continue
        if isinstance(v, str) and v.strip():
            if v.lstrip().startswith(("{", "[")):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, (dict, list)):
                        normalized[k] = parsed
                        continue
                except (json.JSONDecodeError, ValueError):
                    pass
            # 非 list 字段：逗号分隔的字符串不再自动 split，保持原值（避免误处理普通文本）
            normalized[k] = v
            continue
        normalized[k] = v
    # float 字段 in-place 标准化（validate_global_config 里的第 1 步，错误忽略）
    try:
        validate_global_config(normalized)
    except Exception:
        pass
    return normalized


def normalize_key(key: str) -> str:
    """key 规范化：大写 + 自动补齐 XINHAI_ 前缀"""
    k = str(key).strip()
    if not k:
        return ""
    k = k.upper()
    if k.startswith("XINHAI_"):
        return k
    return f"XINHAI_{k}"


def normalize_full_keys(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    规范化整个配置字典的 key（返回双份冗余 KV，确保任何历史前端都能命中）：
      1) 原 key 原样保留一份（不动大小写/前缀，兼容历史代码）
      2) 规范化 key（大写 + 补 XINHAI_ 前缀）也存一份，确保前端 config.js 能命中
    不存在重复覆盖问题：规范化后同值 merge，不会互相污染（都是同一个 value）。
    """
    if not isinstance(data, dict):
        return {}
    out: Dict[str, Any] = {}
    for k, v in data.items():
        if not isinstance(k, str):
            continue
        # 1) 原 key 原样保留
        out[k] = v
        # 2) 规范化 key 也存一份
        nk = normalize_key(k)
        if nk and nk != k and nk not in out:
            out[nk] = v
    return out


def unwrap_engine_scalar(key: str, raw_value: Any) -> Any:
    """
    global_config_get_by_key 返回值兜底：
    极少数情况下引擎可能误返回整条行包装记录，这里尝试解包出正确的单值。
    """
    if (
        isinstance(raw_value, dict)
        and "config_json" in raw_value
        and ("id" in raw_value or "created_at" in raw_value or "updated_at" in raw_value)
    ):
        inner = raw_value.get("config_json")
        if isinstance(inner, str) and inner.strip():
            try:
                parsed = json.loads(inner)
                if isinstance(parsed, dict):
                    return parsed.get(key, None)
            except (json.JSONDecodeError, ValueError):
                return None
        if isinstance(inner, dict):
            return inner.get(key, None)
        return None
    return raw_value


def values_equal(a: Any, b: Any) -> bool:
    """
    判断前后两个值是否“语义上相等”，用于跳过无意义保存。
    对 dict/list 用 JSON 序列化对比（避免 Python 对象引用不同导致误判）。
    """
    try:
        return json.dumps(a, ensure_ascii=False, sort_keys=True) == json.dumps(
            b, ensure_ascii=False, sort_keys=True
        )
    except Exception:
        return a == b


# ==========================================================================
# 全局配置集中式校验（唯一真相来源，取代零散 SLOT_CAST_MAP / _coerce_value_for_key）
# ==========================================================================


def validate_global_config(data: dict) -> list:
    """
    使用 cv（ConfigValidator）工具函数组做**集中式**校验：
      0) list 字段 in-place 标准化（str → list[str]，兼容中英文逗号、顿号）；
      1) in-place 把特定 int 字段标准化为 float（避免引擎存 int 导致 FLOAT 字段
         在展示时丢失「浮点」语义）；
      2) 136 条类型 + 范围 + 枚举 + 渠道合法性规则；
      3) LLM_PARAMS / DEFAULT_RETRY_CONFIG 等嵌套结构的精细字段校验。
    cv 的每条 check 均以 `v is not None` 为前置条件，所以 PATCH 场景（只改部分字段）
    直接把 cleaned 丢进来即可，缺失键不会报假错。
    """
    # 延迟 import，避免 utils 与 common 的循环依赖（被 routers / config / 其他模块导入时）
    from app.common import values as va
    from app.common.llm_constants import LLMModel

    cv = ConfigValidator
    errors: list = []
    if not isinstance(data, dict):
        errors.append("请求配置必须是 JSON 对象（dict）")
        return errors
    d = data

    # ---- Step 0: list 字段 in-place 标准化（任何进入校验器的 list 字段都一定是 list[str]）----
    for list_key in LIST_FIELD_KEYS:
        if list_key in d and d[list_key] is not None and not isinstance(d[list_key], list):
            d[list_key] = parse_comma_list(d[list_key])

    # ---- float 字段 in-place 标准化（int → float，保证 float 字段永远是 float）----
    for field in [
        "XINHAI_WATERMARK_OPACITY",
        "XINHAI_METACOGNITION_QUEUE_HIGH_WATERMARK",
        "XINHAI_METACOGNITION_QUEUE_MID_WATERMARK",
        "XINHAI_FULL_TEXT_TOKENS_RATIO",
        "XINHAI_MAX_TOKENS_EXPANSION_FACTOR",
        "XINHAI_FACTOR_INCREMENT",
        "XINHAI_LOCAL_MODEL_MEMORY_THRESHOLD",
        "XINHAI_SEMANTIC_SIMILARITY_THRESHOLD",
    ]:
        if field in d and isinstance(d[field], int):
            d[field] = float(d[field])

    # ---- 类型 + 范围 + 枚举批量规则 ----
    checks = [
        (cv.str_check, ("XINHAI_TEXT_DEFAULT_VENDOR",)),
        (cv.str_check, ("XINHAI_TEXT_DEFAULT_MODEL",)),
        (cv.model_valid_check, ("XINHAI_TEXT_DEFAULT_MODEL", set(LLMModel.all()))),
        (cv.int_check, ("XINHAI_TEXT_API_TIMEOUT", 1, 600)),
        (cv.str_check, ("XINHAI_DEEPSEEK_API_KEY",)),
        (cv.str_check, ("XINHAI_TONGYI_API_KEY",)),

        (cv.str_check, ("XINHAI_AUDIO_DEFAULT_VENDOR",)),
        (cv.str_check, ("XINHAI_AUDIO_DEFAULT_MODEL",)),
        (cv.str_check, ("XINHAI_IMAGE_DEFAULT_VENDOR",)),
        (cv.str_check, ("XINHAI_IMAGE_DEFAULT_MODEL",)),
        (cv.str_check, ("XINHAI_VIDEO_DEFAULT_VENDOR",)),
        (cv.str_check, ("XINHAI_VIDEO_DEFAULT_MODEL",)),

        (cv.bool_check, ("XINHAI_LANGSMITH_ENABLED",)),
        (cv.str_check, ("XINHAI_LANGSMITH_API_KEY",)),
        (cv.str_check, ("XINHAI_LANGSMITH_PROJECT",)),
        (cv.str_check, ("XINHAI_LANGSMITH_ENDPOINT",)),

        (cv.bool_check, ("XINHAI_METACOGNITION_ENABLED",)),
        (cv.int_check, ("XINHAI_METACOGNITION_MAX_LLM_CALLS", 30, 100)),
        (cv.int_check, ("XINHAI_METACOGNITION_MAX_DEBATE_ROUNDS", 1, 50)),
        (cv.int_check, ("XINHAI_METACOGNITION_QUEUE_MAXSIZE", 10, 200)),
        (cv.int_check, ("XINHAI_METACOGNITION_MAX_CONCURRENT_LOOPS", 1, 10)),
        (cv.int_check, ("XINHAI_METACOGNITION_EXPIRES_AT", 120, 3600)),
        (cv.int_check, ("XINHAI_METACOGNITION_MAX_CHARS_PER_TURN", 200, 3000)),
        (cv.int_check, ("XINHAI_METACOGNITION_MAX_DEBATE_TURNS_TO_INJECT", 1, 5)),
        (cv.int_check, ("XINHAI_METACOGNITION_MAX_ISSUES_TO_DISPLAY", 1, 15)),
        (cv.int_check, ("XINHAI_METACOGNITION_DATA_LOADER_DEFAULT_LEVEL", 0, 2)),

        (cv.int_check, ("XINHAI_METACOGNITION_MONITOR_ALERT_COOLDOWN", 0, 7200)),
        (cv.float_check, ("XINHAI_METACOGNITION_QUEUE_HIGH_WATERMARK", 0.5, 1.0)),
        (cv.float_check, ("XINHAI_METACOGNITION_QUEUE_MID_WATERMARK", 0.1, 0.8)),
        (cv.int_check, ("XINHAI_METACOGNITION_QUEUE_CHECK_INTERVAL", 10, 600)),

        (cv.int_check, ("XINHAI_METACOGNITION_TARGET_CHARS", 500, 1500)),
        (cv.int_check, ("XINHAI_METACOGNITION_TOLERANCE", 0, 300)),

        (cv.int_check, ("XINHAI_LOG_KEEP_DAYS", 1, 365)),
        (cv.int_check, ("XINHAI_LOG_MAX_BYTES", 1048576, 1073741824)),
        (cv.int_check, ("XINHAI_LOG_BACKUP_COUNT", 1, 50)),

        (cv.int_check, ("XINHAI_MAX_LLM_STEP_CONCURRENCY", 1, 30)),
        (cv.int_check, ("XINHAI_CURRENT_LLM_STEP_CONCURRENCY", 1, 30)),
        (cv.int_check, ("XINHAI_MEDIUM_LLM_STEP_CONCURRENCY", 1, 30)),
        (cv.int_check, ("XINHAI_MAX_BATCH_TASK_CONCURRENCY", 1, 15)),
        (cv.int_check, ("XINHAI_CURRENT_BATCH_TASK_CONCURRENCY", 1, 15)),
        (cv.int_check, ("XINHAI_MEDIUM_BATCH_TASK_CONCURRENCY", 1, 15)),

        (cv.int_check, ("XINHAI_LOCAL_MODEL_MAX_MEMORY_MB", 512, 262144)),
        (cv.int_check, ("XINHAI_LOCAL_MODEL_MONITOR_INTERVAL", 5, 3600)),
        (cv.float_check, ("XINHAI_LOCAL_MODEL_MEMORY_THRESHOLD", 0.0, 1.0)),
        (cv.int_check, ("XINHAI_LOCAL_MODEL_MAX_EVICTION_ATTEMPTS", 1, 100)),
        (cv.int_check, ("XINHAI_LOCAL_MODEL_CONCURRENCY", 1, 64)),
        (cv.bool_check, ("XINHAI_ENABLE_TEXT_ANALYSIS_TASKS",)),
        (cv.comma_separated_str_list_check, ("XINHAI_TEXT_ANALYSIS_TASKS",)),

        (cv.int_check, ("XINHAI_GLOBAL_MAX_RETRIES", 1, 100000)),
        (cv.bool_check, ("XINHAI_GLOBAL_ENABLE_METRICS",)),

        (cv.str_check, ("XINHAI_STORAGE_BACKEND",)),
        (cv.int_check, ("XINHAI_LLM_CACHE_MAX_SIZE", 128, 65536)),
        (cv.int_check, ("XINHAI_LLM_CACHE_TTL", 0, 2592000)),
        (cv.str_check, ("XINHAI_REDIS_HOST",)),
        (cv.int_check, ("XINHAI_REDIS_PORT", 1, 65535)),
        (cv.int_check, ("XINHAI_REDIS_DB", 0, 15)),
        (cv.str_check, ("XINHAI_REDIS_PASSWORD",)),
        (cv.int_check, ("XINHAI_REDIS_TIMEOUT", 1, 30)),

        (cv.bool_check, ("XINHAI_WATERMARK_ENABLED",)),
        (cv.str_check, ("XINHAI_WATERMARK_TEXT",)),
        (cv.str_check, ("XINHAI_WATERMARK_COLOR",)),
        (cv.float_check, ("XINHAI_WATERMARK_OPACITY", 0.0, 1.0)),
        (cv.int_check, ("XINHAI_WATERMARK_FONT_SIZE", 8, 120)),
        (cv.int_check, ("XINHAI_WATERMARK_ANGLE", -180, 180)),
        (cv.int_check, ("XINHAI_WATERMARK_SPACING_COLS", 1, 20)),
        (cv.int_check, ("XINHAI_WATERMARK_SPACING_ROWS", 1, 20)),
        (cv.int_check, ("XINHAI_WATERMARK_PADDING", 0, 200)),

        (cv.bool_check, ("XINHAI_NOTIFICATION_ENABLED",)),
        (cv.channels_valid_check, ("XINHAI_NOTIFICATION_CHANNELS", set(va.VAL_NOTIFICATION_CHANNELS))),
        (cv.str_check, ("XINHAI_EMAIL_SMTP_SERVER",)),
        (cv.int_check, ("XINHAI_EMAIL_PORT", 1, 65535)),
        (cv.str_check, ("XINHAI_EMAIL_USERNAME",)),
        (cv.str_check, ("XINHAI_EMAIL_PASSWORD",)),
        (cv.comma_separated_str_list_check, ("XINHAI_EMAIL_TO",)),
        (cv.comma_separated_str_list_check, ("XINHAI_FEISHU_AT_USER_IDS",)),
        (cv.comma_separated_str_list_check, ("XINHAI_WECOM_AT_USER_IDS",)),
        (cv.str_check, ("XINHAI_FEISHU_WEBHOOK_URL",)),
        (cv.str_check, ("XINHAI_WECOM_WEBHOOK_URL",)),

        (cv.str_check, ("XINHAI_UNSPLASH_ACCESS_KEY",)),
        (cv.str_check, ("XINHAI_UNSPLASH_BASIC_PATH",)),
        (cv.str_check, ("XINHAI_PEXELS_ACCESS_KEY",)),
        (cv.str_check, ("XINHAI_PEXELS_BASIC_PATH",)),

        (cv.bool_check, ("XINHAI_OLLAMA_ENABLED",)),
        (cv.str_check, ("XINHAI_OLLAMA_BASE_URL",)),
        (cv.str_check, ("XINHAI_OLLAMA_MODEL",)),
        (cv.dict_check, ("XINHAI_OLLAMA_PARAMS",)),
        (cv.int_check, ("XINHAI_OLLAMA_TIMEOUT", 60, 1800)),

        (cv.str_check, ("XINHAI_TEXT_REPORT_TITLE",)),

        (cv.str_check, ("XINHAI_PROXY_BACKEND_SSE_URL",)),
        (cv.int_check, ("XINHAI_SSE_HEARTBEAT_INTERVAL", 10, 120)),

        (cv.float_check, ("XINHAI_MAX_TOKENS_EXPANSION_FACTOR", 1.0, 10.0)),
        (cv.float_check, ("XINHAI_FULL_TEXT_TOKENS_RATIO", 1.0, 10.0)),

        (cv.int_check, ("XINHAI_IMAGE_COUNT", 38, 1000)),
        (cv.int_check, ("XINHAI_REFRESH_INTERVAL_MS", 30000, 7200000)),
        (cv.int_check, ("XINHAI_HEADER_BG_IMAGE_ID", 1, 1000)),
        (cv.int_check, ("XINHAI_FOOTER_BG_IMAGE_ID", 1, 1000)),
        (cv.int_check, ("XINHAI_DEFAULT_BG_IMAGE_ID", 1, 1000)),
        (cv.int_check, ("XINHAI_NOVEL_BG_IMAGE_ID", 1, 1000)),
        (cv.int_check, ("XINHAI_MESSAGE_WALL_BG_IMAGE_ID", 1, 1000)),

        (cv.int_check, ("XINHAI_MAX_LENGTH_RETRIES", 1, 10)),
        (cv.float_check, ("XINHAI_FACTOR_INCREMENT", 0.1, 1.0)),

        # 注入配置已改为 values.py 常量，此处不再校验

        (cv.int_check, ("XINHAI_PARAGRAPH_TARGET_CHARS", 100, 10000)),
        (cv.int_check, ("XINHAI_PARAGRAPH_TOLERANCE", 10, 2000)),
        (cv.int_check, ("XINHAI_PARAGRAPH_SPLIT_MIN_CHARS", 1, 500)),
        (cv.int_check, ("XINHAI_PARAGRAPH_SPLIT_TARGET_CHARS", 20, 10000)),
        (cv.str_check, ("XINHAI_PARAGRAPH_SPLIT_SENTENCE_PATTERN",)),
        (cv.bool_check, ("XINHAI_JIEBA_FILTER_STOPWORDS_DEFAULT",)),
        (cv.int_check, ("XINHAI_JIEBA_MIN_WORD_LEN", 1, 10)),
        (cv.int_check, ("XINHAI_TEXTRANK_TOP_K", 1, 500)),
        (cv.int_check, ("XINHAI_VOCAB_FILTER_MAX_WORDS", 1, 500)),
        (cv.int_check, ("XINHAI_VOCAB_FILTER_MAX_FREQWORDS", 1, 500)),
        (cv.float_check, ("XINHAI_SEMANTIC_SIMILARITY_THRESHOLD", 0.0, 1.0)),

        (cv.bool_check, ("XINHAI_REASONING_AUTO_INJECT",)),
        (cv.dict_check, ("XINHAI_REASONING_EFFORT_MAP",)),

        (cv.dict_check, ("XINHAI_TEXT_PARAMS",)),
        (cv.dict_check, ("XINHAI_DEFAULT_RETRY_CONFIG",)),
        (cv.list_check, ("XINHAI_NOTIFICATION_CHANNELS",)),
        (cv.list_check, ("XINHAI_EMAIL_TO",)),
        (cv.list_check, ("XINHAI_FEISHU_AT_USER_IDS",)),
        (cv.list_check, ("XINHAI_WECOM_AT_USER_IDS",)),
        (cv.list_check, ("XINHAI_LOCAL_MODELS_DEFINITION",)),
    ]
    cv.run_checks(errors, d, checks)

    # ---- 嵌套结构精细校验（TEXT_PARAMS / DEFAULT_RETRY_CONFIG）----
    text_params = d.get("XINHAI_TEXT_PARAMS")
    if text_params is not None:
        if not isinstance(text_params, dict):
            errors.append("XINHAI_TEXT_PARAMS 必须是字典")
        else:
            for k, v_min, v_max in [("temperature", 0, 1), ("max_tokens", 1, 100000), ("top_p", 0, 1)]:
                if k in text_params:
                    val = text_params[k]
                    if not isinstance(val, (int, float)) or val < v_min or val > v_max:
                        errors.append(f"XINHAI_TEXT_PARAMS.{k} 必须是 {v_min}-{v_max} 的数字")
            if "response_format" in text_params and not isinstance(text_params["response_format"], dict):
                errors.append("XINHAI_TEXT_PARAMS.response_format 必须是字典")
            if "stop" in text_params and not isinstance(text_params["stop"], list):
                errors.append("XINHAI_TEXT_PARAMS.stop 必须是列表")

    retry_cfg = d.get("XINHAI_DEFAULT_RETRY_CONFIG")
    if retry_cfg is not None:
        if not isinstance(retry_cfg, dict):
            errors.append("XINHAI_DEFAULT_RETRY_CONFIG 必须是字典")
        else:
            if "max_retries" in retry_cfg:
                v = retry_cfg["max_retries"]
                if not isinstance(v, int) or v < 0 or v > 20:
                    errors.append("XINHAI_DEFAULT_RETRY_CONFIG.max_retries 必须是 0-20 的整数")
            if "enable_exp_backoff" in retry_cfg and not isinstance(retry_cfg["enable_exp_backoff"], bool):
                errors.append("XINHAI_DEFAULT_RETRY_CONFIG.enable_exp_backoff 必须是布尔值")
            if "reraise" in retry_cfg and not isinstance(retry_cfg["reraise"], bool):
                errors.append("XINHAI_DEFAULT_RETRY_CONFIG.reraise 必须是布尔值")

    return errors
