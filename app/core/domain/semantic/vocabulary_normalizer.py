"""语义词汇归一化工具 —— 三类实体（角色/时间/地点）的标点修正、错别字修正、总上限截断。

从 routers/semantic_vocabularies.py 提取，保持函数签名与行为完全一致。
被 routers/semantic_vocabularies.py 引用。
"""

import dataclasses
import json
import re
from typing import Any, Dict, List, Optional

from app.common import values as va
from app.config.config import config
from app.utils.text_processor import PunctuationProcessor
from app.utils.spell_checker import SpellChecker

CATEGORY_ENTITY = "entity"
CATEGORY_TEMPORAL = "temporal"
CATEGORY_LOCATION = "location"

_CHAR_TOP_KEYS = frozenset({"type", "gender", "identity", "secret", "relationships"})
_TIME_TOP_KEYS = frozenset({"type", "sort_index", "description"})
_LOC_TOP_KEYS = frozenset({"type", "parent_id", "description"})

_SENTENCE_END_PATTERN = re.compile(config.PARAGRAPH_SPLIT_SENTENCE_PATTERN)


def _extract_sentence_end_chars(sentence_pattern: str) -> str:
    """提取句子结束字符（复用段落拆分器逻辑）"""
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


def _cut_sentence_aware(text: str, max_len: int) -> str:
    """句子感知截断：在max_len以内找到最后一个句尾标点作为截断点，确保不超过上限且在完整句子处结束"""
    s = _s(text)
    if len(s) <= max_len:
        return s
    window = s[:max_len]
    last_sentence_end = -1
    for m in _SENTENCE_END_PATTERN.finditer(window):
        last_sentence_end = m.end()
    if last_sentence_end > 0:
        return s[:last_sentence_end]
    return s[:max_len]


def _s(v: Any) -> str:
    return "" if v is None else str(v)


def _cut(text: Any, max_len: int) -> str:
    s = _s(text)
    if max_len <= 0:
        return ""
    return s if len(s) <= max_len else s[:max_len]


def _cut_aliases(aliases: Any, max_joined: int) -> List[str]:
    if not isinstance(aliases, list):
        return []
    cleaned: List[str] = []
    for a in aliases:
        s = _s(a).strip()
        if s:
            cleaned.append(s)
    joined = ",".join(cleaned)
    if len(joined) <= max_joined:
        return cleaned
    current: List[str] = []
    running = 0
    for a in cleaned:
        extra = len(a) + (1 if current else 0)
        if running + extra > max_joined:
            break
        current.append(a)
        running += extra
    if not current and cleaned:
        first = cleaned[0]
        allow = max_joined
        current = [first if len(first) <= allow else first[:allow]]
    return current


def _cut_attrs(
    attrs: Any,
    known_keys: frozenset,
    key_max: int,
    val_max: int,
    max_custom_count: Optional[int] = None,
) -> Dict[str, Any]:
    if not isinstance(attrs, dict):
        return {}
    result: Dict[str, Any] = {}
    custom_count = 0
    for k, v in attrs.items():
        ks = _s(k).strip()
        if not ks:
            continue
        if ks in known_keys:
            result[ks] = v
            continue
        if isinstance(max_custom_count, int) and max_custom_count >= 0:
            if custom_count >= max_custom_count:
                continue
            custom_count += 1
        kk = ks if len(ks) <= key_max else ks[:key_max]
        if isinstance(v, (dict, list)):
            result[kk] = v
        else:
            vs = _s(v)
            result[kk] = vs if len(vs) <= val_max else vs[:val_max]
    return result


def _cut_relationships(
    rels: Any,
    type_max: int,
    max_count: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if not isinstance(rels, list):
        return []
    out: List[Dict[str, Any]] = []
    for idx, r in enumerate(rels):
        if not isinstance(r, dict):
            continue
        if isinstance(max_count, int) and max_count >= 0 and idx >= max_count:
            break
        new_rel: Dict[str, Any] = {}
        for k, v in r.items():
            if k == "type":
                new_rel[k] = _cut(v, type_max)
            else:
                new_rel[k] = v
        out.append(new_rel)
    return out


def _total_entity(payload: Dict[str, Any]) -> int:
    total = 0
    total += len(_s(payload.get("name")))
    attrs = payload.get("attributes") or {}
    if isinstance(attrs, dict):
        total += len(_s(attrs.get("type")))
        total += len(_s(attrs.get("gender")))
        total += len(_s(attrs.get("identity")))
        total += len(_s(attrs.get("secret")))
        rels = attrs.get("relationships")
        if isinstance(rels, list):
            for r in rels:
                if isinstance(r, dict):
                    total += len(_s(r.get("type")))
        for k, v in attrs.items():
            if k in _CHAR_TOP_KEYS:
                continue
            total += len(_s(k))
            if not isinstance(v, (dict, list)):
                total += len(_s(v))
    aliases = payload.get("aliases")
    if isinstance(aliases, list):
        total += len(",".join(_s(a) for a in aliases if _s(a)))
    return total


def _total_temporal(payload: Dict[str, Any]) -> int:
    total = 0
    total += len(_s(payload.get("name")))
    attrs = payload.get("attributes") or {}
    if isinstance(attrs, dict):
        total += len(_s(attrs.get("type")))
        total += len(_s(attrs.get("sort_index")))
        total += len(_s(attrs.get("description")))
        for k, v in attrs.items():
            if k in _TIME_TOP_KEYS:
                continue
            total += len(_s(k))
            if not isinstance(v, (dict, list)):
                total += len(_s(v))
    aliases = payload.get("aliases")
    if isinstance(aliases, list):
        total += len(",".join(_s(a) for a in aliases if _s(a)))
    return total


def _total_location(payload: Dict[str, Any]) -> int:
    total = 0
    total += len(_s(payload.get("name")))
    attrs = payload.get("attributes") or {}
    if isinstance(attrs, dict):
        total += len(_s(attrs.get("type")))
        total += len(_s(attrs.get("parent_id")))
        total += len(_s(attrs.get("description")))
        for k, v in attrs.items():
            if k in _LOC_TOP_KEYS:
                continue
            total += len(_s(k))
            if not isinstance(v, (dict, list)):
                total += len(_s(v))
    aliases = payload.get("aliases")
    if isinstance(aliases, list):
        total += len(",".join(_s(a) for a in aliases if _s(a)))
    return total


def _trim_entity_to_total(payload: Dict[str, Any], max_total: int) -> Dict[str, Any]:
    """句子感知的角色总上限截断：在句尾标点处截断，避免注入半截句子"""
    if _total_entity(payload) <= max_total:
        return payload
    attrs = payload.get("attributes")
    if not isinstance(attrs, dict):
        attrs = {}
    for k, v in list(attrs.items()):
        if k in _CHAR_TOP_KEYS or isinstance(v, (dict, list)):
            continue
        cur = _total_entity(payload)
        if cur <= max_total:
            return payload
        overflow = cur - max_total
        sv = _s(v)
        if len(sv) <= overflow:
            del attrs[k]
        else:
            attrs[k] = _cut_sentence_aware(sv, max(0, len(sv) - overflow))
    for k in [kk for kk in attrs.keys() if kk not in _CHAR_TOP_KEYS]:
        cur = _total_entity(payload)
        if cur <= max_total:
            return payload
        del attrs[k]
    while _total_entity(payload) > max_total and isinstance(payload.get("aliases"), list) and payload["aliases"]:
        payload["aliases"].pop()
    cur = _total_entity(payload)
    if cur > max_total:
        sv = _s(attrs.get("secret"))
        keep = max(0, len(sv) - (cur - max_total))
        attrs["secret"] = _cut_sentence_aware(sv, keep)
    cur = _total_entity(payload)
    if cur > max_total:
        sv = _s(attrs.get("identity"))
        keep = max(0, len(sv) - (cur - max_total))
        attrs["identity"] = _cut_sentence_aware(sv, keep)
    cur = _total_entity(payload)
    if cur > max_total:
        sv = _s(attrs.get("type"))
        keep = max(0, len(sv) - (cur - max_total))
        attrs["type"] = _cut_sentence_aware(sv, keep)
    cur = _total_entity(payload)
    if cur > max_total:
        sv = _s(payload.get("name"))
        keep = max(1, len(sv) - (cur - max_total))
        payload["name"] = _cut_sentence_aware(sv, keep)
    return payload


def _trim_temporal_to_total(payload: Dict[str, Any], max_total: int) -> Dict[str, Any]:
    """句子感知的时间总上限截断：在句尾标点处截断，避免注入半截句子"""
    if _total_temporal(payload) <= max_total:
        return payload
    attrs = payload.get("attributes")
    if not isinstance(attrs, dict):
        attrs = {}
    for k, v in list(attrs.items()):
        if k in _TIME_TOP_KEYS or isinstance(v, (dict, list)):
            continue
        cur = _total_temporal(payload)
        if cur <= max_total:
            return payload
        overflow = cur - max_total
        sv = _s(v)
        if len(sv) <= overflow:
            del attrs[k]
        else:
            attrs[k] = _cut_sentence_aware(sv, max(0, len(sv) - overflow))
    for k in [kk for kk in attrs.keys() if kk not in _TIME_TOP_KEYS]:
        cur = _total_temporal(payload)
        if cur <= max_total:
            return payload
        del attrs[k]
    while _total_temporal(payload) > max_total and isinstance(payload.get("aliases"), list) and payload["aliases"]:
        payload["aliases"].pop()
    cur = _total_temporal(payload)
    if cur > max_total:
        sv = _s(attrs.get("description"))
        keep = max(0, len(sv) - (cur - max_total))
        attrs["description"] = _cut_sentence_aware(sv, keep)
    cur = _total_temporal(payload)
    if cur > max_total:
        sv = _s(attrs.get("type"))
        keep = max(0, len(sv) - (cur - max_total))
        attrs["type"] = _cut_sentence_aware(sv, keep)
    cur = _total_temporal(payload)
    if cur > max_total:
        sv = _s(payload.get("name"))
        keep = max(1, len(sv) - (cur - max_total))
        payload["name"] = _cut_sentence_aware(sv, keep)
    return payload


def _trim_location_to_total(payload: Dict[str, Any], max_total: int) -> Dict[str, Any]:
    """句子感知的地点总上限截断：在句尾标点处截断，避免注入半截句子"""
    if _total_location(payload) <= max_total:
        return payload
    attrs = payload.get("attributes")
    if not isinstance(attrs, dict):
        attrs = {}
    for k, v in list(attrs.items()):
        if k in _LOC_TOP_KEYS or isinstance(v, (dict, list)):
            continue
        cur = _total_location(payload)
        if cur <= max_total:
            return payload
        overflow = cur - max_total
        sv = _s(v)
        if len(sv) <= overflow:
            del attrs[k]
        else:
            attrs[k] = _cut_sentence_aware(sv, max(0, len(sv) - overflow))
    for k in [kk for kk in attrs.keys() if kk not in _LOC_TOP_KEYS]:
        cur = _total_location(payload)
        if cur <= max_total:
            return payload
        del attrs[k]
    while _total_location(payload) > max_total and isinstance(payload.get("aliases"), list) and payload["aliases"]:
        payload["aliases"].pop()
    cur = _total_location(payload)
    if cur > max_total:
        sv = _s(attrs.get("description"))
        keep = max(0, len(sv) - (cur - max_total))
        attrs["description"] = _cut_sentence_aware(sv, keep)
    cur = _total_location(payload)
    if cur > max_total:
        sv = _s(attrs.get("type"))
        keep = max(0, len(sv) - (cur - max_total))
        attrs["type"] = _cut_sentence_aware(sv, keep)
    cur = _total_location(payload)
    if cur > max_total:
        sv = _s(payload.get("name"))
        keep = max(1, len(sv) - (cur - max_total))
        payload["name"] = _cut_sentence_aware(sv, keep)
    return payload


def _normalize_entity(payload: Dict[str, Any]) -> Dict[str, Any]:
    """角色实体标准化：标点修正 → 错别字修正 → 总上限句子感知截断"""
    if not isinstance(payload, dict):
        return payload
    payload = dict(payload)
    attrs = payload.get("attributes")
    if not isinstance(attrs, dict):
        attrs = {}

    punctuation_processor = PunctuationProcessor()
    spell_checker = SpellChecker()

    if isinstance(payload.get("name"), str):
        payload["name"], _ = punctuation_processor.auto_fix_punctuation(payload["name"])
        payload["name"], _ = spell_checker.auto_fix_wrong_characters(payload["name"])

    if isinstance(payload.get("aliases"), list):
        fixed_aliases = []
        for alias in payload["aliases"]:
            if isinstance(alias, str):
                alias, _ = punctuation_processor.auto_fix_punctuation(alias)
                alias, _ = spell_checker.auto_fix_wrong_characters(alias)
                fixed_aliases.append(alias)
        payload["aliases"] = fixed_aliases

    for key in ["type", "gender", "identity", "secret"]:
        if isinstance(attrs.get(key), str):
            fixed_text, _ = punctuation_processor.auto_fix_punctuation(attrs[key])
            attrs[key] = fixed_text
            fixed_text, _ = spell_checker.auto_fix_wrong_characters(attrs[key])
            attrs[key] = fixed_text

    rels = attrs.get("relationships")
    if isinstance(rels, list):
        for rel in rels:
            if isinstance(rel, dict) and isinstance(rel.get("type"), str):
                rel["type"], _ = punctuation_processor.auto_fix_punctuation(rel["type"])
                rel["type"], _ = spell_checker.auto_fix_wrong_characters(rel["type"])

    for k, v in attrs.items():
        if k in _CHAR_TOP_KEYS:
            continue
        if isinstance(v, str):
            attrs[k], _ = punctuation_processor.auto_fix_punctuation(v)
            attrs[k], _ = spell_checker.auto_fix_wrong_characters(attrs[k])

    payload["attributes"] = _cut_attrs(
        attrs,
        _CHAR_TOP_KEYS,
        va.VAL_WEAVE_ATTR_KEY_MAX,
        va.VAL_WEAVE_ATTR_VALUE_MAX,
        max_custom_count=va.VAL_WEAVE_ATTRS_MAX_COUNT_CHARACTER,
    )

    return _trim_entity_to_total(payload, va.VAL_WEAVE_CHAR_TOTAL_MAX)


def _normalize_temporal(payload: Dict[str, Any]) -> Dict[str, Any]:
    """时间实体标准化：标点修正 → 错别字修正 → 总上限句子感知截断"""
    if not isinstance(payload, dict):
        return payload
    payload = dict(payload)
    attrs = payload.get("attributes")
    if not isinstance(attrs, dict):
        attrs = {}

    punctuation_processor = PunctuationProcessor()
    spell_checker = SpellChecker()

    if isinstance(payload.get("name"), str):
        payload["name"], _ = punctuation_processor.auto_fix_punctuation(payload["name"])
        payload["name"], _ = spell_checker.auto_fix_wrong_characters(payload["name"])

    if isinstance(payload.get("aliases"), list):
        fixed_aliases = []
        for alias in payload["aliases"]:
            if isinstance(alias, str):
                alias, _ = punctuation_processor.auto_fix_punctuation(alias)
                alias, _ = spell_checker.auto_fix_wrong_characters(alias)
                fixed_aliases.append(alias)
        payload["aliases"] = fixed_aliases

    for key in ["type", "sort_index", "description"]:
        if isinstance(attrs.get(key), str):
            fixed_text, _ = punctuation_processor.auto_fix_punctuation(attrs[key])
            attrs[key] = fixed_text
            fixed_text, _ = spell_checker.auto_fix_wrong_characters(attrs[key])
            attrs[key] = fixed_text

    for k, v in attrs.items():
        if k in _TIME_TOP_KEYS:
            continue
        if isinstance(v, str):
            fixed_text, _ = punctuation_processor.auto_fix_punctuation(v)
            attrs[k] = fixed_text
            fixed_text, _ = spell_checker.auto_fix_wrong_characters(v)
            attrs[k] = fixed_text

    payload["attributes"] = _cut_attrs(
        attrs,
        _TIME_TOP_KEYS,
        va.VAL_WEAVE_ATTR_KEY_MAX,
        va.VAL_WEAVE_ATTR_VALUE_MAX,
        max_custom_count=va.VAL_WEAVE_ATTRS_MAX_COUNT_TEMPORAL,
    )

    return _trim_temporal_to_total(payload, va.VAL_WEAVE_TIME_TOTAL_MAX)


def _normalize_location(payload: Dict[str, Any]) -> Dict[str, Any]:
    """地点实体标准化：标点修正 → 错别字修正 → 总上限句子感知截断"""
    if not isinstance(payload, dict):
        return payload
    payload = dict(payload)
    attrs = payload.get("attributes")
    if not isinstance(attrs, dict):
        attrs = {}

    punctuation_processor = PunctuationProcessor()
    spell_checker = SpellChecker()

    if isinstance(payload.get("name"), str):
        payload["name"], _ = punctuation_processor.auto_fix_punctuation(payload["name"])
        payload["name"], _ = spell_checker.auto_fix_wrong_characters(payload["name"])

    if isinstance(payload.get("aliases"), list):
        fixed_aliases = []
        for alias in payload["aliases"]:
            if isinstance(alias, str):
                alias, _ = punctuation_processor.auto_fix_punctuation(alias)
                alias, _ = spell_checker.auto_fix_wrong_characters(alias)
                fixed_aliases.append(alias)
        payload["aliases"] = fixed_aliases

    for key in ["type", "parent_id", "description"]:
        if isinstance(attrs.get(key), str):
            fixed_text, _ = punctuation_processor.auto_fix_punctuation(attrs[key])
            attrs[key] = fixed_text
            fixed_text, _ = spell_checker.auto_fix_wrong_characters(attrs[key])
            attrs[key] = fixed_text

    for k, v in attrs.items():
        if k in _LOC_TOP_KEYS:
            continue
        if isinstance(v, str):
            fixed_text, _ = punctuation_processor.auto_fix_punctuation(v)
            attrs[k] = fixed_text
            fixed_text, _ = spell_checker.auto_fix_wrong_characters(v)
            attrs[k] = fixed_text

    payload["attributes"] = _cut_attrs(
        attrs,
        _LOC_TOP_KEYS,
        va.VAL_WEAVE_ATTR_KEY_MAX,
        va.VAL_WEAVE_ATTR_VALUE_MAX,
        max_custom_count=va.VAL_WEAVE_ATTRS_MAX_COUNT_LOCATION,
    )

    return _trim_location_to_total(payload, va.VAL_WEAVE_LOC_TOTAL_MAX)


def normalize_semantic_payload(payload: Dict[str, Any], category_override: Optional[str] = None) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    category = (category_override or payload.get("category") or "").strip()
    if category == CATEGORY_ENTITY:
        return _normalize_entity(payload)
    if category == CATEGORY_TEMPORAL:
        return _normalize_temporal(payload)
    if category == CATEGORY_LOCATION:
        return _normalize_location(payload)
    return payload


def row_to_dict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    try:
        data = getattr(row, "__dict__", None)
        if isinstance(data, dict):
            return dict(data)
    except Exception:
        pass
    try:
        if dataclasses.is_dataclass(row):
            return dataclasses.asdict(row)
    except Exception:
        pass
    return {}
