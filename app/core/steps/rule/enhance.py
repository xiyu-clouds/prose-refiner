from typing import List
from app.core.steps.rule.base import BaseSteps
from app.common import keys as ke


class EnhanceStep(BaseSteps):
    """
    串行增强步骤的具体实现
    """
    CHINESE_NAME = "串行 - 增强"

    # 报告类型 → (type_key, 需要从 fix_data 提取的字段名列表)
    _REPORT_EXTRACTION_MAP = {
        ke.KEY_CREATIVE_ENHANCE: (ke.KEY_CREATIVE_ENHANCE, [ke.KEY_ISSUES_FIXED]),
        ke.KEY_CANDIDATES_OUTPUT: (ke.KEY_CANDIDATE_GENERATION, [ke.KEY_CANDIDATES]),
        ke.KEY_SELECTION_RESULT: (ke.KEY_INTELLIGENT_SELECTION, [ke.KEY_SELECTED_INDEX, ke.KEY_REASON]),
        ke.KEY_FIDELITY_REPAIR: (ke.KEY_FIDELITY_REPAIR, [ke.KEY_ISSUES_FIXED]),
    }

    def execution_mode(self) -> str:
        return ke.KEY_SERIAL

    def get_step_type(self) -> str:
        return ke.KEY_SERIAL_ENHANCE

    async def post_process(self, results: List[tuple]) -> None:
        for result, task in results:
            if not result.success():
                continue

            step_name = task.get(ke.KEY_NAME)
            output_key = task.get(ke.KEY_OUTPUT_KEY)
            content = result.content

            # 统一上下文记录
            context_data = {**result.to_dict(), ke.KEY_NAME: step_name}
            self.context_builder.update_context(context_data)

            if not isinstance(content, dict):
                continue

            fix_data = content.get(output_key)
            if not isinstance(fix_data, dict):
                continue

            # 查表获取报告类型和需提取的字段
            extraction_rule = self._REPORT_EXTRACTION_MAP.get(output_key)
            if extraction_rule is None:
                continue

            report_type, field_names = extraction_rule

            # 按规则提取字段，遇到 None 则跳过该条报告 (例如智能选择缺少 reason)
            report_entry = {ke.KEY_TYPE: report_type}
            for field in field_names:
                value = fix_data.get(field)
                if value is None:
                    break
                report_entry[field] = value

            self.context_builder.set_enhance_report(step_name, report_entry)
