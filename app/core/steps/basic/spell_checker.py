"""
拼写检查模块 - 错别字与形近字检测
提供中文错别字检测、形近字识别和易混淆词语检测功能，
支持自动修复常见错误词。
"""
import re
from typing import List, Dict, Tuple
from app.common import keys as ke
from app.core.steps.basic.config_loader import ConfigLoader


class SpellChecker:
    """拼写检查器"""
    CHINESE_NAME = "拼写检查器"

    def __init__(self):
        """初始化拼写规则配置"""
        loader = ConfigLoader()
        rules = loader.get_spell_rules()
        self.wrong_characters = rules[ke.KEY_WRONG_CHARACTERS]
        self.similar_characters = rules[ke.KEY_SIMILAR_CHARACTERS]
        self.common_errors = rules[ke.KEY_COMMON_ERRORS]
        self.de_fix_pairs = rules.get(ke.KEY_DE_FIX_PAIRS, {})

    def detect_wrong_characters(self, text: str) -> List[Dict]:
        """
        检测常见错误词语
        Returns:
            检测到的问题列表，包含错误词、正确建议和位置信息
        """
        issues = []
        for correct, wrong_list in self.common_errors.items():
            for wrong in wrong_list:
                for match in re.finditer(re.escape(wrong), text):
                    issues.append({
                        ke.KEY_TYPE: ke.KEY_WRONG_CHARACTER,
                        ke.KEY_DESCRIPTION: f"'{wrong}' 应为 '{correct}'",
                        ke.KEY_START: match.start(),
                        ke.KEY_END: match.end(),
                        ke.KEY_TEXT: wrong,
                        ke.KEY_SUGGESTION: correct
                    })
        return issues

    def detect_similar_characters(self, text: str) -> List[Dict]:
        """
        检测易混淆的形近字
        Returns:
            检测到的形近字列表，包含可能混淆的字符
        """
        issues = []
        seen_positions = set()

        for i, char in enumerate(text):
            if char in self.similar_characters and i not in seen_positions:
                similar = self.similar_characters[char]
                issues.append({
                    ke.KEY_TYPE: ke.KEY_SIMILAR_CHARACTER,
                    ke.KEY_DESCRIPTION: f"'{char}' 可能与 '{', '.join(similar)}' 混淆",
                    ke.KEY_START: i,
                    ke.KEY_END: i + 1,
                    ke.KEY_TEXT: char,
                    ke.KEY_SIMILAR_CHARS: similar
                })
                seen_positions.add(i)

        return issues

    def detect_confusable_words(self, text: str) -> List[Dict]:
        """
        检测词语中的易混淆单字
        Returns:
            检测到的易混淆词语列表
        """
        issues = []
        words = re.findall(r'[\u4e00-\u9fa5]{2,}', text)
        seen_issues = set()

        for word in words:
            word_start = text.index(word)
            for i, char in enumerate(word):
                if char in self.wrong_characters:
                    for wrong_char in self.wrong_characters[char]:
                        issue_key = (word_start + i, char, wrong_char)
                        if issue_key not in seen_issues:
                            seen_issues.add(issue_key)
                            issues.append({
                                ke.KEY_TYPE: ke.KEY_CONFUSABLE_WORD,
                                ke.KEY_DESCRIPTION: f"词语 '{word}' 中的 '{char}' 可能被误写为 '{wrong_char}'",
                                ke.KEY_START: word_start + i,
                                ke.KEY_END: word_start + i + 1,
                                ke.KEY_TEXT: char,
                                ke.KEY_CONFUSABLE: wrong_char,
                                ke.KEY_WORD: word
                            })

        return issues

    def auto_fix_de_errors(self, text: str) -> Tuple[str, List[Dict]]:
        """
        自动修复"的/得/地"使用错误
        使用预定义的规则映射来修复常见的"的/得/地"错误，避免死循环问题。
        Args:
            text: 输入文本
        Returns:
            (修复后的文本, 修复记录列表)
        """
        f_text = text
        f = []
        applied_fixes = set()

        # 按短语长度降序排列，优先替换长短语，避免短短语干扰
        sorted_pairs = sorted(self.de_fix_pairs.items(), key=lambda item: len(item[0]), reverse=True)

        for wrong, correct in sorted_pairs:
            if wrong in f_text and (wrong, correct) not in applied_fixes:
                f_text = f_text.replace(wrong, correct)
                applied_fixes.add((wrong, correct))
                f.append({
                    ke.KEY_TYPE: ke.KEY_FIXED_DE_ERROR,
                    ke.KEY_DESCRIPTION: f"将 '{wrong}' 替换为 '{correct}'",
                    ke.KEY_COUNT: f_text.count(correct)
                })

        return f_text, f

    def auto_fix_wrong_characters(self, text: str) -> Tuple[str, List[Dict]]:
        """
        自动修复常见错误词语
        Args:
            text: 输入文本
        Returns:
            (修复后的文本, 修复记录列表)
        """
        f_text = text
        f = []
        applied_fixes = set()

        for correct, wrong_list in self.common_errors.items():
            for wrong in wrong_list:
                if wrong in f_text:
                    f_text, count = re.subn(re.escape(wrong), correct, f_text)
                    if count > 0 and (wrong, correct) not in applied_fixes:
                        applied_fixes.add((wrong, correct))
                        f.append({
                            ke.KEY_TYPE: ke.KEY_FIXED_WRONG_CHARACTER,
                            ke.KEY_DESCRIPTION: f"将 '{wrong}' 替换为 '{correct}'",
                            ke.KEY_COUNT: count
                        })

        return f_text, f


if __name__ == '__main__':
    checker = SpellChecker()

    test_text = """这是一段侧试文本，迫不及待的跑，包含错别子和行近字。例入：'不事'应该是'不是'，'以经'应该是'已经'，'问提'应该是'问题'。还有形近字如'人'和'入'容易混肴。"""

    print("原始文本：")
    print(test_text)
    print("\n错别字检测：")
    wrong_chars = checker.detect_wrong_characters(test_text)
    for issue in wrong_chars:
        print(f"- {issue['description']}")

    print("\n形近字检测：")
    similar_chars = checker.detect_similar_characters(test_text)
    for issue in similar_chars[:5]:
        print(f"- {issue['description']}")

    print("\n易混淆词语检测：")
    confusable = checker.detect_confusable_words(test_text)
    for issue in confusable[:5]:
        print(f"- {issue['description']}")

    print("\n修复后文本：")
    fixed_text, fixes1 = checker.auto_fix_wrong_characters(test_text)
    fixed_text, fixes2 = checker.auto_fix_de_errors(fixed_text)
    print(fixed_text)
