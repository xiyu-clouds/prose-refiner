import asyncio
import importlib
import json
import re
from typing import Dict, List, Any, Optional
from langchain_core.language_models import BaseChatModel
from app.common import keys as ke
from app.common import values as va
from app.common.enums import ValidationRule
from app.common.llm_constants import LLMVendor
from app.config.config import config
from app.utils.logger import LoggerManager as logger


def resolve_max_tokens(char_count: int) -> int:
    """基于输入文本长度动态计算 max_tokens 基准值。

    计算公式：max(safe_min, char_count * FULL_TEXT_TOKENS_RATIO)
    safe_min 为安全兜底，保证短文本也有足够空间容纳 DeepSeek 推理链。
    """
    base = int(char_count * config.FULL_TEXT_TOKENS_RATIO)
    safe_min = 3072
    return max(base, safe_min)



def extract_json_safely(content: str) -> dict:
    if not content or not content.strip():
        return {ke.KEY__ERROR: "空响应内容"}

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    cleaned = re.sub(r'^```(?:json|text|markdown)?\s*', '', content, flags=re.IGNORECASE)
    cleaned = re.sub(r'```\s*$', '', cleaned)
    cleaned = cleaned.strip()
    cleaned = cleaned.replace('\\\\', '\\').replace('\\\'', '\'').replace('\\"', '"')

    try:
        match = re.search(r'{.*}', cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except json.JSONDecodeError:
        pass

    return {ke.KEY__ERROR: "无法提取有效 JSON", ke.KEY__RAW: content[:200]}


def remove_check(text: str) -> str:
    text = re.sub(r'^```(?:json|text|markdown)?\s*\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\n?```$', '', text)
    return text


def extract_by_path(data: Dict, path: List) -> Any:
    """根据路径列表提取值，失败返回 None"""
    try:
        result = data
        for key in path:
            if isinstance(key, int) and isinstance(result, list):
                result = result[key]
            elif isinstance(key, str) and isinstance(result, dict):
                result = result[key]
            else:
                return None
        return result
    except (KeyError, IndexError, TypeError):
        return None


def extract_content_from_response(data: Dict, vendor: str) -> Optional[str]:
    """
    遍历配置中的路径列表，逐个尝试
    """
    meta = LLMVendor.get_metadata(vendor)
    schemas = meta.get(ke.KEY_RESPONSE_PATH, [])

    for schema in schemas:
        content_path = schema.get(ke.KEY_CONTENT)
        if content_path:
            content = extract_by_path(data, content_path)
            if content is not None:
                # 如果 content 是字符串，直接返回
                if isinstance(content, str):
                    return content
                # 如果 content 是其他类型，转换为字符串
                else:
                    return str(content)
    return None


def map_params_to_vendor(params: Dict[str, Any], params_map: Dict[str, str]) -> Dict[str, Any]:
    """
    将标准参数映射到厂商特定参数

    Args:
        params: 标准参数字典
        params_map: 参数映射表（标准名 -> 厂商名）

    Returns:
        映射后的参数字典
    """
    final_params = {}

    for std_key, value in params.items():
        # 如果值为 None，通常不传给 SDK，除非 SDK 需要显式 None
        if value is None:
            continue

        # 如果标准参数在映射表中，转换为厂商参数名
        if std_key in params_map:
            final_params[params_map[std_key]] = value
        else:
            final_params[std_key] = value

    return final_params


def create_langchain_model(vendor: str, params: Dict[str, Any]) -> BaseChatModel:
    """
    通用工厂：基于 LLMVendor.METADATA 动态加载与参数映射

    Args:
        vendor: 厂商标识
        params: 标准参数字典

    Returns:
        BaseChatModel 实例
    """
    # 1. 获取厂商元数据（如果找不到会直接报错，符合预期）
    meta = LLMVendor.get_metadata(vendor)

    # 2. 动态导入类
    try:
        module = importlib.import_module(meta[ke.KEY_PACKAGE])
        model_class = getattr(module, meta[ke.KEY_CLASS])
    except ImportError as e:
        raise ImportError(f"缺少依赖包: {meta[ke.KEY_PACKAGE]}。请运行: pip install {meta[ke.KEY_PACKAGE]}") from e

    # 3. 参数映射
    params_map = meta.get(ke.KEY_PARAMS_MAP, {})
    final_params = map_params_to_vendor(params, params_map)

    # 3.1 透传 base_url（厂商级端点，如通义 DashScope OpenAI 兼容端点）
    base_url = meta.get(ke.KEY_BASE_URL)
    if base_url:
        final_params[ke.KEY_BASE_URL] = base_url

    # 3.2 response_format 需要放入 model_kwargs，避免 LangChain 触发 UserWarning：
    #     "response_format was transferred to model_kwargs. Please confirm that response_format is what you intended."
    if ke.KEY_RESPONSE_FORMAT in final_params:
        rf = final_params.pop(ke.KEY_RESPONSE_FORMAT)
        if isinstance(final_params.get("model_kwargs"), dict):
            final_params["model_kwargs"][ke.KEY_RESPONSE_FORMAT] = rf
        else:
            final_params["model_kwargs"] = {ke.KEY_RESPONSE_FORMAT: rf}

    # 4. 实例化
    logger.debug(f"实例化模型: {vendor}, 类: {model_class.__name__}, 映射参数: {final_params}",
                 module_name="LLM工厂")
    return model_class(**final_params)


def build_monitored_config_from_rules(rules: List[ValidationRule]) -> Dict[str, str]:
    """
    从校验规则中提取需要监控解包的字段。
    策略：只监控期望类型为「基础类型」（非 dict 非 list）的叶子字段。
    原因：dict/list 类型的字段本身是容器，无需解包；真正需要解包的是那些本应是字符串/数字却被模型包装成字典的情况。
    """
    # 不需要解包的类型（容器类型）
    SKIP_TYPES = {ke.KEY_DICT, ke.KEY_LIST}

    config = {}
    for rule in rules:
        field_path = rule.path
        validator_func = rule.validator
        type_str = va.VAL_TYPE_VALIDATOR_TO_STR_MAP.get(validator_func)

        # 只关心基础类型（str, int, float, bool）
        if type_str and type_str not in SKIP_TYPES:
            leaf_field = field_path.split('.')[-1]
            config[leaf_field] = type_str
    return config


def format_llm_error(response) -> str:
    """
    从 LLMResponse 中提取标准化错误描述。
    优先拼接 errors 列表，其次使用 msg，最后回退到未知错误。
    """
    if response.errors:
        return "; ".join(response.errors)
    if response.msg:
        return response.msg
    return "未知错误"


def sort_context_paragraphs(context: dict) -> dict:
    """
    对上下文中的段落字典按段落序号升序排列。
    若 paragraphs 字段缺失或类型异常，则返回原 context。
    """
    if not isinstance(context, dict):
        return context

    paragraphs = context.get(ke.KEY_PARAGRAPHS)
    if not isinstance(paragraphs, dict):
        return context

    try:
        sorted_items = sorted(paragraphs.items(), key=lambda item: int(item[0]))
        context[ke.KEY_PARAGRAPHS] = dict(sorted_items)
    except (ValueError, TypeError):
        # 键不能转为 int 时放弃排序，保持原样
        pass

    return context


def format_character_profiles(profiles: list, title: str = "### 角色设定") -> str:
    if not isinstance(profiles, list) or not profiles:
        return ""
    lines = [title]
    for p in profiles:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        desc_parts = [f"- **{p['name']}**"]
        if p.get("identity"):
            desc_parts.append(f"身份：{p['identity']}")
        if p.get("personality"):
            traits = "、".join(p["personality"])
            desc_parts.append(f"性格：{traits}")
        if p.get("secret"):
            desc_parts.append(f"隐秘：{p['secret']}")
        if p.get("presence"):
            desc_parts.append(f"细节：{p['presence']}")
        # custom
        for k, v in p.get("custom", {}).items():
            if v:
                desc_parts.append(f"{k}：{v}")
        lines.append("；".join(desc_parts) + "。")
    return "\n".join(lines)


def format_relationship_map(rel_map: list, title: str = "### 人物关系") -> str:
    if not isinstance(rel_map, list) or not rel_map:
        return ""
    items = [f"- {r}" for r in rel_map if isinstance(r, str) and r.strip()]
    return "\n".join([title] + items) if items else ""


def format_worldview_rules(rules: list, title: str = "### 世界观规则") -> str:
    if not isinstance(rules, list) or not rules:
        return ""
    lines = [title]
    for r in rules:
        if not isinstance(r, dict) or not r.get("name"):
            continue
        parts = [f"- **{r['name']}**"]
        if r.get("description"):
            parts.append(f"规则：{r['description']}")
        if r.get("limitation"):
            parts.append(f"限制：{r['limitation']}")
        for k, v in r.get("custom", {}).items():
            if v:
                parts.append(f"{k}：{v}")
        lines.append("；".join(parts) + "。")
    return "\n".join(lines)


def format_style_preference(style, title: str = "### 风格倾向") -> str:
    if isinstance(style, list):
        style = "\n".join(str(s).strip() for s in style if s and str(s).strip())

    if not style:
        return ""

    return f"{title}\n{style}"


def build_user_clarification(injection_params: Dict[str, Any]) -> str:
    parts = [format_character_profiles(
        injection_params.get(ke.KEY_CHARACTER_PROFILES, [])), format_relationship_map(
        injection_params.get(ke.KEY_RELATIONSHIP_MAP, [])), format_worldview_rules(
        injection_params.get(ke.KEY_WORLDVIEW_RULES, [])), format_style_preference(
        injection_params.get(ke.KEY_STYLE_PREFERENCE, ""))]

    return "\n\n".join(p for p in parts if p)


def clean_serializable(obj):
    """递归移除不可序列化的对象（如 coroutine）"""
    if isinstance(obj, dict):
        return {str(k): clean_serializable(v) for k, v in obj.items() if not asyncio.iscoroutine(v)}
    elif isinstance(obj, list):
        return [clean_serializable(i) for i in obj if not asyncio.iscoroutine(i)]
    elif asyncio.iscoroutine(obj):
        return None  # 直接丢弃协程对象
    return obj
