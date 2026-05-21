import hashlib
import re
from typing import List, Dict, Tuple, Any
from app.core.steps.rule.base import BaseSteps
from app.common import keys as ke
from app.utils.logger import LoggerManager as logger


class PreprocessingStep(BaseSteps):
    CHINESE_NAME = "串行 - 预处理"

    def execution_mode(self) -> str:
        return ke.KEY_SERIAL

    def get_step_type(self) -> str:
        return ke.KEY_SERIAL_PREPROCESSING

    @staticmethod
    def _parse_fix_mapping(issues: List[str]) -> Dict[str, str]:
        """从 issues_fixed 中解析 {错误词: 正确词}，格式：[类别] 错误片段 -> 正确片段"""
        mapping = {}
        # 匹配模式：[任意类别] 错误内容 -> 正确内容
        pattern = re.compile(r'^\[[^]]+]\s*(.+?)\s*->\s*(.+)$')
        for issue in issues:
            match = pattern.match(issue.strip())
            if match:
                wrong = match.group(1).strip()
                correct = match.group(2).strip()
                if wrong and correct:
                    mapping[wrong] = correct
        return mapping

    @staticmethod
    def _apply_fixes(text: str, fixes: Dict[str, str]) -> str:
        """强制应用所有累积修正"""
        for wrong, correct in fixes.items():
            text = text.replace(wrong, correct)
        return text

    @staticmethod
    def _compute_hash(text: str) -> str:
        return hashlib.md5(text.encode(ke.KEY_UTF_8)).hexdigest()

    async def post_process(self, results: List[Tuple[Any, Dict]]) -> None:
        cumulative_fixes: Dict[str, str] = {}
        text_hashes: List[str] = []

        for result, task in results:
            if not result.success():
                continue

            step_name = task.get(ke.KEY_NAME)
            output_key = task.get(ke.KEY_OUTPUT_KEY)

            # 一次性获取修复数据容器
            content = result.content
            if not isinstance(content, dict):
                continue
            fix_data = content.get(output_key)
            if not isinstance(fix_data, dict):
                continue

            # 提取修正记录并更新累积表
            issues_fixed = fix_data.get(ke.KEY_ISSUES_FIXED)
            if issues_fixed:
                self.context_builder.set_preprocessing_report(step_name, issues_fixed)
                new_fixes = self._parse_fix_mapping(issues_fixed)
                cumulative_fixes.update(new_fixes)

            # 提取模型产出的清洗文本
            cleaned = fix_data.get(ke.KEY_CLEANED_TEXT)
            if cleaned is None:
                continue

            current_hash = self._compute_hash(cleaned)
            # 哈希回退告警（仅监控）
            if text_hashes and current_hash in text_hashes:
                logger.warning(f"文本哈希回退至前序版本，步骤: {step_name}", module_name=self.CHINESE_NAME)
            text_hashes.append(current_hash)

            # 词级强制修复
            regressions = [wrong for wrong in cumulative_fixes if wrong in cleaned]
            if regressions:
                logger.warning(f"检测到 {len(regressions)} 处已修正词回退，步骤: {step_name}，执行强制修复", module_name=self.CHINESE_NAME)
                cleaned = self._apply_fixes(cleaned, cumulative_fixes)
                fix_data[ke.KEY_CLEANED_TEXT] = cleaned  # 写回修正值
                self.context_builder.set_preprocessing_report(
                    "自动回退修复",
                    [f"[回退修复] 强制应用累积修正，共 {len(regressions)} 处"]
                )

            # 持久化原始响应
            context_data = {**result.to_dict(), ke.KEY_NAME: step_name}
            self.context_builder.update_context(context_data)
