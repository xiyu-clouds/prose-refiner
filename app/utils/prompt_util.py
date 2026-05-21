import re
from typing import Any
from .logger import LoggerManager as logger
from app.common import keys as ke

CHINESE_NAME = "Prompt 工具函数"


def wrap_static_json(text: str) -> str:
    """
    将文本中的单大括号 {} 包裹为双大括号 {{}}，以适配 str.format()。
    用于处理不需要注入变量的静态 JSON 片段。
    """
    if not isinstance(text, str):
        return text
    # 简单粗暴但有效：全量替换
    # 因为这部分内容本身就不应该包含 {var} 占位符
    return text.replace("{", "{{").replace("}", "}}")


def unwrap_static_json(text: str) -> str:
    """
    将格式化后的文本中的双大括号 {{}} 还原为单大括号 {}。
    用于清理最终 Prompt，去除多余字符。
    """
    if not isinstance(text, str):
        return text
    return text.replace("{{", "{").replace("}}", "}")


def extract_placeholders(template: str) -> set[str]:
    """
    安全提取 Python str.format 风格的占位符。
    支持：{name}, {user_id}, {count}
    忽略：{{escaped}}, {timestamp:%Y}, {value:.2f}
    """
    if not isinstance(template, str):
        raise TypeError("提示模板必须是字符串")
    # 匹配未转义的 {identifier...}，只取合法标识符部分
    pattern = r"(?<!\{)\{([_a-zA-Z][_a-zA-Z0-9]*)[^}]*\}(?!\})"
    return set(re.findall(pattern, template))


def safe_format_prompt(template: str, **kwargs: Any) -> str:
    """
    安全格式化 prompt 模板，仅支持关键字传参，杜绝位置错配。

    Raises:
        ValueError: 缺少必需参数
        RuntimeError: 格式化执行失败
    """
    required = extract_placeholders(template)
    provided = set(kwargs.keys())

    missing = required - provided
    if missing:
        raise ValueError(
            f"❌ Prompt 缺少必需参数: {sorted(missing)}\n"
            f"   模板要求: {sorted(required)}\n"
            f"   实际提供: {sorted(provided)}"
        )

    extra = provided - required
    if extra:
        logger.warning("⚠️ Prompt 接收到未使用的参数", extra={ke.KEY_UNUSED_PARAMS: sorted(extra)}, module_name=CHINESE_NAME)

    try:
        # 执行格式化 (此时静态部分仍是 {{}})
        formatted_text = template.format(**kwargs)

        # 清理静态部分 (将 {{}} 还原为 {})
        final_text = unwrap_static_json(formatted_text)

        return final_text
    except KeyError as e:
        raise RuntimeError(f"Prompt 格式化 KeyError（应已被拦截）: {e}") from e
    except Exception as e:
        raise RuntimeError(f"💥 Prompt 格式化运行时错误: {type(e).__name__}: {e}") from e
