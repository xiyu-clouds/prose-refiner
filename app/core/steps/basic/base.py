import re
from app.common import keys as ke
from typing import Dict, Any
from app.core.steps.basic.analysis import TextAnalyzer
from app.core.steps.basic.pure_paragraph_splitter import PureParagraphSplitter
from app.core.steps.basic.spell_checker import SpellChecker
from app.core.steps.basic.text_processor import TextProcessor


class Preprocessor:
    """文本预处理统一入口"""
    CHINESE_NAME = "文本预处理统一入口"

    def __init__(self, context_builder):
        self.context_builder = context_builder
        self.text_processor = TextProcessor()
        self.spell_checker = SpellChecker()
        self.text_analyzer = TextAnalyzer()
        sentence_chars = self._extract_sentence_end_chars(
            self.text_analyzer.sentence_pattern
        )
        self.pure_paragraph_splitter = PureParagraphSplitter(
            sentence_end_chars=sentence_chars,
            min_chars=self.text_analyzer.paragraph_splitter_min_chars,
            target_chars=self.text_analyzer.paragraph_splitter_target_chars,
            char_tolerance=self.text_analyzer.paragraph_splitter_char_tolerance
        )

    @staticmethod
    def _extract_sentence_end_chars(sentence_pattern: str) -> str:
        """
        从配置的正则表达式（如 "[。！？…\\.\\!\\?]+"）中提取句末标点字符集。
        返回去重后的字符串，例如 "!?.。！？…"。
        若无法提取任何字符，返回空字符串。
        """
        # 去除首尾的 '[' 和 ']+' 等量词
        inner = re.sub(r'^\[|]\+?$', '', sentence_pattern)
        if not inner:
            return ""

        chars = set()
        ii = 0
        while ii < len(inner):
            if inner[ii] == '\\' and ii + 1 < len(inner):
                # 转义字符，取后一个字符（如 \. 取 .）
                chars.add(inner[ii + 1])
                ii += 2
            else:
                chars.add(inner[ii])
                ii += 1
        return ''.join(chars)

    async def process(self, text: str) -> Dict[str, Any]:
        """
        执行全量预处理流程。
        顺序：标点修复（含分析） -> 常见错词修复 -> 的得地专项修复 -> 完整文本分析
        """
        all_fixes = []

        # 1. 标点处理
        fixed_text, punct_fixes, _ = self.text_processor.fix(text)
        all_fixes.extend(punct_fixes)

        # 2. 常见错别字修复
        fixed_text, spell_fixes = self.spell_checker.auto_fix_wrong_characters(fixed_text)
        all_fixes.extend(spell_fixes)

        # 3. 的得地专项修复
        fixed_text, de_fixes = self.spell_checker.auto_fix_de_errors(fixed_text)
        all_fixes.extend(de_fixes)

        # 4. 完整的文本分析（基于最终清洗文本）
        analysis_report = self.text_analyzer.analyze(fixed_text)

        # 5. 段落分离（产出有序段落列表）
        paragraphs = self.pure_paragraph_splitter.split(fixed_text)

        # 6. 将本地预处理报告存入上下文管理器
        self.context_builder.set_basic_report({
            ke.KEY_FIX_RECORDS: all_fixes,
            ke.KEY_ANALYSIS_REPORT: analysis_report,
        })

        return {
            ke.KEY_ORIGINAL_TEXT: text,
            ke.KEY_CLEANED_TEXT: fixed_text,
            ke.KEY_FIX_RECORDS: all_fixes,
            ke.KEY_ANALYSIS_REPORT: analysis_report,
            ke.KEY_PARAGRAPHS: paragraphs
        }
