import re
from typing import List


class PureParagraphSplitter:
    """
    纯段落拆分器：输出纯净的段落文本列表，无任何元数据。
    规则：
    - 自动识别分段符：空行 > 单换行 > 整篇
    - 过短段落向前合并（保留换行）
    - 超长段落按自然断点切分：换行 > 句末标点 > 向前寻找句末标点
    """
    CHINESE_NAME = "纯段落拆分器"

    def __init__(
            self,
            sentence_end_chars: str,
            min_chars: int,
            target_chars: int,
            char_tolerance: int,
    ):
        self.min_chars = min_chars
        self.target_chars = target_chars
        self.char_tolerance = char_tolerance
        # 构造匹配任意单个句末字符的正则
        self.sentence_end_pattern = re.compile(f"[{re.escape(sentence_end_chars)}]")

    def split(self, text: str) -> List[str]:
        """返回纯净的段落列表"""
        if not text:
            return []

        # 1. 规范化换行
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # 2. 提取原始段落（保留内部换行）
        raw_paras = self._extract_raw_paragraphs(text)

        # 3. 清理每段的首尾空白，过滤空段
        cleaned = [p.strip() for p in raw_paras if p.strip()]

        # 4. 合并过短段落
        merged = self._merge_short_paragraphs(cleaned)

        # 5. 拆分超长段落
        final = self._split_long_paragraphs(merged)

        return final

    @staticmethod
    def _extract_raw_paragraphs(text: str) -> List[str]:
        """提取原始段落片段（保留内部换行）"""
        # 检测是否有连续空行
        if re.search(r'\n\s*\n', text):
            parts = re.split(r'\n\s*\n', text)
            return [p for p in parts if p.strip()]
        # 检测是否有单换行
        if '\n' in text:
            return [p for p in text.split('\n') if p.strip()]
        # 无换行
        return [text]

    def _merge_short_paragraphs(self, paragraphs: List[str]) -> List[str]:
        """向前合并过短段落，保留换行符"""
        if len(paragraphs) <= 1:
            return paragraphs

        merged = []
        for para in paragraphs:
            if len(para) >= self.min_chars or not merged:
                merged.append(para)
            else:
                # 向前合并：上一段 + '\n' + 当前段
                merged[-1] = merged[-1] + '\n' + para
        return merged

    def _split_long_paragraphs(self, paragraphs: List[str]) -> List[str]:
        """对超长段落进行智能切分"""
        result = []
        for para in paragraphs:
            if len(para) <= self.target_chars + self.char_tolerance:
                result.append(para)
            else:
                result.extend(self._split_single_long_para(para))
        return result

    def _split_single_long_para(self, text: str) -> List[str]:
        """将单个超长段落切分为多个语义连贯的段落"""
        parts = []
        start = 0
        n = len(text)

        while start < n:
            # 剩余部分不再超长
            if n - start <= self.target_chars + self.char_tolerance:
                parts.append(text[start:].strip())
                break

            # 搜索区间：[target, target+tolerance]
            search_end = min(start + self.target_chars + self.char_tolerance, n)
            window = text[start:search_end]

            # 1. 优先找换行符
            nl_pos = window.rfind('\n')
            if nl_pos != -1:
                cut = start + nl_pos + 1  # 换行符归前一段
                part = text[start:cut].strip()
                if part:
                    parts.append(part)
                start = cut
                continue

            # 2. 在区间内找最后一个句末标点
            sentence_cut = self._find_last_sentence_end_in_range(text, start, search_end)
            if sentence_cut != -1:
                cut = sentence_cut + 1  # 标点归前一段
                part = text[start:cut].strip()
                if part:
                    parts.append(part)
                start = cut
                continue

            # 3. 区间内无自然断点，退回 target 以内寻找最后一个句末标点
            inner_cut = self._find_last_sentence_end_in_range(text, start, start + self.target_chars)
            if inner_cut != -1:
                cut = inner_cut + 1
                part = text[start:cut].strip()
                if part:
                    parts.append(part)
                start = cut
                continue

            # 4. 极端情况：target 以内也无任何句末标点（例如全是英文或数字）
            #    则安全后退：在 target_chars 处切断，但尽量不切断单词（简化处理：直接切）
            cut = start + self.target_chars
            part = text[start:cut].strip()
            if part:
                parts.append(part)
            start = cut

        return parts

    def _find_last_sentence_end_in_range(self, text: str, start: int, end: int) -> int:
        """在 [start, end) 区间内返回最后一个句末标点的索引，找不到返回 -1"""
        sub = text[start:end]
        last_idx = -1
        for m in self.sentence_end_pattern.finditer(sub):
            last_idx = start + m.end() - 1
        return last_idx
