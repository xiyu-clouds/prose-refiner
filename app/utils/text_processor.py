import re
from typing import List, Dict, Tuple
from app.common import keys as ke
from app.core.registry.global_singleton_registry import GlobalSingletonRegistry
from app.utils.logger import LoggerManager as logger


class PunctuationProcessor:
    """标点处理器 - 从引擎获取标点规则配置"""
    CHINESE_NAME = "标点处理器"

    def __init__(self):
        rules = self._load_rules()
        self._validate_rules(rules)
        self.half_to_full = rules.get(ke.KEY_HALF_TO_FULL, {})
        self.full_to_half = {v: k for k, v in self.half_to_full.items()}
        self.invalid_punctuation_patterns = rules.get(ke.KEY_INVALID_PUNCTUATION_PATTERNS, [])
        self.missing_space_patterns = rules.get(ke.KEY_MISSING_SPACE_PATTERNS, [])
        self.wrong_punctuation_patterns = rules.get(ke.KEY_WRONG_PUNCTUATION_PATTERNS, [])

    @staticmethod
    def _get_engine():
        registry = GlobalSingletonRegistry.get_instance_sync()
        return registry.get_cognitive_engine()

    def _load_rules(self) -> Dict:
        try:
            engine = self._get_engine()
            if engine and hasattr(engine, 'punctuation_config_get_config'):
                rules = engine.punctuation_config_get_config()
                if isinstance(rules, dict):
                    return rules
        except Exception:
            pass
        return {
            ke.KEY_HALF_TO_FULL: {},
            ke.KEY_INVALID_PUNCTUATION_PATTERNS: [],
            ke.KEY_MISSING_SPACE_PATTERNS: [],
            ke.KEY_WRONG_PUNCTUATION_PATTERNS: [],
        }

    def _validate_rules(self, rules: Dict) -> None:
        self._fix_patterns(rules, ke.KEY_INVALID_PUNCTUATION_PATTERNS)
        self._fix_patterns(rules, ke.KEY_MISSING_SPACE_PATTERNS)
        self._fix_patterns(rules, ke.KEY_WRONG_PUNCTUATION_PATTERNS)

    def _fix_patterns(self, rules: Dict, key: str) -> None:
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
        if not pattern:
            return True
        try:
            re.compile(pattern)
            return True
        except re.error:
            return False

    def _fix_regex(self, pattern: str):
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
        fixed = pattern
        fixed = fixed.replace('\\', '\\\\')
        return fixed

    def convert_half_to_full(self, text: str) -> str:
        return ''.join([self.half_to_full.get(char, char) for char in text])

    def convert_full_to_half(self, text: str) -> str:
        return ''.join([self.full_to_half.get(char, char) for char in text])

    def normalize_punctuation(self, text: str, prefer_fullwidth: bool = True) -> str:
        return self.convert_half_to_full(text) if prefer_fullwidth else self.convert_full_to_half(text)

    def detect_invalid_punctuation(self, text: str) -> List[Dict]:
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
        issues = []
        fixed_text = text

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

        fixed_text = self.normalize_punctuation(fixed_text)
        fixed_text = re.sub(r'[ \t]+', ' ', fixed_text)
        fixed_text = fixed_text.strip()

        return fixed_text, issues


class TextProcessor:
    """文本处理器 - 综合处理接口"""

    def __init__(self):
        self.punctuation_processor = PunctuationProcessor()

    def analyze(self, text: str) -> Dict:
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
        fixed_text, fix_records = self.punctuation_processor.auto_fix_punctuation(text)
        analysis = self.analyze(fixed_text)
        return fixed_text, fix_records, analysis