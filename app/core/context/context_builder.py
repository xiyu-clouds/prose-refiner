import contextvars
from typing import Dict, Any, List, Optional, Literal
from app.common import keys as ke
from app.utils.logger import LoggerManager as logger

# 协程局部变量：当前处理的段落索引（None 表示全文模式）
_paragraph_index_ctx: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(ke.KEY_PARAGRAPH_INDEX, default=None)


class ContextBuilder:
    CHINESE_NAME = "上下文管理器"

    def __init__(self):
        self.context = {
            ke.KEY_FULL_TEXT: {},
            ke.KEY_PARAGRAPHS: {},
            ke.KEY_SCENE_GUIDE: {},
            ke.KEY_BASIC_REPORT: {}
        }
        self.analysis_report = {
            ke.KEY_FULL_TEXT: [],
            ke.KEY_PARAGRAPHS: []
        }
        self.aggregation_report = {
            ke.KEY_FULL_TEXT: [],
            ke.KEY_PARAGRAPHS: []
        }
        self.enhance_report = {
            ke.KEY_FULL_TEXT: [],
            ke.KEY_PARAGRAPHS: []
        }
        self.polish_report = {
            ke.KEY_FULL_TEXT: [],
            ke.KEY_PARAGRAPHS: []
        }
        self.preprocessing_report = []

    @classmethod
    def get_instance(cls) -> "ContextBuilder":
        """创建并返回一个新的上下文构造器实例"""
        return cls()

    def reset(self) -> None:
        """
        重置上下文状态。
        在每一个新的 Pipeline 任务开始时调用，确保数据隔离。
        """
        self.context = {
            ke.KEY_FULL_TEXT: {},
            ke.KEY_PARAGRAPHS: {},
            ke.KEY_SCENE_GUIDE: {},
            ke.KEY_BASIC_REPORT: {}
        }
        self.analysis_report = {ke.KEY_FULL_TEXT: [], ke.KEY_PARAGRAPHS: []}
        self.aggregation_report = {ke.KEY_FULL_TEXT: [], ke.KEY_PARAGRAPHS: []}
        self.enhance_report = {ke.KEY_FULL_TEXT: [], ke.KEY_PARAGRAPHS: []}
        self.polish_report = {ke.KEY_FULL_TEXT: [], ke.KEY_PARAGRAPHS: []}
        self.preprocessing_report = []
        logger.info("🔄 上下文构造器已重置", module_name=self.CHINESE_NAME)

    def get_context(self, mode: Literal["full_text", "paragraphs"] = None):
        """
        获取上下文。
        - mode=None: 返回完整上下文（包含 full_text 和 paragraphs）
        - mode='full_text': 返回全文上下文
        - mode='paragraphs': 返回段落的上下文
        """
        if mode is None:
            return self.context
        return self.context[mode]

    @staticmethod
    def set_current_paragraph_index(idx: Optional[int]) -> None:
        """设置当前协程的段落索引，用于报告标记"""
        _paragraph_index_ctx.set(idx)

    @staticmethod
    def get_current_paragraph_index() -> Optional[int]:
        """获取当前协程的段落索引"""
        return _paragraph_index_ctx.get()

    def _add_nested_report_entry(self, container: Dict[str, List], step_name: str, content: Any) -> None:
        para_idx = self.get_current_paragraph_index()
        entry = {ke.KEY_NAME: step_name, ke.KEY_DATA: content}
        if para_idx is not None:
            entry[ke.KEY_PARAGRAPH_INDEX] = para_idx
            container[ke.KEY_PARAGRAPHS].append(entry)
        else:
            container[ke.KEY_FULL_TEXT].append(entry)
        logger.debug(f"📋 报告已记录: {step_name} (段落: {para_idx})", module_name=self.CHINESE_NAME)

    def _add_flat_report_entry(self, container: List, step_name: str, content: Any) -> None:
        para_idx = self.get_current_paragraph_index()
        entry = {ke.KEY_NAME: step_name, ke.KEY_DATA: content}
        if para_idx is not None:
            entry[ke.KEY_PARAGRAPH_INDEX] = para_idx
        container.append(entry)
        logger.debug(f"📋 报告已记录: {step_name} (段落: {para_idx})", module_name=self.CHINESE_NAME)

    def get_basic_report(self) -> dict:
        return self.context[ke.KEY_BASIC_REPORT]

    def get_preprocessing_report(self) -> List:
        return self.preprocessing_report

    def get_polish_report(self,  mode: Literal["full_text", "paragraphs"] = None):
        if mode is None:
            return self.analysis_report
        return self.polish_report[mode]

    def get_analysis_report(self,  mode: Literal["full_text", "paragraphs"] = None):
        if mode is None:
            return self.analysis_report
        return self.analysis_report[mode]

    def get_aggregation_report(self,  mode: Literal["full_text", "paragraphs"] = None):
        if mode is None:
            return self.aggregation_report
        return self.aggregation_report[mode]

    def get_enhance_report(self, mode: Literal["full_text", "paragraphs"] = None):
        if mode is None:
            return self.enhance_report
        return self.enhance_report[mode]

    def get_current_enhance_report(self) -> List[Dict]:
        para_idx = self.get_current_paragraph_index()
        if para_idx is None:
            return self.enhance_report[ke.KEY_FULL_TEXT]
        else:
            return [
                r for r in self.enhance_report[ke.KEY_PARAGRAPHS]
                if r.get(ke.KEY_PARAGRAPH_INDEX) == para_idx
            ]

    def get_current_analysis_report(self) -> List[Dict]:
        """返回当前协程对应的分析报告列表（全文级或当前段落级）"""
        para_idx = self.get_current_paragraph_index()
        if para_idx is None:
            return self.analysis_report[ke.KEY_FULL_TEXT]
        else:
            return [
                r for r in self.analysis_report[ke.KEY_PARAGRAPHS]
                if r.get(ke.KEY_PARAGRAPH_INDEX) == para_idx
            ]

    def get_current_aggregation_report(self) -> List[Dict]:
        """返回当前协程对应的聚合报告列表（全文级或当前段落级）"""
        para_idx = self.get_current_paragraph_index()
        if para_idx is None:
            return self.aggregation_report[ke.KEY_FULL_TEXT]
        else:
            return [
                r for r in self.aggregation_report[ke.KEY_PARAGRAPHS]
                if r.get(ke.KEY_PARAGRAPH_INDEX) == para_idx
            ]

    def set_basic_report(self, record: Dict[str, Any]) -> None:
        """直接存入 fix_records 和 analysis_report"""
        self.context[ke.KEY_BASIC_REPORT] = {
            ke.KEY_FIX_RECORDS: record.get(ke.KEY_FIX_RECORDS, []),
            ke.KEY_ANALYSIS_REPORT: record.get(ke.KEY_ANALYSIS_REPORT, {})
        }

    def set_preprocessing_report(self, step_name: str, record: Any) -> None:
        self._add_flat_report_entry(self.preprocessing_report, step_name, record)

    def set_polish_report(self, step_name: str, record: Any) -> None:
        self._add_nested_report_entry(self.polish_report, step_name, record)

    def set_analysis_report(self, step_name: str, report: Any) -> None:
        self._add_nested_report_entry(self.analysis_report, step_name, report)

    def set_aggregation_report(self, step_name: str, report: Any) -> None:
        self._add_nested_report_entry(self.aggregation_report, step_name, report)

    def set_enhance_report(self, step_name: str, report: Any) -> None:
        self._add_nested_report_entry(self.enhance_report, step_name, report)

    def update_context(self, result: Dict[str, Any]) -> None:
        if not self._is_result_valid(result):
            return

        data = result[ke.KEY_CONTENT]
        step_name = result[ke.KEY_NAME]
        para_idx = self.get_current_paragraph_index()

        if para_idx is None:
            self.context[ke.KEY_FULL_TEXT].update(data)
            logger.info("🟢 全文上下文更新成功", extra={ke.KEY_STEP: step_name}, module_name=self.CHINESE_NAME)
        else:
            para_dict = self.context[ke.KEY_PARAGRAPHS].setdefault(para_idx, {})
            para_dict.update(data)
            logger.info(f"🟢 段落 {para_idx} 上下文更新成功", extra={ke.KEY_STEP: step_name}, module_name=self.CHINESE_NAME)

    def _is_result_valid(self, result: Dict[str, Any]) -> bool:
        is_ok = result.get(ke.KEY_OK, False)
        is_valid = result.get(ke.KEY_VALID, False)
        step_name = result.get(ke.KEY_NAME)

        if not is_ok:
            error_msg = self._extract_error_message(result)
            logger.warning(
                f"⚠️ 步骤执行失败: {step_name}",
                module_name=self.CHINESE_NAME,
                extra={ke.KEY_STEP: step_name, ke.KEY_ERROR: error_msg}
            )
            return False

        if not is_valid:
            val_errors = result.get(ke.KEY_ERRORS, []) or [result.get(ke.KEY_MSG, "未知校验错误")]
            logger.warning(
                f"⚠️ 步骤内容无效: {step_name}",
                module_name=self.CHINESE_NAME,
                extra={ke.KEY_STEP: step_name, ke.KEY_ERROR: val_errors}
            )
            return False

        data = result.get(ke.KEY_CONTENT)
        if not isinstance(data, dict) or not data:
            logger.info(f"⚪ 跳过注入: {step_name} (无有效数据)", module_name=self.CHINESE_NAME)
            return False

        return True

    @staticmethod
    def _extract_error_message(result: Dict[str, Any]) -> str:
        """
        优雅地提取错误信息
        """
        errors = result.get(ke.KEY_ERRORS)
        if errors:
            return ";".join(errors)

        msg = result.get(ke.KEY_MSG)
        if msg:
            return msg

        stack = result.get(ke.KEY_STACK)
        if stack:
            return stack.splitlines()[0]

        return "未知错误 (无详细信息)"
