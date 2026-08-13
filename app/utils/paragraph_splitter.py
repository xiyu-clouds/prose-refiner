import re
from typing import List
from app.config.config import config


class ParagraphSplitter:
    """
    段落拆分器：输出纯净的段落文本列表，无任何元数据。
    规则：
    - 自动识别分段符：空行 > 单换行 > 整篇
    - 过短段落向前合并（保留换行）
    - 超长段落按自然断点切分：换行 > 句末标点 > 向前寻找句末标点
    """
    CHINESE_NAME = "段落拆分器"

    def __init__(self):
        self.min_chars = config.PARAGRAPH_SPLIT_MIN_CHARS or 10
        self.target_chars = config.PARAGRAPH_SPLIT_TARGET_CHARS or 300
        self.char_tolerance = config.PARAGRAPH_TOLERANCE or 150
        sentence_end_chars = self._extract_sentence_end_chars(config.PARAGRAPH_SPLIT_SENTENCE_PATTERN or r"[。！？…\\.\\!\\?]+")
        self.sentence_end_pattern = re.compile(f"[{re.escape(sentence_end_chars)}]")

    def split(self, text: str) -> List[str]:
        """返回纯净的段落列表"""
        if not text:
            return []

        text = text.replace('\r\n', '\n').replace('\r', '\n')

        raw_paras = self._extract_raw_paragraphs(text)

        cleaned = [p.strip() for p in raw_paras if p.strip()]

        merged = self._merge_short_paragraphs(cleaned)

        final = self._split_long_paragraphs(merged)

        return final

    @staticmethod
    def _extract_sentence_end_chars(sentence_pattern: str) -> str:
        inner = re.sub(r'^\[|]\+?$', '', sentence_pattern)
        if not inner:
            return ""

        chars = set()
        ii = 0
        while ii < len(inner):
            if inner[ii] == '\\' and ii + 1 < len(inner):
                chars.add(inner[ii + 1])
                ii += 2
            else:
                chars.add(inner[ii])
                ii += 1
        return ''.join(chars)

    @staticmethod
    def _extract_raw_paragraphs(text: str) -> List[str]:
        if re.search(r'\n\s*\n', text):
            parts = re.split(r'\n\s*\n', text)
            return [p for p in parts if p.strip()]
        if '\n' in text:
            return [p for p in text.split('\n') if p.strip()]
        return [text]

    def _merge_short_paragraphs(self, paragraphs: List[str]) -> List[str]:
        if len(paragraphs) <= 1:
            return paragraphs

        merged = []
        for para in paragraphs:
            if len(para) >= self.min_chars or not merged:
                merged.append(para)
            else:
                merged[-1] = merged[-1] + '\n' + para
        return merged

    def _split_long_paragraphs(self, paragraphs: List[str]) -> List[str]:
        result = []
        for para in paragraphs:
            if len(para) <= self.target_chars + self.char_tolerance:
                result.append(para)
            else:
                result.extend(self._split_single_long_para(para))
        return result

    def _split_single_long_para(self, text: str) -> List[str]:
        parts = []
        start = 0
        n = len(text)

        while start < n:
            if n - start <= self.target_chars + self.char_tolerance:
                parts.append(text[start:].strip())
                break

            search_end = min(start + self.target_chars + self.char_tolerance, n)
            window = text[start:search_end]

            nl_pos = window.rfind('\n')
            if nl_pos != -1:
                cut = start + nl_pos + 1
                part = text[start:cut].strip()
                if part:
                    parts.append(part)
                start = cut
                continue

            sentence_cut = self._find_last_sentence_end_in_range(text, start, search_end)
            if sentence_cut != -1:
                cut = sentence_cut + 1
                part = text[start:cut].strip()
                if part:
                    parts.append(part)
                start = cut
                continue

            inner_cut = self._find_last_sentence_end_in_range(text, start, start + self.target_chars)
            if inner_cut != -1:
                cut = inner_cut + 1
                part = text[start:cut].strip()
                if part:
                    parts.append(part)
                start = cut
                continue

            cut = start + self.target_chars
            part = text[start:cut].strip()
            if part:
                parts.append(part)
            start = cut

        return parts

    def _find_last_sentence_end_in_range(self, text: str, start: int, end: int) -> int:
        sub = text[start:end]
        last_idx = -1
        for m in self.sentence_end_pattern.finditer(sub):
            last_idx = start + m.end() - 1
        return last_idx