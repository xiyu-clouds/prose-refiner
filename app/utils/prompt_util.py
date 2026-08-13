from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional
from .logger import LoggerManager as logger
from app.common import keys as ke
from app.common import values as va

CHINESE_NAME = "Prompt 工具函数"


def wrap_static_json(text: str) -> str:
    """
    将文本中的单大括号 {} 包裹为双大括号 {{}}，以适配 str.format()。
    用于处理不需要注入变量的静态 JSON 片段。
    """
    if not isinstance(text, str):
        return text
    # 简单粗暴但有效：全量替换
    # 因为这部分内容本身就不应该包含 {var} 占位符
    return text.replace("{", "{{").replace("}", "}}")


def unwrap_static_json(text: str) -> str:
    """
    将格式化后的文本中的双大括号 {{}} 还原为单大括号 {}。
    用于清理最终 Prompt，去除多余字符。
    """
    if not isinstance(text, str):
        return text
    return text.replace("{{", "{").replace("}}", "}")


def extract_placeholders(template: str) -> set[str]:
    """
    安全提取 Python str.format 风格的占位符。
    支持：{name}, {user_id}, {count}
    忽略：{{escaped}}, {timestamp:%Y}, {value:.2f}
    """
    if not isinstance(template, str):
        raise TypeError("提示模板必须是字符串")
    # 匹配未转义的 {identifier...}，只取合法标识符部分
    pattern = r"(?<!\{)\{([_a-zA-Z][_a-zA-Z0-9]*)[^}]*\}(?!\})"
    return set(re.findall(pattern, template))


def safe_format_prompt(template: str, **kwargs: Any) -> str:
    """
    安全格式化 prompt 模板，仅支持关键字传参，杜绝位置错配。

    Raises:
        ValueError: 缺少必需参数
        RuntimeError: 格式化执行失败
    """
    required = extract_placeholders(template)
    provided = set(kwargs.keys())

    missing = required - provided
    if missing:
        raise ValueError(
            f"Prompt 缺少必需参数: {sorted(missing)}\n"
            f"   模板要求: {sorted(required)}\n"
            f"   实际提供: {sorted(provided)}"
        )

    extra = provided - required
    if extra:
        logger.warning("Prompt 接收到未使用的参数", extra={ke.KEY_UNUSED_PARAMS: sorted(extra)}, module_name=CHINESE_NAME)

    try:
        # 转义变量值中的大括号，避免被 str.format() 误解析
        escaped_kwargs = {}
        for k, v in kwargs.items():
            if isinstance(v, str):
                escaped_kwargs[k] = v.replace("{", "{{").replace("}", "}}")
            else:
                escaped_kwargs[k] = v

        # 执行格式化 (此时静态部分仍是 {{}})
        formatted_text = template.format(**escaped_kwargs)

        # 清理静态部分 (将 {{}} 还原为 {})
        final_text = unwrap_static_json(formatted_text)

        return final_text
    except KeyError as e:
        raise RuntimeError(f"Prompt 格式化 KeyError（应已被拦截）: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Prompt 格式化运行时错误: {type(e).__name__}: {e}") from e


# ======================================================================
# Prompt 注入中文化工具（合并自 common/prompt_utils.py，统一工具入口）
#   - 将语义词汇结构化数据转「全中文标签、无空字段、无前端数字ID」的纯文本
# ======================================================================

def _zh_key(field_key: str, mapping: Mapping[str, str], extra_first: bool = False) -> str:
    """多档回退：extra_first=True 时 attribute 创作映射优先，否则场景→通用→原key。"""
    if not isinstance(field_key, str):
        return str(field_key)
    k = field_key.strip()
    if not k:
        return ""
    if extra_first and va.VAL_PROMPT_ATTRIBUTE_FIELD_ZH:
        if k in va.VAL_PROMPT_ATTRIBUTE_FIELD_ZH:
            zh = va.VAL_PROMPT_ATTRIBUTE_FIELD_ZH[k]
            if isinstance(zh, str) and zh.strip():
                return zh.strip()
    if mapping and k in mapping:
        zh = mapping[k]
        if isinstance(zh, str) and zh.strip():
            return zh.strip()
    if va.VAL_PROMPT_GENERIC_FIELD_ZH and k in va.VAL_PROMPT_GENERIC_FIELD_ZH:
        zh = va.VAL_PROMPT_GENERIC_FIELD_ZH[k]
        if isinstance(zh, str) and zh.strip():
            return zh.strip()
    return k


def _is_empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    if isinstance(v, (list, tuple, set, dict)):
        return len(v) == 0
    return False


def _val_to_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple, set)):
        parts = []
        for x in v:
            s = "" if x is None else str(x).strip()
            if s:
                parts.append(s)
        return "、".join(parts)
    if isinstance(v, dict):
        inner = []
        for ik, iv in v.items():
            if _is_empty(iv):
                continue
            ik_s = ik if isinstance(ik, str) else str(ik)
            iv_s = _val_to_str(iv)
            if iv_s:
                inner.append(f"{ik_s}={iv_s}")
        return "，".join(inner)
    return str(v).strip()


def _normalize_value(field_key: str, raw_v: Any) -> str:
    """gender(male→男)/type(hero→男主)/location_type(city→城市) 等值中文化。"""
    mapping = va.VAL_PROMPT_VALUE_ZH or {}
    fk = (field_key or "").strip()

    def _one(x: Any) -> str:
        if x is None:
            return ""
        s = str(x).strip()
        if not s:
            return ""
        if fk and fk in mapping:
            sub = mapping[fk]
            if isinstance(sub, dict):
                low = s.lower()
                if low in sub and isinstance(sub[low], str) and sub[low].strip():
                    return sub[low].strip()
                for raw_k, zh_v in sub.items():
                    if (isinstance(raw_k, str) and raw_k.lower() == low
                            and isinstance(zh_v, str) and zh_v.strip()):
                        return zh_v.strip()
        return s

    if isinstance(raw_v, (list, tuple, set)):
        out = [_one(x) for x in raw_v]
        out = [x for x in out if x]
        return "、".join(out)
    return _one(raw_v)


def build_entity_index(entries: Iterable[Any]) -> Dict[str, str]:
    """全量列表→{entity_id: 姓名（别名）} 索引，用于 relationships / parent_id 反查真实姓名。"""
    if entries is None:
        return {}
    idx: Dict[str, str] = {}
    for e in entries:
        if not isinstance(e, dict):
            continue
        eid = None
        for k in ("id", "entity_id", "targetId", "target_id", "uid", "key"):
            if k in e and e.get(k) is not None and str(e.get(k)).strip():
                eid = str(e[k]).strip()
                break
        if not eid:
            continue
        name = ""
        for k in ("name", "title", "label", "display"):
            v = e.get(k)
            if not _is_empty(v):
                name = str(v).strip()
                break
        if not name:
            continue
        aliases = e.get("aliases")
        alias_join = ""
        if isinstance(aliases, (list, tuple, set)) and aliases:
            clean = [str(a).strip() for a in aliases if not _is_empty(a)]
            if clean:
                alias_join = "、".join(clean)
        if alias_join:
            idx[eid] = f"{name}（{alias_join}）"
        else:
            idx[eid] = name
    return idx


def _format_name_with_aliases(r: Mapping[str, Any]) -> str:
    """昵称格式：姓名（别名：甲、乙）。"""
    name_v = r.get("name")
    if _is_empty(name_v):
        for fallback in ("title", "label", "display", "id"):
            v = r.get(fallback)
            if not _is_empty(v):
                name_v = v
                break
        if _is_empty(name_v):
            return ""
    name = str(name_v).strip()
    aliases = r.get("aliases")
    alias_list: List[str] = []
    if isinstance(aliases, (list, tuple, set)) and aliases:
        alias_list = [str(a).strip() for a in aliases if not _is_empty(a)]
    elif not _is_empty(aliases):
        alias_list = [str(aliases).strip()]
    if alias_list:
        unique_aliases: List[str] = []
        seen = set()
        for a in alias_list:
            if a and a not in seen and a != name:
                seen.add(a)
                unique_aliases.append(a)
        if unique_aliases:
            return f"{name}（别名：{'、'.join(unique_aliases)}）"
    return name


def _format_relationships(
        rels: Any,
        entity_index: Optional[Mapping[str, str]],
) -> str:
    """自然中文子句：对苏浅（浅浅、苏苏）：恋人；对张飞：小弟；对关羽：兄弟（亲密度：亲密）"""
    if not isinstance(rels, (list, tuple)) or not rels:
        return ""
    clauses: List[str] = []
    for rel in rels:
        if not isinstance(rel, Mapping):
            raw = "" if rel is None else str(rel).strip()
            if raw:
                clauses.append(raw)
            continue
        target_id = None
        for tk in ("targetId", "target_id", "target", "to", "towards"):
            if tk in rel and rel.get(tk) is not None and str(rel.get(tk)).strip():
                target_id = str(rel[tk]).strip()
                break
        target_display = ""
        if target_id and entity_index and target_id in entity_index:
            target_display = entity_index[target_id]
        elif "target_name" in rel and not _is_empty(rel.get("target_name")):
            target_display = str(rel["target_name"]).strip()
        elif target_id:
            target_display = f"[人物ID={target_id}]"
        rtype = ""
        for tk in ("type", "kind", "relation", "relationship", "rel_type"):
            if tk in rel and not _is_empty(rel.get(tk)):
                raw_rtype = rel.get(tk)
                rtype = _normalize_value("rel_type", raw_rtype) if isinstance(raw_rtype,
                                                                              (str, list, tuple, set)) else str(
                    raw_rtype).strip()
                break
        extras: List[str] = []
        for ek, ev in rel.items():
            if ek in {"type", "kind", "relation", "relationship", "rel_type",
                      "targetId", "target_id", "target", "to", "towards", "target_name"}:
                continue
            if _is_empty(ev):
                continue
            ek_s = ek if isinstance(ek, str) else str(ek)
            zh_k = _zh_key(ek_s, va.VAL_PROMPT_REL_FIELD_ZH)
            zh_v = _normalize_value(ek_s, ev) if isinstance(ev, (str, list, tuple, set)) else _val_to_str(ev)
            if not zh_v:
                continue
            extras.append(f"{zh_k}：{zh_v}")
        if target_display and rtype:
            base = f"对{target_display}：{rtype}"
        elif target_display:
            base = f"对{target_display}"
        elif rtype:
            base = f"关系：{rtype}"
        else:
            base = ""
        if extras:
            extra_s = "（" + "；".join(extras) + "）"
            base = (base + extra_s) if base else "；".join(extras)
        if base:
            clauses.append(base)
    if not clauses:
        return ""
    return "关系：" + "；".join(clauses)


def _collect_extra_fields(r: Mapping[str, Any], attrs: Mapping[str, Any], mapping: Mapping[str, str]) -> List[str]:
    """收集顶层/attributes 自定义字段（attribute 创作属性映射优先命中）。"""
    STRUCT_KEYS = frozenset({
        "id", "uid", "key", "entity_id", "name", "aliases", "relationships",
        "attributes", "sort_index", "order", "created_at", "updated_at",
        "category", "session_id", "work_id", "status", "deleted",
        "location_type", "time_type",
    })
    parts: List[str] = []
    seen_keys: set = set()

    def _add_field(raw_k: str, v: Any):
        if _is_empty(v):
            return
        k = raw_k.strip() if isinstance(raw_k, str) else str(raw_k)
        if not k or k in seen_keys or k in STRUCT_KEYS:
            return
        if k in {"gender", "identity", "type", "secret", "age", "profession", "birthplace",
                 "family", "修为本质", "description", "desc", "parent_id", "parent",
                 "start", "end", "duration", "coord", "size", "population",
                 "location_type", "time_type"}:
            return
        zh_k = _zh_key(k, mapping, extra_first=True)
        zh_v = _normalize_value(k, v) if isinstance(v, (str, list, tuple, set)) else _val_to_str(v)
        if not zh_v:
            return
        parts.append(f"{zh_k}：{zh_v}")
        seen_keys.add(k)

    for k, v in r.items():
        if isinstance(k, str):
            _add_field(k, v)
    if isinstance(attrs, Mapping):
        for k, v in attrs.items():
            if isinstance(k, str):
                _add_field(k, v)
    return parts


def normalize_entry_for_prompt(
        entry: Any,
        category: str,
        entity_index: Optional[Mapping[str, str]] = None,
        max_chars: Optional[int] = None,
) -> str:
    """单条 entry → 单行中文化纯文本。
    若传 max_chars（正整数），则按「字段优先级 → 关系 → 自定义属性」顺序逐字段预算，
    超出预算的字段直接跳过不写，保证最后一个字段也是完整的，绝不在字段中间硬砍字符串；
    head（姓名+别名）必须保留（身份标识），若 head 自身超过 max_chars 也完整返回。
    """
    if entry is None or not isinstance(entry, Mapping):
        return ""
    r: Mapping[str, Any] = entry
    if not r:
        return ""
    cat = (category or "").strip().lower()
    if cat == "character":
        cat = "entity"
    if cat == "time":
        cat = "temporal"
    if cat in ("temporal", "time"):
        priority = va.VAL_PROMPT_TIME_FIELD_PRIORITY
        mapping = va.VAL_PROMPT_TIME_FIELD_ZH
    elif cat == "location":
        priority = va.VAL_PROMPT_LOC_FIELD_PRIORITY
        mapping = va.VAL_PROMPT_LOC_FIELD_ZH
    else:
        priority = va.VAL_PROMPT_CHAR_FIELD_PRIORITY
        mapping = va.VAL_PROMPT_CHAR_FIELD_ZH
    attrs = r.get("attributes") if isinstance(r.get("attributes"), Mapping) else {}
    head = _format_name_with_aliases(r)
    body: List[str] = []
    for f in priority:
        if f in {"name", "aliases"}:
            continue
        if f == "relationships":
            rel_text = _format_relationships(r.get("relationships"), entity_index)
            if rel_text:
                body.append(rel_text)
            continue
        if f == "attributes":
            continue
        val = r.get(f)
        if _is_empty(val) and isinstance(attrs, Mapping) and f in attrs and not _is_empty(attrs.get(f)):
            val = attrs.get(f)
        if _is_empty(val):
            continue
        zh_k = _zh_key(f, mapping)
        if f in {"parent_id", "parent"} and entity_index:
            parent_id_str = str(val).strip() if val is not None else ""
            if parent_id_str and parent_id_str in entity_index:
                body.append(f"{zh_k}：{entity_index[parent_id_str]}")
                continue
        val_key = f
        if cat == "temporal" and f == "type":
            val_key = "time_type"
        if isinstance(val, (str, list, tuple, set)):
            zh_v = _normalize_value(val_key, val)
        else:
            zh_v = _val_to_str(val)
        if not zh_v:
            continue
        body.append(f"{zh_k}：{zh_v}")
    extra_list = _collect_extra_fields(r, attrs or {}, mapping)
    if extra_list:
        body.extend(extra_list)
    all_chunks: List[str] = []
    if head:
        all_chunks.append(head)
    # 字段级预算截断：逐块判断，不够就跳过，保证字段完整性
    if isinstance(max_chars, int) and max_chars > 0:
        used = sum(len(x) for x in all_chunks) + (len(all_chunks) - 1 if all_chunks else 0)
        for b in body:
            if not b or not isinstance(b, str):
                continue
            s = b.strip()
            if not s:
                continue
            add_len = 1 + len(s)  # 前面一个空格分隔符 + 本块内容
            if used + add_len <= max_chars:
                all_chunks.append(s)
                used += add_len
        return " ".join(all_chunks).strip()
    # 无预算：全量拼接
    for b in body:
        if b and isinstance(b, str) and b.strip():
            all_chunks.append(b.strip())
    return " ".join(all_chunks).strip()


def normalize_entries_for_prompt(
        entries: Iterable[Any],
        category: str,
        all_entries: Optional[Iterable[Any]] = None,
        max_chars_per_entry: Optional[int] = None,
) -> List[str]:
    """批量封装：自动建 id→人名 索引；统一调用入口。
    可选 max_chars_per_entry：单条 entry 字段级字符预算，透传给 normalize_entry_for_prompt。
    """
    if entries is None:
        return []
    src_for_index = list(all_entries) if all_entries is not None else list(entries)
    entity_index = build_entity_index(src_for_index)
    result: List[str] = []
    for e in entries:
        s = normalize_entry_for_prompt(e, category, entity_index, max_chars_per_entry)
        if s:
            result.append(s)
    return result
