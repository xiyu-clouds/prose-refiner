from typing import List, Dict, Any
from app.core.steps.text.base import BaseText
from app.common import keys as ke
from app.common import values as va
from app.utils.logger import LoggerManager as logger


class PolishStep(BaseText):
    """
    串行打磨步骤的具体实现
    """
    CHINESE_NAME = "串行 - 打磨"

    def execution_mode(self) -> str:
        return ke.KEY_SERIAL

    def get_step_type(self) -> str:
        return ke.KEY_SERIAL_POLISH

    def _format_auxiliary_report(self, aggregation_reports: List[Dict]) -> str:
        """将聚合报告格式化为精炼的自然语言辅助信息，仅保留前7条高优先级任务。"""
        if not aggregation_reports:
            return ""

        data = aggregation_reports[-1].get(ke.KEY_DATA, {})
        tasks = data.get(ke.KEY_TASKS, [])
        if not tasks:
            return ""

        # 排序并截取
        top_tasks = sorted(
            tasks,
            key=lambda t: va.VAL_PRIORITY_ORDER.get(t.get(ke.KEY_PRIORITY, "P2"), 2)
        )[:7]

        # 将每条任务转换为描述字符串
        task_descriptions = [self._format_single_task(task) for task in top_tasks]
        task_descriptions = [d for d in task_descriptions if d]  # 过滤空描述

        if not task_descriptions:
            return ""

        lines = ["以下为按优先级排序的修复建议："] + task_descriptions

        # 聚合备注
        notes = data.get(ke.KEY_AGGREGATION_NOTES, [])
        if notes:
            lines.append("聚合备注：" + "；".join(notes))

        return "\n\n".join(lines)

    @staticmethod
    def _format_single_task(task: Dict) -> str:
        """格式化单条任务，仅拼接存在的字段。"""
        parts = []

        # 头部：[优先级][类别]
        priority = task.get(ke.KEY_PRIORITY)
        category = task.get(ke.KEY_CATEGORY)
        if priority or category:
            header = f"[{priority or ''}][{category or ''}]" if priority and category else f"[{priority or category}]"
            parts.append(header)

        # 问题摘要
        target = task.get(ke.KEY_TARGET_ISSUE)
        if target:
            parts.append(target)

        if not parts:
            return ""

        line = " ".join(parts)

        # 原文片段
        fragment = task.get(ke.KEY_ORIGINAL_FRAGMENT)
        if fragment:
            line += f"\n原文片段：「{fragment}」"

        # 建议操作
        action = task.get(ke.KEY_SUGGESTED_ACTION)
        if action:
            line += f"\n建议操作：{action}"

        return line

    async def execute(self, injection_params: Dict[str, Any] = None) -> None:
        """重写 execute，在调用父类前动态注入辅助聚合报告"""
        if injection_params is None:
            injection_params = {}

        reports = self.context_builder.get_current_aggregation_report()
        if not reports:
            logger.info("无当前粒度的聚合报告，跳过辅助信息注入", module_name=self.CHINESE_NAME)
            auxiliary_report = ""
        else:
            auxiliary_report = self._format_auxiliary_report(reports)

        injection_params[ke.KEY_AUXILIARY_DIAGNOSIS_REPORT] = auxiliary_report or ""

        await super().execute(injection_params)

    async def post_process(self, results: List[tuple]) -> None:
        for result, task in results:
            if not result.success():
                continue

            step_name = task.get(ke.KEY_NAME)
            output_key = task.get(ke.KEY_OUTPUT_KEY)

            context_data = {**result.to_dict(), ke.KEY_NAME: step_name}
            self.context_builder.update_context(context_data)

            issues_fixed = self._extract_cleaned_text(result, output_key, ke.KEY_ISSUES_FIXED)
            if issues_fixed is not None:
                self.context_builder.set_polish_report(step_name, issues_fixed)
