from typing import List, Any
from app.core.steps.rule.base import BaseSteps
from app.common import keys as ke


class AnalysisStep(BaseSteps):
    """
    并行诊断步骤的具体实现
    """
    CHINESE_NAME = "并行 - 诊断"

    def execution_mode(self) -> str:
        return ke.KEY_PARALLEL

    def get_step_type(self) -> str:
        return ke.KEY_PARALLEL_ANALYSIS

    async def post_process(self, results: List[Any]) -> None:
        for result, task in results:
            if not result.success():
                continue

            step_name = task.get(ke.KEY_NAME)
            output_key = task.get(ke.KEY_OUTPUT_KEY)
            content = result.content
            if isinstance(content, dict):
                fix_data = content.get(output_key)
                if isinstance(fix_data, dict):
                    self.context_builder.set_analysis_report(step_name, fix_data)

            context_data = {**result.to_dict(), ke.KEY_NAME: step_name}
            self.context_builder.update_context(context_data)
