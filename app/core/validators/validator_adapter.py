from typing import Dict, List, Callable, Any
from .validator import UniversalDataValidator
from ...common.enums import ValidationRule
from ...utils.llm_utils import build_monitored_config_from_rules
from app.common import keys as ke
from app.common import enums as en

CHINESE_NAME = "校验器入口"

validator = UniversalDataValidator.get_instance()


def build_pre_process_callback(rules: List[ValidationRule]) -> Callable[[Dict], None]:
    """
    根据规则列表，动态构建前置清洗回调函数。
    只提取那些 strip_quotes=True 的字段路径。
    """
    # 1. 提取需要清洗的字段路径列表
    target_paths = [rule.path for rule in rules if rule.strip_quotes]

    if not target_paths:
        # 如果没有需要清洗的字段，返回一个空函数，省去后续判断
        return lambda data: None

    def _recursive_clean(obj, current_path):
        if isinstance(obj, dict):
            for k, v in obj.items():
                new_path = f"{current_path}.{k}" if current_path else k
                if any(new_path.endswith(p) for p in target_paths):
                    if isinstance(v, str) and len(v) >= 2:
                        original_v = v
                        # 简单的首尾引号去除逻辑
                        if (v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'"):
                            obj[k] = v[1:-1]
                    elif isinstance(v, list):
                        # 如果是列表，遍历清洗（复用之前的逻辑）
                        obj[k] = [
                            item[1:-1] if isinstance(item, str) and len(item) >= 2 and ((item[0] == '"' and item[-1] == '"') or (item[0] == "'" and item[-1] == "'"))
                            else item for item in v
                        ]
                else:
                    _recursive_clean(v, new_path)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _recursive_clean(item, f"{current_path}[{i}]")

    return lambda data: _recursive_clean(data, "")


def validate_step_rules(data: Dict, step_id: str) -> Dict:
    rules: List[ValidationRule] = en.VAL_STEP_CHECK_RULES.get(step_id, [])
    if not rules:
        return {
            ke.KEY_IS_VALID: True,
            ke.KEY_ERRORS: [],
            ke.KEY_CLEANED_DATA: data
        }

    dynamic_config = build_monitored_config_from_rules(rules)

    pre_callback = build_pre_process_callback(rules)

    return validator.validate(
        data=data,
        rules=rules,
        monitored_fields_config=dynamic_config,
        pre_process_callback=pre_callback,
        post_process_callback=None
    )


def validate_metacognition_rules(data: Dict[str, Any], plugin_id: str) -> Dict[str, Any]:
    rules: List[ValidationRule] = en.VAL_METACOGNITION_CHECK_RULES.get(plugin_id, [])

    if not rules:
        return {
            ke.KEY_IS_VALID: True,
            ke.KEY_ERRORS: [],
            ke.KEY_CLEANED_DATA: data
        }

    dynamic_config = build_monitored_config_from_rules(rules)

    return validator.validate(
        data=data,
        rules=rules,
        monitored_fields_config=dynamic_config,
        pre_process_callback=None,
        post_process_callback=None
    )
