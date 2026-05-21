from typing import Dict, List, Any
from app.core.steps.rule.base import BaseSteps
from app.common import keys as ke
from app.utils.logger import LoggerManager as logger


class AggregationStep(BaseSteps):
    """
    串行聚合步骤的具体实现
    """
    CHINESE_NAME = "串行 - 聚合"

    def execution_mode(self) -> str:
        return ke.KEY_SERIAL

    def get_step_type(self) -> str:
        return ke.KEY_SERIAL_AGGREGATION

    @staticmethod
    def _format_analysis_reports(reports: List[Dict]) -> str:
        """
        将分析报告列表转换为精炼的自然语言描述。
        输入格式：[{"name": "表达力诊断", "data": {...}}, ...]
        """
        if not reports:
            return ""

        paragraphs = []
        for item in reports:
            step_name = item.get(ke.KEY_NAME)
            data = item.get(ke.KEY_DATA)
            if not step_name or not isinstance(data, dict):
                continue

            # 收集该步骤下所有非空字段的内容
            field_lines = []
            for field_name, issues in data.items():
                if issues and isinstance(issues, list):
                    issues_text = "；".join(str(i) for i in issues)
                    field_lines.append(f"{field_name}: {issues_text}")

            if field_lines:
                paragraph = f"【{step_name}】\n" + "\n".join(field_lines)
                paragraphs.append(paragraph)

        return "\n\n".join(paragraphs) if paragraphs else "各诊断报告未发现明显问题。"

    async def execute(self, injection_params: Dict[str, Any] = None) -> None:
        if injection_params is None:
            injection_params = {}

        reports = self.context_builder.get_current_analysis_report()
        if not reports:
            logger.info("无诊断报告，跳过聚合步骤", module_name=self.CHINESE_NAME)
            return

        diagnosis_reports_str = self._format_analysis_reports(reports)
        injection_params[ke.KEY_DIAGNOSIS_REPORTS] = diagnosis_reports_str

        await super().execute(injection_params)

    async def post_process(self, results: List[tuple]) -> None:
        for result, task in results:
            if not result.success():
                continue

            step_name = task.get(ke.KEY_NAME)
            output_key = task.get(ke.KEY_OUTPUT_KEY)

            context_data = {**result.to_dict(), ke.KEY_NAME: step_name}
            self.context_builder.update_context(context_data)

            content = result.content
            if isinstance(content, dict):
                fix_instruction = content.get(output_key)
                if isinstance(fix_instruction, dict):
                    self.context_builder.set_aggregation_report(step_name, fix_instruction)
