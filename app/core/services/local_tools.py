from pathlib import Path
from typing import Set, Dict, List, Optional, Iterable, Any
import jieba
import jieba.analyse
from collections import Counter
from app.config.config import config
from app.utils.file_util import FileUtil
from app.utils.logger import LoggerManager as logger


class LocalTextTools:
    CHINESE_NAME = "本地文本处理工具"
    _instance: Optional["LocalTextTools"] = None

    def __init__(self):
        if LocalTextTools._instance is not None:
            raise RuntimeError("请使用 LocalTextTools.get_instance() 获取单例")

        self.stopwords_path = config.JIEBA_STOPWORDS_PATH
        self.userdict_path = config.JIEBA_USERDICT_PATH
        self.filter_stopwords_default = config.JIEBA_FILTER_STOPWORDS_DEFAULT
        self.min_word_len = config.JIEBA_MIN_WORD_LEN
        self.textrank_top_k = config.TEXTRANK_TOP_K
        self.stopwords = self._load_stopwords(self.stopwords_path)
        self._preload_existing_jieba_userdict()

        # 词库白名单，动态加载后填充
        self.vocab: Dict[str, Set[str]] = {}
        self.category_labels: Dict[str, str] = {}
        self._vocab_loaded = False
        logger.info(
            f"本地文本工具初始化完成，停用词数量: {len(self.stopwords)}",
            module_name=self.CHINESE_NAME
        )

    @classmethod
    def get_instance(cls) -> "LocalTextTools":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def _load_stopwords(path: str) -> set:
        stopwords = set()
        try:
            file_util = FileUtil()
            content = file_util.read_file(path, auto_decode=True)
            for line in content.splitlines():
                word = line.strip()
                if word:
                    stopwords.add(word)
        except Exception as e:
            logger.warning(
                f"停用词加载失败，将不使用过滤: {e}",
                module_name=LocalTextTools.CHINESE_NAME
            )
        return stopwords

    # ======================== jieba 自定义词典（基于 semantic_vocabulary.name）========================
    def _preload_existing_jieba_userdict(self) -> None:
        """启动时预加载磁盘上已存在的 jieba 自定义词典文件（若有）。具体作品内的增删改，由写接口触发 sync_jieba_userdict_for_session 刷新。"""
        try:
            p = Path(str(self.userdict_path).strip()) if self.userdict_path else None
            if not p or not p.is_file():
                return
            count = 0
            with p.open("r", encoding="utf-8") as f:
                for line in f:
                    w = (line or "").split(" " or "\t", 1)[0].strip()
                    if w:
                        count += 1
            if count <= 0:
                return
            jieba.load_userdict(str(p))
            logger.info(
                f"启动预加载 jieba 自定义词典完成，文件={p}，词数={count}",
                module_name=self.CHINESE_NAME,
            )
        except Exception as e:
            logger.warning(
                f"启动预加载 jieba 自定义词典失败，跳过: {e}",
                module_name=self.CHINESE_NAME,
            )

    def _read_existing_userdict_words(self) -> Set[str]:
        """读取旧版 jieba 自定义词典里的所有词，用于合并时不丢失用户原有自定义词。"""
        existing: Set[str] = set()
        p = Path(str(self.userdict_path).strip()) if self.userdict_path else None
        if not p or not p.is_file():
            return existing
        try:
            with p.open("r", encoding="utf-8") as f:
                for line in f:
                    parts = (line or "").strip().split()
                    if not parts:
                        continue
                    w = parts[0].strip()
                    if w:
                        existing.add(w)
        except Exception as e:
            logger.warning(
                f"读旧版 jieba 自定义词典失败，将忽略旧词：{e}",
                module_name=self.CHINESE_NAME,
            )
        return existing

    def _write_jieba_userdict(self, names_iterable: Iterable[Any]) -> None:
        """把传入的 name 集合（与旧版文件已有词合并去重）写入磁盘 jieba 自定义词典，并立刻让内存态 jieba 生效。
        词频统一 5（匹配旧版格式），词性统一 n。"""
        # 1) 先读旧文件里的词，避免同步时丢失用户之前加的自定义词
        existing_words = self._read_existing_userdict_words()
        # 2) 合并旧词 + 新传入的 name，去重、清洗
        normalized: List[str] = []
        seen_normalized: Set[str] = set()
        for raw in list(existing_words) + list(names_iterable or []):
            s = "" if raw is None else str(raw).strip()
            if not s:
                continue
            k = s
            if k in seen_normalized:
                continue
            seen_normalized.add(k)
            normalized.append(s)

        # 3) 确保父目录存在，写文件（UTF-8），词频统一 5，词性统一 n（名词）—— 与旧版格式一致
        p = Path(str(self.userdict_path).strip()) if self.userdict_path else None
        if not p:
            logger.warning(
                "_write_jieba_userdict 跳过：config.JIEBA_USERDICT_PATH 为空",
                module_name=self.CHINESE_NAME,
            )
            return
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("w", encoding="utf-8") as f:
                for w in normalized:
                    safe = w.replace("\n", "").replace("\r", "").replace("\t", " ").replace("  ", " ").strip()
                    if not safe:
                        continue
                    f.write(f"{safe} 5 n\n")
        except Exception as e:
            logger.error(
                f"写 jieba 自定义词典文件失败，文件={p}：{e}",
                module_name=self.CHINESE_NAME,
                exc_info=True,
            )
            raise

        # 4) 内存态显式 add_word 保证权重最新
        try:
            for w in normalized:
                jieba.add_word(w, freq=5, tag="n")
        except Exception as e:
            logger.warning(
                f"jieba.add_word 批量登记失败（文件已写入，下次启动会自动加载）：{e}",
                module_name=self.CHINESE_NAME,
            )
        logger.info(
            f"jieba 自定义词典已同步，词数={len(normalized)}（旧词保留{len(existing_words & set(normalized))}），文件={p}",
            module_name=self.CHINESE_NAME,
        )

    def sync_jieba_userdict_for_session(self, engine: Any, session_id: str) -> None:
        """从 Rust engine 的 semantic_vocabulary_list(session_id, None) 拿全类别的 name，写入 jieba 自定义词典并立即加载。"""
        try:
            if engine is None:
                logger.warning(
                    "sync_jieba_userdict_for_session 跳过：engine 为空",
                    module_name=self.CHINESE_NAME,
                )
                return
            sid = "" if session_id is None else str(session_id).strip()
            if not sid:
                logger.warning(
                    "sync_jieba_userdict_for_session 跳过：session_id 为空",
                    module_name=self.CHINESE_NAME,
                )
                return
            # 拿全类别（category=None）
            resp = engine.semantic_vocabulary_list(sid, None)
            entries: List[Any] = []
            if isinstance(resp, dict):
                entries = list(resp.get("data") or []) if isinstance(resp.get("data"), list) else []
            elif isinstance(resp, list):
                entries = resp
            names: List[str] = []
            for ent in entries:
                if isinstance(ent, dict):
                    name = ent.get("name")
                else:
                    name = getattr(ent, "name", None)
                if name is not None and str(name).strip():
                    names.append(str(name).strip())
            self._write_jieba_userdict(names)
        except Exception as e:
            logger.error(
                f"sync_jieba_userdict_for_session 失败：session_id={session_id}, err={e}",
                module_name=self.CHINESE_NAME,
                exc_info=True,
            )
            # 同步词典失败不影响业务接口（只是分词可能会更糙一点），所以这里不抛 HTTPException

    # ======================== 异步词库加载 ========================
    async def load_vocab_async(self):
        """服务启动后的 warm-up：词库白名单（self.vocab，给 filter_by_category/filter_all 用）当前批次未要求接入引擎，占位保留；
        而「基于 semantic_vocabulary.name 生成的 jieba 自定义词典」则在具体作品每次语义词汇写操作（增/改/删）成功后触发 sync_jieba_userdict_for_session 同步。
        若磁盘上已有现成 userdict 文件，__init__ 阶段已预加载，这里无需重复动作。"""
        logger.info(
            "词库白名单（self.vocab）当前批次未接入引擎 semantic_vocabulary，跳过加载占位；作品内语义词汇变更会在写接口成功后触发 jieba 自定义词典同步",
            module_name=self.CHINESE_NAME,
        )
        self.vocab.clear()
        self.category_labels.clear()
        self._vocab_loaded = True

    # ======================== 分词、关键词、统计 ========================
    def cut_words(self, text: str, filter_stopwords: bool = None, context: str = "") -> list:
        if filter_stopwords is None:
            filter_stopwords = self.filter_stopwords_default
        words = jieba.lcut(text)
        if filter_stopwords and self.stopwords:
            words = [w for w in words if w not in self.stopwords and len(w.strip()) >= self.min_word_len]
        elif not filter_stopwords:
            words = [w for w in words if len(w.strip()) >= self.min_word_len]
        ctx_suffix = f"，类型={context}" if isinstance(context, str) and context.strip() else ""
        logger.debug(f"分词完成{ctx_suffix}，词数: {len(words)}", module_name=self.CHINESE_NAME)
        return words

    def extract_keywords(self, text: str, top_k: int = None, context: str = "") -> list:
        if top_k is None:
            top_k = self.textrank_top_k
        keywords = jieba.analyse.textrank(text, topK=top_k, withWeight=False)
        ctx_suffix = f"，类型={context}" if isinstance(context, str) and context.strip() else ""
        logger.debug(f"TextRank 关键词提取完成{ctx_suffix}，数量: {len(keywords)}", module_name=self.CHINESE_NAME)
        return keywords

    def get_text_stats(self, text: str, words: List[str], keywords: List[str]) -> dict:
        stats = {
            "总字符数": len(text),
            "总词数": len(words)
        }

        # 高频词（基于词频统计，与关键词维度不同）
        word_freq = Counter(words).most_common(config.VOCAB_FILTER_MAX_FREQWORDS)
        stats["高频词"] = [w for w, _ in word_freq]

        # 词库白名单（self.vocab）当前批次未接入引擎，跳过实体类别过滤与关键主题词统计，避免全0的误导日志
        logger.info(
            f"文本统计完成: {stats.get('总字符数', 0)}字符, {stats.get('总词数', 0)}词, "
            f"高频词: {len(stats.get('高频词', []))}个",
            module_name=self.CHINESE_NAME
        )
        return stats

    # ======================== 词库过滤 ========================
    def filter_by_category(self, candidates: List[str], category: str) -> List[str]:
        if not self._vocab_loaded or category not in self.vocab:
            return candidates
        allowed = self.vocab[category]
        result = [w for w in candidates if w in allowed]
        logger.debug(f"白名单过滤 [{category}]: {len(candidates)} → {len(result)}", module_name=self.CHINESE_NAME)
        return result

    def filter_all(self, words: List[str]) -> Dict[str, List[str]]:
        """按所有类别过滤，返回 {category: [matched_words]}"""
        if not self._vocab_loaded:
            return {}
        result = {}
        for cat, allowed in self.vocab.items():
            matched = [w for w in words if w in allowed]
            if matched:
                result[cat] = matched
        logger.debug(f"全类别过滤: 匹配到 {len(result)} 个类别, {sum(len(v) for v in result.values())} 个实体",
                     module_name=self.CHINESE_NAME)
        return result

    def get_category_label(self, category: str) -> str:
        return self.category_labels.get(category, category)

    def filter_events(self, text: str, registered_events: List[str]) -> List[str]:
        """在原文中直接查找已注册事件描述是否出现"""
        matched = []
        for event_desc in registered_events:
            if event_desc in text:
                matched.append(event_desc)
        return matched
