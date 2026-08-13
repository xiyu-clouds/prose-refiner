"""任务 payload 工具 —— 字段白名单过滤、类型强制、全局大纲内容截断。

从 routers/tasks.py 提取，保持函数签名与行为完全一致。
被以下模块引用：
- routers/tasks.py（create_task / semantic_upsert_task / update_task）
- core/domain/capabilities/common.py（_precreate_task_with_indices）
"""

import json
from typing import Any, Dict

from app.common import values as va

_UPDATE_STRIP_KEYS = frozenset({
    "id", "session_id", "sequence", "parent_id", "sort_order",
    "volume_index", "chapter_index",
    "created_at", "updated_at",
})

_TASK_ALLOWED_FIELDS = frozenset({
    "id",
    "session_id",
    "task_type",
    "sequence",
    "parent_id",
    "sort_order",
    "volume_index",
    "chapter_index",
    "status",
    "title",
    "content_text",
    "word_count",
    "created_at",
    "updated_at",
})


def coerce_int(v: Any, default: int = 0) -> int:
    if v is None:
        return default
    if isinstance(v, bool):
        return default
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        ival = int(v)
        return ival if ival == v else default
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return default
        try:
            return int(s, 10)
        except Exception:
            return default
    return default


def sanitize_global_outline_content(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    task_type = payload.get("task_type")
    if task_type != va.VAL_TASK_TYPE_GLOBAL_OUTLINE:
        return payload
    content_text = payload.get("content_text")
    if not isinstance(content_text, str) or not content_text.strip():
        return payload
    try:
        obj = json.loads(content_text)
    except Exception:
        return payload
    if not isinstance(obj, dict):
        return payload
    plot = obj.get("plot") if isinstance(obj.get("plot"), str) else ""
    summary = obj.get("summary") if isinstance(obj.get("summary"), str) else ""
    plot_hard = int(va.VAL_OUTLINE_GLOBAL_PLOT_HARD_CHARS)
    summary_hard = int(va.VAL_OUTLINE_GLOBAL_SUMMARY_HARD_CHARS)
    changed = False
    if len(plot) > plot_hard:
        plot = plot[:plot_hard]
        obj["plot"] = plot
        changed = True
    if len(summary) > summary_hard:
        summary = summary[:summary_hard]
        obj["summary"] = summary
        changed = True
    if changed:
        payload["content_text"] = json.dumps(obj, ensure_ascii=False)
        payload["word_count"] = len(plot) + len(summary)
    return payload


def prepare_create_payload(d: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(d, dict):
        return d
    prepared = {k: v for k, v in d.items() if k in _TASK_ALLOWED_FIELDS}
    prepared.setdefault("id", 0)
    prepared.setdefault("sequence", 0)
    prepared.setdefault("created_at", "")
    prepared.setdefault("updated_at", "")
    prepared["task_type"] = str(prepared.get("task_type", ""))
    # parent_id 的合法值只有两个：
    #   - None  → 表示无根（匹配 SQL "parent_id IS NULL"）
    #   - 正整数 i64 → 明确指向父任务
    # 其他"疑似空"（空串、0、false、undefined 被转的非数）一律视为 None，
    # 禁止 fallback 成 0：因为 0 会被序列化到 Some(0)，与 NULL 是完全不同的语义键，
    # 导致 Rust 层的"parent_id IS NULL/?"幂等匹配命中完全不同的记录，产生重复插入。
    raw_parent = prepared.get("parent_id")
    if raw_parent is None:
        prepared["parent_id"] = None
    elif isinstance(raw_parent, str):
        s = raw_parent.strip()
        if not s:
            prepared["parent_id"] = None
        else:
            try:
                parsed = int(s, 10)
                prepared["parent_id"] = parsed if parsed > 0 else None
            except Exception:
                prepared["parent_id"] = None
    elif isinstance(raw_parent, bool):
        prepared["parent_id"] = None
    elif isinstance(raw_parent, int):
        prepared["parent_id"] = raw_parent if raw_parent > 0 else None
    elif isinstance(raw_parent, float):
        ival = int(raw_parent)
        prepared["parent_id"] = ival if ival > 0 and ival == raw_parent else None
    else:
        prepared["parent_id"] = None
    prepared["sort_order"] = coerce_int(prepared.get("sort_order"), 0)
    prepared = sanitize_global_outline_content(prepared)
    return prepared


def prepare_update_patch(d: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(d, dict):
        return d
    stripped = {
        k: v for k, v in d.items()
        if k in _TASK_ALLOWED_FIELDS and k not in _UPDATE_STRIP_KEYS
    }
    return sanitize_global_outline_content(stripped)
