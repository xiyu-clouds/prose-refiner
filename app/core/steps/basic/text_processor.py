"""
文本处理模块 - 标点符号检测与修复
提供中文标点符号的检测、规范化和自动修复功能，
支持半角/全角转换、缺失空格检测、无效标点检测等。
"""

import re
from typing import List, Dict, Tuple
from app.common import keys as ke
from app.core.steps.basic.config_loader import ConfigLoader
from app.utils.logger import LoggerManager as logger


class PunctuationProcessor:
    """标点处理器"""
    CHINESE_NAME = "标点处理器"

    def __init__(self):
        """初始化标点规则配置"""
        loader = ConfigLoader()
        rules = loader.get_punctuation_rules()
        self._validate_rules(rules)
        self.half_to_full = rules[ke.KEY_HALF_TO_FULL]
        self.full_to_half = {v: k for k, v in self.half_to_full.items()}
        self.invalid_punctuation_patterns = rules[ke.KEY_INVALID_PUNCTUATION_PATTERNS]
        self.missing_space_patterns = rules[ke.KEY_MISSING_SPACE_PATTERNS]
        self.wrong_punctuation_patterns = rules[ke.KEY_WRONG_PUNCTUATION_PATTERNS]

    def _validate_rules(self, rules: Dict) -> None:
        """验证并修复配置规则中的正则表达式"""
        self._fix_patterns(rules, ke.KEY_INVALID_PUNCTUATION_PATTERNS)
        self._fix_patterns(rules, ke.KEY_MISSING_SPACE_PATTERNS)
        self._fix_patterns(rules, ke.KEY_WRONG_PUNCTUATION_PATTERNS)

    def _fix_patterns(self, rules: Dict, key: str) -> None:
        """修复指定类型的正则表达式模式"""
        patterns = rules.get(key, [])
        for i in range(len(patterns)):
            item = patterns[i]
            pattern = item[0]
            desc = item[-1]
            if not self._is_valid_regex(pattern):
                fixed_pattern = self._fix_regex(pattern)
                if fixed_pattern:
                    logger.warning(f"自动修复无效正则表达式: {key}, 原模式: '{pattern}', 修复后: '{fixed_pattern}', 描述: {desc}", module_name=self.CHINESE_NAME)
                    if isinstance(item, list):
                        item[0] = fixed_pattern
                    else:
                        patterns[i] = list(item)
                        patterns[i][0] = fixed_pattern
                else:
                    logger.error(f"无法修复无效正则表达式: {key}, 模式: '{pattern}', 描述: {desc}", module_name=self.CHINESE_NAME)
                    raise ValueError(f"无法修复无效正则表达式: {pattern}")

    @staticmethod
    def _is_valid_regex(pattern: str) -> bool:
        """检查正则表达式是否有效"""
        if not pattern:
            return True
        try:
            re.compile(pattern)
            return True
        except re.error:
            return False

    def _fix_regex(self, pattern: str):
        """
        自动修复常见的正则表达式错误
        Returns:
            修复后的正则表达式，如果无法修复返回None
        """
        if not pattern:
            return None

        fixed = pattern

        try:
            re.compile(fixed)
            return fixed
        except re.error:
            pass

        fixed = self._fix_unterminated_char_class(pattern)
        if self._is_valid_regex(fixed):
            return fixed

        fixed = self._fix_unterminated_group(pattern)
        if self._is_valid_regex(fixed):
            return fixed

        fixed = self._fix_escape_issues(pattern)
        if self._is_valid_regex(fixed):
            return fixed

        return None

    @staticmethod
    def _fix_unterminated_char_class(pattern: str) -> str:
        """修复未闭合的字符集"""
        stack = []
        for i, char in enumerate(pattern):
            if char == '[' and (i == 0 or pattern[i-1] != '\\'):
                stack.append(i)
            elif char == ']' and (i == 0 or pattern[i-1] != '\\'):
                if stack:
                    stack.pop()
        if stack:
            return pattern + ']' * len(stack)
        return pattern

    @staticmethod
    def _fix_unterminated_group(pattern: str) -> str:
        """修复未闭合的分组"""
        stack = []
        for i, char in enumerate(pattern):
            if char == '(' and (i == 0 or pattern[i-1] != '\\'):
                stack.append(i)
            elif char == ')' and (i == 0 or pattern[i-1] != '\\'):
                if stack:
                    stack.pop()
        if stack:
            return pattern + ')' * len(stack)
        return pattern

    @staticmethod
    def _fix_escape_issues(pattern: str) -> str:
        """修复转义问题"""
        fixed = pattern
        fixed = fixed.replace('\\', '\\\\')
        return fixed

    def convert_half_to_full(self, text: str) -> str:
        """将半角标点转换为全角标点"""
        return ''.join([self.half_to_full.get(char, char) for char in text])

    def convert_full_to_half(self, text: str) -> str:
        """将全角标点转换为半角标点"""
        return ''.join([self.full_to_half.get(char, char) for char in text])

    def normalize_punctuation(self, text: str, prefer_fullwidth: bool = True) -> str:
        """
        规范化标点符号
        Args:
            text: 输入文本
            prefer_fullwidth: 是否优先使用全角标点
        Returns:
            规范化后的文本
        """
        return self.convert_half_to_full(text) if prefer_fullwidth else self.convert_full_to_half(text)

    def detect_invalid_punctuation(self, text: str) -> List[Dict]:
        """
        检测无效标点（连续重复标点）
        Returns:
            检测到的问题列表，包含类型、描述、位置和内容
        """
        issues = []
        for pattern, desc in self.invalid_punctuation_patterns:
            for match in re.finditer(pattern, text):
                issues.append({
                    ke.KEY_TYPE: ke.KEY_INVALID_PUNCTUATION,
                    ke.KEY_DESCRIPTION: desc,
                    ke.KEY_START: match.start(),
                    ke.KEY_END: match.end(),
                    ke.KEY_TEXT: match.group()
                })
        return issues

    def detect_missing_space(self, text: str) -> List[Dict]:
        """检测缺失空格的情况"""
        issues = []
        for pattern, _, desc in self.missing_space_patterns:
            for match in re.finditer(pattern, text):
                issues.append({
                    ke.KEY_TYPE: ke.KEY_MISSING_SPACE,
                    ke.KEY_DESCRIPTION: desc,
                    ke.KEY_START: match.start(),
                    ke.KEY_END: match.end(),
                    ke.KEY_TEXT: match.group()
                })
        return issues

    def detect_wrong_punctuation(self, text: str) -> List[Dict]:
        """检测错误标点用法"""
        issues = []
        for pattern, _, desc in self.wrong_punctuation_patterns:
            for match in re.finditer(pattern, text):
                issues.append({
                    ke.KEY_TYPE: ke.KEY_WRONG_PUNCTUATION,
                    ke.KEY_DESCRIPTION: desc,
                    ke.KEY_START: match.start(),
                    ke.KEY_END: match.end(),
                    ke.KEY_TEXT: match.group()
                })
        return issues

    def auto_fix_punctuation(self, text: str) -> Tuple[str, List[Dict]]:
        """
        自动修复标点问题
        Args:
            text: 输入文本
        Returns:
            (修复后的文本, 修复记录列表)
        """
        issues = []
        fixed_text = text

        # 修复连续重复标点
        for pattern, desc in self.invalid_punctuation_patterns:
            try:
                fixed_text, count = re.subn(pattern, lambda m: m.group()[0], fixed_text)
                if count > 0:
                    issues.append({ke.KEY_TYPE: ke.KEY_FIXED_INVALID, ke.KEY_DESCRIPTION: desc, ke.KEY_COUNT: count})
            except re.error as e:
                logger.warning(f"跳过无效正则表达式 pattern={pattern}, desc={desc}, error={e}", module_name=self.CHINESE_NAME)

        for pattern, replacement, desc in self.wrong_punctuation_patterns:
            try:
                fixed_text, count = re.subn(pattern, replacement, fixed_text)
                if count > 0:
                    issues.append({ke.KEY_TYPE: ke.KEY_FIXED_WRONG, ke.KEY_DESCRIPTION: desc, ke.KEY_COUNT: count})
            except re.error as e:
                logger.warning(f"跳过无效正则表达式 pattern={pattern}, desc={desc}, error={e}", module_name=self.CHINESE_NAME)

        for pattern, replacement, desc in self.missing_space_patterns:
            try:
                fixed_text, count = re.subn(pattern, replacement, fixed_text)
                if count > 0:
                    issues.append(
                        {ke.KEY_TYPE: ke.KEY_FIXED_MISSING_SPACE, ke.KEY_DESCRIPTION: desc, ke.KEY_COUNT: count})
            except re.error as e:
                logger.warning(f"跳过无效正则表达式 pattern={pattern}, desc={desc}, error={e}", module_name=self.CHINESE_NAME)

        # 统一标点格式
        fixed_text = self.normalize_punctuation(fixed_text)
        # 仅合并水平空格，不合并换行符
        fixed_text = re.sub(r'[ \t]+', ' ', fixed_text)
        # 去除首尾空白（包括换行），但保留文本内部的段落分隔符（多个换行）
        fixed_text = fixed_text.strip()

        return fixed_text, issues


class TextProcessor:
    """文本处理器 - 综合处理接口"""

    def __init__(self):
        self.punctuation_processor = PunctuationProcessor()

    def analyze(self, text: str) -> Dict:
        """
        分析文本中的标点问题
        Returns:
            分析结果字典，包含issues和statistics
        """
        result = {
            ke.KEY_ORIGINAL_TEXT: text,
            ke.KEY_ISSUES: [],
            ke.KEY_STATISTICS: {}
        }

        result[ke.KEY_ISSUES].extend(self.punctuation_processor.detect_invalid_punctuation(text))
        result[ke.KEY_ISSUES].extend(self.punctuation_processor.detect_missing_space(text))
        result[ke.KEY_ISSUES].extend(self.punctuation_processor.detect_wrong_punctuation(text))

        result[ke.KEY_STATISTICS][ke.KEY_CHAR_COUNT] = len(text)
        result[ke.KEY_STATISTICS][ke.KEY_WORD_COUNT] = len(re.sub(r'[\s\n]+', '', text))
        result[ke.KEY_STATISTICS][ke.KEY_ISSUE_COUNT] = len(result[ke.KEY_ISSUES])

        return result

    def fix(self, text: str) -> Tuple[str, List[Dict], Dict]:
        """
        修复文本并返回分析结果
        Returns:
            (修复后的文本, 修复记录列表, 分析结果)
        """
        fixed_text, fix_records = self.punctuation_processor.auto_fix_punctuation(text)
        analysis = self.analyze(fixed_text)
        return fixed_text, fix_records, analysis


if __name__ == '__main__':
    text = """
沈墨六十岁那年的冬天格外冷。

他坐在琴坊里，炉火烧得正旺，噼啪作响，映得满室橘红。膝盖上横着一张刚上完最后一道漆的古琴。琴身乌黑如夜，鹿角霜的灰胎下隐隐透出流水般的断纹，十三颗琴徽在火光里闪着温润的微光。

这是他做的最后一把琴。

并非不能再做，只是不想罢了。这两年，手指关节肿得厉害，握锉刀时总觉力不从心。徒弟们把他的工具都收了起来，说师父你动嘴就行，动手的事我们来。沈墨不语，只是把那把伴他半生的平口刀悄悄留在了枕头底下。

他把琴翻过来，想最后检查一遍龙池和凤沼的弧度。手指摸过龙池边缘时，忽然顿住了。

那里的漆面上，有一道浅浅的指痕。

是上次上漆时不小心按上去的。拇指的纹路清清楚楚地印在琴底，像一枚刻在黑色水面上的印章。沈墨怔怔地看了许久，指腹反复摩挲那个凹陷，想抹平它，指尖却舍不得离开。

他做了一辈子琴，每一把都要求毫无瑕疵。琴面要平整如镜，漆色要匀净如水，岳山和龙龈的弧度要精确到毫厘。唯独这一道指痕，他不想修了。

窗外，雪落无声，渐渐吞没了整个院子。沈墨把琴放回膝上，忽然觉得这把琴有点像他自己——活了一辈子，总该留下点不那么完美的东西。

他抬手轻拨琴弦，琴音低沉浑厚，余韵悠长，如同半句未尽的古老叹息，沉入茫茫雪夜。

后来这把琴被他的大徒弟收进了琴匣，再没拿出来给人看过。匣子里压着一张纸条，是沈墨的字迹：“此琴名‘留白’，岳山处有吾指痕一道。琴有缺，人不全，方是人间的琴。”
    """
    t = TextProcessor()
    a, b,c = t.fix(text)
    print(a)
    print("=======================")
    print(b)
    print("=======================")
    print(c)
