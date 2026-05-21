"""
文本分析模块 - 可读性与重复内容检测
提供文本可读性分析、句子长度检测、重复内容识别等功能，
帮助评估文本质量和优化阅读体验。
"""

import re
from typing import List, Dict
from collections import Counter

import jieba

from app.utils.logger import LoggerManager as logger
from app.config.config import config
from app.core.steps.basic.config_loader import ConfigLoader
from app.common import keys as ke
from app.utils.file_util import FileUtil


class TextAnalyzer:
    """文本分析器"""

    CHINESE_NAME = "文本分析器"

    def __init__(self):
        """初始化分析规则配置"""
        loader = ConfigLoader()
        rules = loader.get_analysis_rules()
        self.patterns = rules[ke.KEY_PATTERNS]
        self.thresholds = rules[ke.KEY_THRESHOLDS]
        self.readability_rules = rules[ke.KEY_READABILITY]

        self.sentence_pattern = self.patterns[ke.KEY_SENTENCE]
        self.word_pattern = self.patterns[ke.KEY_WORD]
        self.chinese_pattern = self.patterns[ke.KEY_CHINESE]

        # 编译句子分隔正则（用于逐字符匹配）
        self.sentence_end_regex = re.compile(self.sentence_pattern)

        self.max_sentence_length = self.thresholds[ke.KEY_MAX_SENTENCE_LENGTH]
        self.min_sentence_length = self.thresholds[ke.KEY_MIN_SENTENCE_LENGTH]
        self.repeated_word_min_length = self.thresholds[ke.KEY_REPEATED_WORD_MIN_LENGTH]
        self.repeated_word_min_count = self.thresholds[ke.KEY_REPEATED_WORD_MIN_COUNT]
        self.repeated_phrase_min_length = self.thresholds[ke.KEY_REPEATED_PHRASE_MIN_LENGTH]
        self.repeated_phrase_max_length = self.thresholds[ke.KEY_REPEATED_PHRASE_MAX_LENGTH]
        self.repeated_phrase_limit = self.thresholds[ke.KEY_REPEATED_PHRASE_LIMIT]
        self.ngram_min = self.thresholds.get(ke.KEY_REPEATED_PHRASE_NGRAM_MIN, 2)
        self.ngram_max = self.thresholds.get(ke.KEY_REPEATED_PHRASE_NGRAM_MAX, 3)

        # 回退配置与中文加分
        fallback = rules.get(ke.KEY_READABILITY_FALLBACK, {})
        self.fallback_score = fallback.get(ke.KEY_SCORE, 50)
        self.fallback_level = fallback.get(ke.KEY_LEVEL, "困难")
        self.fallback_suggestion = fallback.get(ke.KEY_SUGGESTION, "文本句子过长，建议大量拆分")
        self.chinese_bonus = rules.get(ke.KEY_READABILITY_CHINESE_BONUS, 10)
        self.chinese_ratio_threshold = rules.get(ke.KEY_READABILITY_CHINESE_RATIO_THRESHOLD, 0.5)

        # 加载段落拆分配置（带默认值兜底）
        ps_config = rules.get(ke.KEY_PARAGRAPH_SPLITTER, {})
        self.paragraph_splitter_min_chars = ps_config.get(ke.KEY_MIN_CHARS, 10)
        self.paragraph_splitter_target_chars = ps_config.get(ke.KEY_TARGET_CHARS, 300)
        self.paragraph_splitter_char_tolerance = ps_config.get(ke.KEY_CHAR_TOLERANCE, 50)
        # 加载停用词
        self._stopwords = self._load_stopwords(config.PATH_FILE_STOPWORDS_TXT)

    def _load_stopwords(self, path: str) -> set:
        """加载停用词表，返回集合供快速查找"""
        stopwords = set()
        try:
            file_util = FileUtil()
            content = file_util.read_file(path, auto_decode=True)
            for line in content.splitlines():
                word = line.strip()
                if word:
                    stopwords.add(word)
            logger.debug(f"停用词加载完成，共 {len(stopwords)} 条", module_name=self.CHINESE_NAME)
        except Exception as e:
            logger.warning(f"停用词加载失败，将不使用停用词过滤: {e}", module_name=self.CHINESE_NAME)
        return stopwords

    def split_sentences(self, text: str) -> List[str]:
        """
        按配置的句子分隔符分割句子（不分割引号内的内容）。
        支持中英文句末标点，完全由配置文件驱动。
        """
        result = []
        inside_quotes = False
        current_sentence = []

        for char in text:
            if char in '“"':
                inside_quotes = not inside_quotes
                current_sentence.append(char)
            elif not inside_quotes and self.sentence_end_regex.match(char):
                current_sentence.append(char)
                sentence = ''.join(current_sentence).strip()
                if sentence:
                    result.append(sentence)
                current_sentence = []
            else:
                current_sentence.append(char)

        if current_sentence:
            sentence = ''.join(current_sentence).strip()
            if sentence:
                result.append(sentence)

        return result

    def analyze_sentence_length(self, text: str) -> Dict:
        """
        分析句子长度分布
        Returns:
            分析结果，包含句子数量、平均长度、最大/最小长度和问题句子
        """
        sentences = self.split_sentences(text)
        lengths = [len(s) for s in sentences]

        if not lengths:
            return {
                ke.KEY_SENTENCE_COUNT: 0,
                ke.KEY_AVG_LENGTH: 0,
                ke.KEY_MIN_LENGTH: 0,
                ke.KEY_MAX_LENGTH: 0,
                ke.KEY_ISSUES: []
            }

        avg_length = sum(lengths) / len(lengths)
        min_length = min(lengths)
        max_length = max(lengths)

        issues = []
        for i, (sentence, length) in enumerate(zip(sentences, lengths)):
            if length > self.max_sentence_length:
                issues.append({
                    ke.KEY_TYPE: ke.KEY_TOO_LONG_SENTENCE,
                    ke.KEY_DESCRIPTION: f'句子过长（{length}字），建议拆分',
                    ke.KEY_SENTENCE: sentence[:20] + '...' if length > 20 else sentence,
                    ke.KEY_LENGTH: length,
                    ke.KEY_INDEX: i
                })
            elif length < self.min_sentence_length and sentence.strip():
                issues.append({
                    ke.KEY_TYPE: ke.KEY_TOO_SHORT_SENTENCE,
                    ke.KEY_DESCRIPTION: f'句子过短（{length}字），建议合并',
                    ke.KEY_SENTENCE: sentence,
                    ke.KEY_LENGTH: length,
                    ke.KEY_INDEX: i
                })

        return {
            ke.KEY_SENTENCE_COUNT: len(sentences),
            ke.KEY_AVG_LENGTH: round(avg_length, 2),
            ke.KEY_MIN_LENGTH: min_length,
            ke.KEY_MAX_LENGTH: max_length,
            ke.KEY_ISSUES: issues
        }

    def detect_repeated_words(self, text: str, min_length: int = None, min_count: int = None) -> List[Dict]:
        """
        检测重复出现的词语
        Args:
            text: 输入文本
            min_length: 词语最小长度（默认使用配置值）
            min_count: 最小重复次数（默认使用配置值）
        Returns:
            重复词语列表，按重复次数降序排列
        """
        min_length = min_length or self.repeated_word_min_length
        min_count = min_count or self.repeated_word_min_count

        words = re.findall(self.word_pattern, text)
        word_counts = Counter(words)

        issues = []
        for word, count in word_counts.items():
            if len(word) >= min_length and count >= min_count:
                issues.append({
                    ke.KEY_TYPE: ke.KEY_REPEATED_WORD,
                    ke.KEY_DESCRIPTION: f"词语 '{word}' 重复出现 {count} 次",
                    ke.KEY_WORD: word,
                    ke.KEY_COUNT: count
                })

        issues.sort(key=lambda x: x[ke.KEY_COUNT], reverse=True)
        return issues

    def detect_repeated_sentences(self, text: str) -> List[Dict]:
        """
        检测重复的句子
        Returns:
            重复句子列表，按重复次数降序排列
        """
        sentences = self.split_sentences(text)
        sentence_counts = Counter(sentences)

        issues = []
        for sentence, count in sentence_counts.items():
            if count >= 2:
                issues.append({
                    ke.KEY_TYPE: ke.KEY_REPEATED_SENTENCE,
                    ke.KEY_DESCRIPTION: f"句子重复出现 {count} 次",
                    ke.KEY_SENTENCE: sentence[:30] + '...' if len(sentence) > 30 else sentence,
                    ke.KEY_COUNT: count
                })

        issues.sort(key=lambda x: x[ke.KEY_COUNT], reverse=True)
        return issues

    def detect_repeated_phrases(self, text: str, min_length: int = None, max_length: int = None) -> List[Dict]:
        """
        检测重复出现的短语（基于分词 + 停用词过滤）
        Args:
            text: 输入文本
            min_length: 短语最小字符长度（默认使用配置值）
            max_length: 短语最大字符长度（默认使用配置值）
        Returns:
            重复短语列表，按重复次数降序排列
        """
        min_length = min_length or self.repeated_phrase_min_length
        max_length = max_length or self.repeated_phrase_max_length

        # 分词并过滤停用词、单字词、非中文词
        words = jieba.lcut(text)
        filtered_words = []
        for w in words:
            w = w.strip()
            if not w or w in self._stopwords or len(w) < 2:
                continue
            if not re.match(r'^[\u4e00-\u9fa5]+$', w):
                continue
            filtered_words.append(w)

        # 生成 n-gram 短语
        phrases = []
        for n in range(self.ngram_min, self.ngram_max + 1):
            for i in range(len(filtered_words) - n + 1):
                phrase = ''.join(filtered_words[i:i + n])
                if min_length <= len(phrase) <= max_length:
                    phrases.append(phrase)

        phrase_counts = Counter(phrases)
        issues = []
        for phrase, count in phrase_counts.items():
            if count >= 2:
                issues.append({
                    ke.KEY_TYPE: ke.KEY_REPEATED_PHRASE,
                    ke.KEY_DESCRIPTION: f"短语 '{phrase}' 重复出现 {count} 次",
                    ke.KEY_PHRASE: phrase,
                    ke.KEY_COUNT: count
                })

        issues.sort(key=lambda x: x[ke.KEY_COUNT], reverse=True)
        return issues[:self.repeated_phrase_limit]

    def detect_empty_sentences(self, text: str) -> List[Dict]:
        """
        检测空句子（仅包含标点的句子）
        Returns:
            空句子列表
        """
        sentences = re.split(self.sentence_pattern, text)
        issues = []

        for i, sentence in enumerate(sentences):
            stripped = sentence.strip()
            if not stripped:
                issues.append({
                    ke.KEY_TYPE: ke.KEY_EMPTY_SENTENCE,
                    ke.KEY_DESCRIPTION: f'第 {i + 1} 个句子为空',
                    ke.KEY_INDEX: i
                })

        return issues

    def analyze_readability(self, text: str) -> Dict:
        """
        分析文本可读性
        Returns:
            可读性分析结果，包含评分、难度等级和建议
        """
        sentences = self.split_sentences(text)
        if not sentences:
            return {ke.KEY_SCORE: 0, ke.KEY_LEVEL: '无法分析', ke.KEY_SUGGESTION: '', ke.KEY_AVG_SENTENCE_LENGTH: 0}

        total_chars = sum(len(s) for s in sentences)
        avg_sentence_length = total_chars / len(sentences)

        chinese_chars = len(re.findall(self.chinese_pattern, text))
        total_text_chars = len(re.sub(r'\s+', '', text))
        chinese_ratio = chinese_chars / total_text_chars if total_text_chars > 0 else 0

        score = self.fallback_score
        level = self.fallback_level
        suggestion = self.fallback_suggestion

        for rule in self.readability_rules:
            if rule[ke.KEY_MIN] <= avg_sentence_length <= rule[ke.KEY_MAX]:
                score = rule[ke.KEY_SCORE]
                level = rule[ke.KEY_LEVEL]
                suggestion = rule[ke.KEY_SUGGESTION]
                break

        if chinese_ratio < self.chinese_ratio_threshold:
            score = min(score + self.chinese_bonus, 100)

        return {
            ke.KEY_SCORE: score,
            ke.KEY_LEVEL: level,
            ke.KEY_SUGGESTION: suggestion,
            ke.KEY_AVG_SENTENCE_LENGTH: round(avg_sentence_length, 2),
            ke.KEY_CHINESE_RATIO: round(chinese_ratio, 2)
        }

    def analyze(self, text: str) -> Dict:
        """
        综合分析文本
        Returns:
            完整分析结果字典，包含所有检测项
        """
        result = {
            ke.KEY_SENTENCE_ANALYSIS: self.analyze_sentence_length(text),
            ke.KEY_REPEATED_WORDS: self.detect_repeated_words(text),
            ke.KEY_REPEATED_SENTENCES: self.detect_repeated_sentences(text),
            ke.KEY_REPEATED_PHRASES: self.detect_repeated_phrases(text),
            ke.KEY_EMPTY_SENTENCES: self.detect_empty_sentences(text),
            ke.KEY_READABILITY: self.analyze_readability(text)
        }

        result[ke.KEY_TOTAL_ISSUES] = (
                len(result[ke.KEY_SENTENCE_ANALYSIS][ke.KEY_ISSUES]) +
                len(result[ke.KEY_REPEATED_WORDS]) +
                len(result[ke.KEY_REPEATED_SENTENCES]) +
                len(result[ke.KEY_REPEATED_PHRASES]) +
                len(result[ke.KEY_EMPTY_SENTENCES])
        )

        return result


if __name__ == '__main__':
    analyzer = TextAnalyzer()

    test_text = """这是一段测试文本。这是一段测试文本。它包含重复的内容和重复的内容。这个句子非常长，包含了很多很多的内容，可能会让读者感到疲惫，建议进行适当的拆分以提高可读性。这个句子非常长，包含了很多很多的内容，可能会让读者感到疲惫，建议进行适当的拆分以提高可读性。简短句。测试测试测试重复词语。"""

    print("原始文本：")
    print(test_text)
    print("\n句子长度分析：")
    sentence_analysis = analyzer.analyze_sentence_length(test_text)
    print(f"句子数量: {sentence_analysis['sentence_count']}")
    print(f"平均长度: {sentence_analysis['avg_length']}")
    print(f"问题句子: {len(sentence_analysis['issues'])}")

    print("\n重复词语：")
    for issue in analyzer.detect_repeated_words(test_text):
        print(f"- {issue['description']}")

    print("\n重复句子：")
    for issue in analyzer.detect_repeated_sentences(test_text):
        print(f"- {issue['description']}")

    print("\n重复短语：")
    for issue in analyzer.detect_repeated_phrases(test_text):
        print(f"- {issue['description']}")

    print("\n可读性分析：")
    readability = analyzer.analyze_readability(test_text)
    print(f"评分: {readability['score']}, 难度: {readability['level']}")
    print(f"建议: {readability['suggestion']}")
