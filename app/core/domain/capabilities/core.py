"""能力执行核心业务逻辑（domain 层）。

从 routers/capabilities.py 提取的非路由代码：常量、工具函数、注入变量构造、
LLM 调用编排、任务预创建与回填、幂等检查等纯业务逻辑。
路由层（routers/capabilities.py）仅保留薄路由，通过显式导入复用本模块能力；
handlers_core 通过本模块互相协作。
"""

import asyncio
import ast
import json
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException

from app.common import keys as ke
from app.common import values as va
from app.utils.prompt_util import normalize_entries_for_prompt, wrap_static_json
from app.utils.text_processor import PunctuationProcessor
from app.utils.spell_checker import SpellChecker
from app.config.config import config
from app.core.services.sse_manager import get_sse_manager
from app.core.registry.global_singleton_registry import GlobalSingletonRegistry
from app.core.domain.tasks.payload_tool import prepare_create_payload as _prepare_create_payload, prepare_update_patch as _prepare_update_patch
from app.utils.logger import LoggerManager as logger

LOG_MODULE = "能力执行"

_VAR_PATTERN = re.compile(r"(?<!{){([_a-zA-Z][_a-zA-Z0-9]*)(:[^}]*)?}(?!})")


async def _get_registry() -> GlobalSingletonRegistry:
    return await GlobalSingletonRegistry.get_instance()


def _mask_text(text: str, limit: int = 200) -> str:
    if not isinstance(text, str):
        return ""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...({len(text)}字符)"


def _record_capability_stat_safely(engine, capability_id: str, success: bool, cost: float) -> None:
    if not capability_id:
        return
    try:
        recorder = getattr(engine, "capability_stat_record", None)
        if callable(recorder):
            recorder(capability_id, bool(success), float(cost or 0.0))
        else:
            old = None
            getter = getattr(engine, "capability_stat_get", None)
            if callable(getter):
                old = getter(capability_id)
            total = 1
            rate = 1.0 if success else 0.0
            avg_cost = float(cost or 0.0)
            avg_imp = {}
            if isinstance(old, dict):
                n = int(old.get("total_executions") or 0)
                old_rate = float(old.get("success_rate") or 0.0)
                old_cost = float(old.get("avg_cost") or 0.0)
                avg_imp = old.get("avg_improvement") or {}
                old_success = int(round(old_rate * n))
                total = n + 1
                new_success = old_success + (1 if success else 0)
                rate = 0.0 if total <= 0 else (new_success / total)
                avg_cost = 0.0 if total <= 0 else ((old_cost * n) + float(cost or 0.0)) / total
            saver = getattr(engine, "capability_stat_save", None)
            if callable(saver):
                saver(capability_id, total, rate, json.dumps(avg_imp, ensure_ascii=False), avg_cost)
    except (ValueError, TypeError) as e:
        logger.warning(
            f"记录 capability_stat 失败（非致命）cap={capability_id!r} ok={success} cost={cost}: {e}",
            module_name=LOG_MODULE,
        )


def _next_task_sequence(engine, session_id: str) -> int:
    try:
        rows = engine.task_list(session_id, None, "sequence", True, False)
        if isinstance(rows, list) and rows:
            for r in rows:
                if isinstance(r, dict) and isinstance(r.get("sequence"), int):
                    return int(r["sequence"]) + 1
    except (ValueError, TypeError):
        pass
    return 0


def _find_task_id_by_type(engine, session_id: str, task_type: str, sort_order: int = 0, parent_id: Optional[int] = None) -> Optional[int]:
    """Find a task ID by session_id, task_type, sort_order, and optional parent_id. Returns the id or None."""
    try:
        rows = engine.task_list(session_id, task_type, "created_at", False, False)
        if isinstance(rows, list):
            for r in rows:
                if not isinstance(r, dict):
                    continue
                if r.get("sort_order") != sort_order:
                    continue
                if parent_id is not None:
                    if r.get("parent_id") != parent_id:
                        continue
                tid = r.get("id")
                if isinstance(tid, int):
                    return tid
    except (ValueError, TypeError):
        pass
    return None


def _precreate_task_with_indices(
        engine,
        session_id: str,
        task_type: str,
        title: str,
        parent_id: Optional[int] = None,
        sort_order: int = 0,
        volume_index: Optional[int] = None,
        chapter_index: Optional[int] = None,
) -> Optional[int]:
    """公共预创建任务函数：构造 payload → 校验 → 语义 upsert → 返回 task_id。"""
    if not session_id:
        return None
    try:
        seq = _next_task_sequence(engine, session_id)
        task_payload = {
            "session_id": session_id,
            "task_type": task_type,
            "sequence": seq,
            "parent_id": parent_id,
            "sort_order": sort_order,
            "volume_index": volume_index,
            "chapter_index": chapter_index,
            "status": "pending",
            "title": title,
            "content_text": "",
            "word_count": 0,
        }
        task_payload = _prepare_create_payload(task_payload)
        task_id = engine.task_upsert_semantic(json.dumps(task_payload, ensure_ascii=False))
        if isinstance(task_id, int) and task_id > 0:
            return int(task_id)
        return None
    except (ValueError, TypeError) as e:
        logger.warning(
            f"语义 upsert precreate task({task_type}) 失败 session={session_id!r} vol={volume_index!r} chap={chapter_index!r}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        return None


def _precreate_extract_memory_task(
        engine,
        session_id: str,
) -> Optional[int]:
    return _precreate_task_with_indices(
        engine, session_id, va.VAL_TASK_TYPE_EXTRACTION,
        title="提取会话记忆（执行中）",
        parent_id=None, sort_order=0,
        volume_index=None, chapter_index=None,
    )


def _finalize_extract_memory_task_safely(
        engine,
        session_id: str,
        capability_id: str,
        task_id: Optional[int],
        success: bool,
        dedup_memories: Optional[List[str]],
        token_cost: float,
) -> None:
    if not session_id or not task_id or capability_id != "extract_session_memory":
        return
    task_id_str = str(int(task_id))

    def _force_status_failed(reason: str) -> None:
        try:
            # 失败时只更新 status 和 title，不覆盖 content_text：
            # 错误详情已记录在 llm_invoke_log 中，任务内容应保留已有值。
            engine.task_update(task_id_str, json.dumps(_prepare_update_patch({
                "status": "failed",
            }), ensure_ascii=False))
        except (ValueError, TypeError) as _e2:
            logger.warning(
                f"[最终兜底] 把 task(extract_session_memory) 写回 failed 仍失败 task_id={task_id!r}: {_e2}",
                module_name=LOG_MODULE,
            )

    try:
        if not success:
            try:
                engine.task_delete(task_id_str)
                return
            except (ValueError, TypeError):
                _force_status_failed("能力执行失败，无法删除预创建任务，已标记失败")
                return
        mems = list(dedup_memories or [])
        mems_clean: List[str] = [m for m in mems if isinstance(m, str)]
        count = len(mems_clean)
        content_obj: Dict[str, Any] = {
            "_v": 2,
            "memories": mems_clean,
            "_meta": {
                "count": count,
                "format": "structured",
            },
        }
        content_text = json.dumps(content_obj, ensure_ascii=False)
        word_count = 0
        for m in mems_clean:
            word_count += len(m)
        if not mems_clean:
            try:
                engine.task_delete(task_id_str)
                return
            except (ValueError, TypeError):
                _force_status_failed("提取会话记忆结果为空，无法删除预创建任务，已标记失败")
                return
        patch_payload = {
            "status": "completed",
            "title": f"提取会话记忆 (memories={count})",
            "content_text": content_text,
            "word_count": int(word_count),
        }
        engine.task_update(task_id_str, json.dumps(_prepare_update_patch(patch_payload), ensure_ascii=False))
    except (ValueError, TypeError) as e:
        err_msg = f"extract_session_memory 回填异常: {e}"
        logger.warning(
            f"回填 task(extract_session_memory) 失败（非致命）task_id={task_id!r} session={session_id!r}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        _force_status_failed(err_msg)


def _precreate_global_plot_task(
        engine,
        session_id: str,
) -> Optional[int]:
    return _precreate_task_with_indices(
        engine, session_id, va.VAL_TASK_TYPE_GLOBAL_OUTLINE,
        title="全局剧情设计（执行中）",
        parent_id=None, sort_order=0,
        volume_index=None, chapter_index=None,
    )


def _finalize_global_plot_task_safely(
        engine,
        session_id: str,
        capability_id: str,
        task_id: Optional[int],
        success: bool,
        plot_text: Optional[str],
        summary_text: Optional[str],
        token_cost: float,
) -> None:
    if not session_id or not task_id or capability_id != "global_plot_design":
        return
    task_id_str = str(int(task_id))

    def _force_status_failed(reason: str) -> None:
        try:
            engine.task_update(task_id_str, json.dumps(_prepare_update_patch({
                "status": "failed",
                "title": "全局剧情设计（失败）",
            }), ensure_ascii=False))
        except Exception as _e2:
            logger.warning(
                f"[最终兜底] 把 task(global_plot_design) 写回 failed 仍失败 task_id={task_id!r}: {_e2}",
                module_name=LOG_MODULE,
            )

    try:
        if not success:
            _force_status_failed(
                "能力执行失败，详情见 llm_invoke_log 同 task_id 记录的 error 字段 / traceback 日志"
            )
            return
        plot = "" if not isinstance(plot_text, str) else plot_text.strip()
        summary = "" if not isinstance(summary_text, str) else summary_text.strip()
        if not plot and not summary:
            _force_status_failed(
                "LLM 返回结构缺少 plot / summary 字段，导致解析结果为空；原始响应见 llm_invoke_log 同 task_id 的 response 字段"
            )
            return
        content_obj: Dict[str, Any] = {"_v": 2, "plot": plot, "summary": summary}
        content_text = json.dumps(content_obj, ensure_ascii=False)
        word_count = (len(plot) if plot else 0) + (len(summary) if summary else 0)
        patch_payload = {
            "status": "completed",
            "title": "全局剧情设计",
            "content_text": content_text,
            "word_count": int(word_count),
        }
        engine.task_update(task_id_str, json.dumps(_prepare_update_patch(patch_payload), ensure_ascii=False))
    except (ValueError, TypeError) as e:
        err_msg = f"global_plot_design 回填异常: {e}"
        logger.warning(
            f"回填 task(global_plot_design) 失败（非致命）task_id={task_id!r} session={session_id!r}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        _force_status_failed(err_msg)


def _precreate_volume_plot_task(
        engine,
        session_id: str,
        volume_index: int = 0,
) -> Optional[int]:
    vi = int(volume_index) if isinstance(volume_index, (int, float)) else 0
    if vi < 0:
        vi = 0
    parent_id = _find_task_id_by_type(engine, session_id, va.VAL_TASK_TYPE_GLOBAL_OUTLINE, 0)
    return _precreate_task_with_indices(
        engine, session_id, va.VAL_TASK_TYPE_VOLUME_OUTLINE,
        title=f"卷纲剧情设计（第 {vi + 1} 卷，执行中）",
        parent_id=parent_id, sort_order=vi,
        volume_index=vi, chapter_index=None,
    )


def _finalize_volume_plot_task_safely(
        engine,
        session_id: str,
        capability_id: str,
        task_id: Optional[int],
        success: bool,
        plot_text: Optional[str],
        summary_text: Optional[str],
        global_plot_ref: Optional[str],
        token_cost: float,
) -> None:
    if not session_id or not task_id or capability_id != "volume_plot_design":
        return
    task_id_str = str(int(task_id))

    def _force_status_failed(reason: str) -> None:
        try:
            engine.task_update(task_id_str, json.dumps(_prepare_update_patch({
                "status": "failed",
                "title": "卷纲剧情设计（失败）",
            }), ensure_ascii=False))
        except Exception as _e2:
            logger.warning(
                f"[最终兜底] 把 task(volume_plot_design) 写回 failed 仍失败 task_id={task_id!r}: {_e2}",
                module_name=LOG_MODULE,
            )

    try:
        if not success:
            _force_status_failed(
                "能力执行失败，详情见 llm_invoke_log 同 task_id 记录的 error 字段 / traceback 日志"
            )
            return
        plot = "" if not isinstance(plot_text, str) else plot_text.strip()
        summary = "" if not isinstance(summary_text, str) else summary_text.strip()
        if not plot and not summary:
            _force_status_failed(
                "LLM 返回结构缺少 plot / summary 字段，导致解析结果为空；原始响应见 llm_invoke_log 同 task_id 的 response 字段"
            )
            return
        content_obj: Dict[str, Any] = {"_v": 2, "plot": plot, "summary": summary}
        if isinstance(global_plot_ref, str) and global_plot_ref.strip():
            content_obj["_meta"] = {"global_plot_ref": global_plot_ref.strip()[:400]}
        content_text = json.dumps(content_obj, ensure_ascii=False)
        word_count = (len(plot) if plot else 0) + (len(summary) if summary else 0)
        patch_payload = {
            "status": "completed",
            "title": "卷纲剧情设计",
            "content_text": content_text,
            "word_count": int(word_count),
        }
        engine.task_update(task_id_str, json.dumps(_prepare_update_patch(patch_payload), ensure_ascii=False))
    except (ValueError, TypeError) as e:
        err_msg = f"volume_plot_design 回填异常: {e}"
        logger.warning(
            f"回填 task(volume_plot_design) 失败（非致命）task_id={task_id!r} session={session_id!r}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        _force_status_failed(err_msg)


def _precreate_chapter_plot_task(
        engine,
        session_id: str,
        volume_index: int,
) -> Optional[int]:
    vi = int(volume_index) if isinstance(volume_index, (int, float)) else 0
    if vi < 0:
        vi = 0
    parent_id = _find_task_id_by_type(engine, session_id, va.VAL_TASK_TYPE_VOLUME_OUTLINE, vi)
    return _precreate_task_with_indices(
        engine, session_id, va.VAL_TASK_TYPE_CHAPTER_OUTLINE,
        title=f"章纲剧情设计（第 {vi + 1} 卷，执行中）",
        parent_id=parent_id, sort_order=0,
        volume_index=vi, chapter_index=0,
    )


def _finalize_chapter_plot_task_safely(
        engine,
        session_id: str,
        capability_id: str,
        task_id: Optional[int],
        success: bool,
        plot_text: Optional[str],
        summary_text: Optional[str],
        volume_plot_ref: Optional[str],
        volume_index: Optional[int],
        token_cost: float,
) -> None:
    if not session_id or not task_id or capability_id != "chapter_plot_design":
        return
    task_id_str = str(int(task_id))
    vi = int(volume_index) if isinstance(volume_index, (int, float)) else 0
    if vi < 0:
        vi = 0

    def _force_status_failed(reason: str) -> None:
        try:
            engine.task_update(task_id_str, json.dumps(_prepare_update_patch({
                "status": "failed",
                "title": f"章纲剧情设计（第 {vi + 1} 卷，失败）",
            }), ensure_ascii=False))
        except Exception as _e2:
            logger.warning(
                f"[最终兜底] 把 task(chapter_plot_design) 写回 failed 仍失败 task_id={task_id!r}: {_e2}",
                module_name=LOG_MODULE,
            )

    try:
        if not success:
            _force_status_failed(
                "能力执行失败，详情见 llm_invoke_log 同 task_id 记录的 error 字段 / traceback 日志"
            )
            return
        plot = "" if not isinstance(plot_text, str) else plot_text.strip()
        summary = "" if not isinstance(summary_text, str) else summary_text.strip()
        if not plot and not summary:
            _force_status_failed(
                "LLM 返回结构缺少 plot / summary 字段，导致解析结果为空；原始响应见 llm_invoke_log 同 task_id 的 response 字段"
            )
            return
        content_obj: Dict[str, Any] = {"_v": 2, "chapters": [{"plot": plot, "summary": summary}]}
        if isinstance(volume_plot_ref, str) and volume_plot_ref.strip():
            content_obj["_meta"] = {"volume_plot_ref": volume_plot_ref.strip()[:400]}
        content_text = json.dumps(content_obj, ensure_ascii=False)
        word_count = (len(plot) if plot else 0) + (len(summary) if summary else 0)
        patch_payload = {
            "status": "completed",
            "title": f"章纲剧情设计（第 {vi + 1} 卷）",
            "content_text": content_text,
            "word_count": int(word_count),
        }
        engine.task_update(task_id_str, json.dumps(_prepare_update_patch(patch_payload), ensure_ascii=False))
    except (ValueError, TypeError) as e:
        err_msg = f"chapter_plot_design 回填异常: {e}"
        logger.warning(
            f"回填 task(chapter_plot_design) 失败（非致命）task_id={task_id!r} session={session_id!r}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        _force_status_failed(err_msg)


def _precreate_chapter_events_task(
        engine,
        session_id: str,
        volume_index: int,
        chapter_index: int,
) -> Optional[int]:
    vi = int(volume_index) if isinstance(volume_index, (int, float)) else 0
    ci = int(chapter_index) if isinstance(chapter_index, (int, float)) else 0
    if vi < 0:
        vi = 0
    if ci < 0:
        ci = 0
    volume_outline_id = _find_task_id_by_type(engine, session_id, va.VAL_TASK_TYPE_VOLUME_OUTLINE, vi)
    chapter_outline_id = _find_task_id_by_type(engine, session_id, va.VAL_TASK_TYPE_CHAPTER_OUTLINE, ci, volume_outline_id)
    return _precreate_task_with_indices(
        engine, session_id, va.VAL_TASK_TYPE_CHAPTER_EVENTS,
        title=f"章节事件设计（第 {vi + 1} 卷第 {ci + 1} 章，执行中）",
        parent_id=chapter_outline_id, sort_order=ci,
        volume_index=vi, chapter_index=ci,
    )


def _finalize_chapter_events_task_safely(
        engine,
        session_id: str,
        capability_id: str,
        task_id: Optional[int],
        success: bool,
        events: Optional[List[Any]],
        chapter_plot_ref: Optional[str],
        chapter_summary_ref: Optional[str],
        volume_index: Optional[int],
        chapter_index: Optional[int],
        token_cost: float,
) -> None:
    if not session_id or not task_id or capability_id != "chapter_events_design":
        return
    task_id_str = str(int(task_id))
    vi = int(volume_index) if isinstance(volume_index, (int, float)) else 0
    ci = int(chapter_index) if isinstance(chapter_index, (int, float)) else 0
    if vi < 0:
        vi = 0
    if ci < 0:
        ci = 0

    def _force_status_failed(reason: str) -> None:
        try:
            engine.task_update(task_id_str, json.dumps(_prepare_update_patch({
                "status": "failed",
                "title": f"章节事件设计（第 {vi + 1} 卷第 {ci + 1} 章，失败）",
            }), ensure_ascii=False))
        except Exception as _e2:
            logger.warning(
                f"[最终兜底] 把 task(chapter_events_design) 写回 failed 仍失败 task_id={task_id!r}: {_e2}",
                module_name=LOG_MODULE,
            )

    try:
        if not success:
            _force_status_failed(
                "能力执行失败，详情见 llm_invoke_log 同 task_id 记录的 error 字段 / traceback 日志"
            )
            return
        arr = list(events) if isinstance(events, (list, tuple)) else []
        clean_events: List[str] = []
        for e in arr:
            if e is None:
                continue
            if isinstance(e, str):
                s = e.strip()
                if s:
                    clean_events.append(s)
                continue
            if isinstance(e, dict):
                for _k in ("event", "summary", "text", "desc", "description", "content"):
                    _v = e.get(_k)
                    if isinstance(_v, str) and _v.strip():
                        clean_events.append(_v.strip())
                        break
        if not clean_events:
            _force_status_failed(
                "LLM 返回结构缺少 chapter_events_design.events 字符串数组，导致解析结果为空；原始响应见 llm_invoke_log 同 task_id 的 response 字段"
            )
            return
        wc = 0
        meta: Dict[str, str] = {}
        if isinstance(chapter_plot_ref, str) and chapter_plot_ref.strip():
            cp_s = chapter_plot_ref.strip()[:400]
            meta["chapter_plot_ref"] = cp_s
            wc += len(cp_s)
        if isinstance(chapter_summary_ref, str) and chapter_summary_ref.strip():
            cs_s = chapter_summary_ref.strip()[:400]
            meta["chapter_summary_ref"] = cs_s
            wc += len(cs_s)
        for item in clean_events:
            wc += len(item)
        content_obj: Dict[str, Any] = {"_v": 1, "events": clean_events}
        if meta:
            content_obj["_meta"] = meta
        content_text = json.dumps(content_obj, ensure_ascii=False)
        patch_payload = {
            "status": "completed",
            "title": f"章节事件设计（第 {vi + 1} 卷第 {ci + 1} 章，{len(clean_events)} 条事件）",
            "content_text": content_text,
            "word_count": int(wc),
        }
        engine.task_update(task_id_str, json.dumps(_prepare_update_patch(patch_payload), ensure_ascii=False))
    except (ValueError, TypeError) as e:
        err_msg = f"chapter_events_design 回填异常: {e}"
        logger.warning(
            f"回填 task(chapter_events_design) 失败（非致命）task_id={task_id!r} session={session_id!r}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        _force_status_failed(err_msg)


def _precreate_chapter_content_task(
        engine,
        session_id: str,
        volume_index: int,
        chapter_index: int,
) -> Optional[int]:
    vi = int(volume_index) if isinstance(volume_index, (int, float)) else 0
    ci = int(chapter_index) if isinstance(chapter_index, (int, float)) else 0
    if vi < 0:
        vi = 0
    if ci < 0:
        ci = 0
    volume_outline_id = _find_task_id_by_type(engine, session_id, va.VAL_TASK_TYPE_VOLUME_OUTLINE, vi)
    chapter_outline_id = _find_task_id_by_type(engine, session_id, va.VAL_TASK_TYPE_CHAPTER_OUTLINE, ci, volume_outline_id)
    return _precreate_task_with_indices(
        engine, session_id, va.VAL_TASK_TYPE_CHAPTER_CONTENT,
        title=f"章节正文生成（第 {vi + 1} 卷第 {ci + 1} 章，执行中）",
        parent_id=chapter_outline_id, sort_order=ci,
        volume_index=vi, chapter_index=ci,
    )


def _finalize_chapter_content_task_safely(
        engine,
        session_id: str,
        capability_id: str,
        task_id: Optional[int],
        success: bool,
        content_text: Optional[str],
        volume_index: Optional[int],
        chapter_index: Optional[int],
        token_cost: float,
) -> None:
    if not session_id or not task_id or capability_id != "chapter_content_generation":
        return
    task_id_str = str(int(task_id))
    vi = int(volume_index) if isinstance(volume_index, (int, float)) else 0
    ci = int(chapter_index) if isinstance(chapter_index, (int, float)) else 0
    if vi < 0:
        vi = 0
    if ci < 0:
        ci = 0

    def _force_status_failed(reason: str) -> None:
        try:
            engine.task_update(task_id_str, json.dumps(_prepare_update_patch({
                "status": "failed",
                "title": f"章节正文生成（第 {vi + 1} 卷第 {ci + 1} 章，失败）",
            }), ensure_ascii=False))
        except Exception as _e2:
            logger.warning(
                f"[最终兜底] 把 task(chapter_content_generation) 写回 failed 仍失败 task_id={task_id!r}: {_e2}",
                module_name=LOG_MODULE,
            )

    try:
        if not success:
            _force_status_failed(
                "能力执行失败，详情见 llm_invoke_log 同 task_id 记录的 error 字段 / traceback 日志"
            )
            return
        if not content_text or not content_text.strip():
            _force_status_failed(
                "LLM 返回正文为空，导致解析结果为空；原始响应见 llm_invoke_log 同 task_id 的 response 字段"
            )
            return
        content_text_clean = content_text.strip()
        word_count = len(content_text_clean)
        content_obj: Dict[str, Any] = {"_v": 1, "content_text": content_text_clean}
        content_json = json.dumps(content_obj, ensure_ascii=False)
        patch_payload = {
            "status": "completed",
            "title": f"章节正文生成（第 {vi + 1} 卷第 {ci + 1} 章，{word_count} 字）",
            "content_text": content_json,
            "word_count": int(word_count),
        }
        engine.task_update(task_id_str, json.dumps(_prepare_update_patch(patch_payload), ensure_ascii=False))
    except (ValueError, TypeError) as e:
        err_msg = f"chapter_content_generation 回填异常: {e}"
        logger.warning(
            f"回填 task(chapter_content_generation) 失败（非致命）task_id={task_id!r} session={session_id!r}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        _force_status_failed(err_msg)


_CHARACTER_FIELD_PRIORITY = va.VAL_PROMPT_CHAR_FIELD_PRIORITY
_TIMELINE_FIELD_PRIORITY = va.VAL_PROMPT_TIME_FIELD_PRIORITY
_LOCATION_FIELD_PRIORITY = va.VAL_PROMPT_LOC_FIELD_PRIORITY


def _number_items(items: List[str]) -> str:
    """给条目列表加序号，返回 '1. xxx\\n2. xxx' 格式。空条目自动跳过。"""
    clean = [s.strip() for s in items if isinstance(s, str) and s.strip()]
    if not clean:
        return ""
    return "\n".join(f"{i + 1}. {s}" for i, s in enumerate(clean))


class _InjectionParts:
    """注入各部分独立存储，最终统一拼装，避免拆分旧字符串。"""

    def __init__(self):
        self.core_plot: str = ""       # 故事核心走向
        self.char_texts: List[str] = []  # 主要角色
        self.time_texts: List[str] = []  # 主要时间
        self.loc_texts: List[str] = []   # 主要地点
        self.label_lines: List[str] = [] # 整体标签
        self.mem_texts: List[str] = []   # 会话记忆

    def build_user_input(self, max_chars: int) -> str:
        """按顺序拼装成最终 user_input。条目型数据（角色/时间/地点）加序号，标签型不加。"""
        chunks: List[str] = []
        if self.core_plot:
            chunks.append("【故事核心走向】\n" + self.core_plot)
        if self.char_texts:
            chunks.append("【主要角色】\n" + _number_items(self.char_texts))
        if self.time_texts:
            chunks.append("【主要时间】\n" + _number_items(self.time_texts))
        if self.loc_texts:
            chunks.append("【主要地点】\n" + _number_items(self.loc_texts))
        if self.label_lines:
            chunks.append("【整体标签】\n" + "\n".join(self.label_lines))
        if not chunks:
            return ""
        return _limit_text("\n\n".join(chunks), max_chars)

    def build_session_memory(self) -> str:
        """拼装会话记忆，每条加序号。"""
        return _number_items(self.mem_texts)


def _get_injection_cfg(
    counts: Optional[Dict[str, int]] = None,
) -> Dict[str, int]:
    """获取注入配置。
    counts: 可选，真实选择数量映射，如 {"char": 3, "time": 1, "loc": 2, "mem": 10}。
            若提供，则 user_input_chars = 真实数量 × 单条上限 + 余量。
            若不提供，则 user_input_chars = 默认数量 × 单条上限 + 余量。
    """
    if counts:
        _uic = (
            counts.get("char", va.VAL_INJECT_CHARACTER_COUNT) * va.VAL_INJECT_CHARACTER_CHARS
            + counts.get("time", va.VAL_INJECT_TIMELINE_COUNT) * va.VAL_INJECT_TIMELINE_CHARS
            + counts.get("loc", va.VAL_INJECT_LOCATION_COUNT) * va.VAL_INJECT_LOCATION_CHARS
            + counts.get("mem", va.VAL_INJECT_SESSION_MEMORY_COUNT) * va.VAL_INJECT_SESSION_MEMORY_CHARS
            + 2000  # 核心走向 + 标签等余量
        )
    else:
        _uic = (
            va.VAL_INJECT_CHARACTER_COUNT * va.VAL_INJECT_CHARACTER_CHARS
            + va.VAL_INJECT_TIMELINE_COUNT * va.VAL_INJECT_TIMELINE_CHARS
            + va.VAL_INJECT_LOCATION_COUNT * va.VAL_INJECT_LOCATION_CHARS
            + va.VAL_INJECT_SESSION_MEMORY_COUNT * va.VAL_INJECT_SESSION_MEMORY_CHARS
            + 2000  # 核心走向 + 标签等余量
        )
    return {
        "character_count": va.VAL_INJECT_CHARACTER_COUNT,
        "character_chars": va.VAL_INJECT_CHARACTER_CHARS,
        "timeline_count": va.VAL_INJECT_TIMELINE_COUNT,
        "timeline_chars": va.VAL_INJECT_TIMELINE_CHARS,
        "location_count": va.VAL_INJECT_LOCATION_COUNT,
        "location_chars": va.VAL_INJECT_LOCATION_CHARS,
        "session_count": va.VAL_INJECT_SESSION_MEMORY_COUNT,
        "session_chars": va.VAL_INJECT_SESSION_MEMORY_CHARS,
        "nlp_chars": va.VAL_INJECT_NLP_SUMMARY_CHARS,
        "user_input_chars": _uic,
        "match_k": va.VAL_INJECT_MATCH_KEYWORDS_TOP_K,
    }


def _extract_semantic_entry_text(row: Any, category: str) -> str:
    if row is None:
        return ""
    r = row if isinstance(row, dict) else {}
    attrs = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
    if category == "entity":
        order = _CHARACTER_FIELD_PRIORITY
    elif category == "temporal":
        order = _TIMELINE_FIELD_PRIORITY
    else:
        order = _LOCATION_FIELD_PRIORITY
    parts: List[str] = []
    for f in order:
        if f == "attributes":
            if isinstance(attrs, dict) and attrs:
                for k, v in attrs.items():
                    if v is None:
                        continue
                    parts.append(f"{k}:{v}")
            continue
        if f == "aliases":
            val = r.get("aliases")
            if isinstance(val, (list, tuple)) and val:
                parts.append(",".join("" if x is None else str(x) for x in val))
            continue
        if f == "relationships":
            val = r.get("relationships")
            if isinstance(val, (list, tuple)) and val:
                for rel in val:
                    if not isinstance(rel, dict):
                        continue
                    try:
                        parts.append(str(rel.get("type", "")))
                        parts.append(str(rel.get("targetId", "")))
                    except (ValueError, TypeError):
                        pass
            continue
        val = r.get(f)
        if val is None:
            continue
        parts.append(str(val))
    return " ".join(x for x in parts if isinstance(x, str) and x.strip()).strip()


def _entry_time_sort_key(row: Any) -> Tuple[int, int]:
    r = row if isinstance(row, dict) else {}
    si = r.get("sort_index")
    try:
        si_n = int(si) if si is not None and str(si).strip() != "" else -1
    except (ValueError, TypeError):
        si_n = -1
    try:
        ca = r.get("created_at") or r.get("updated_at") or 0
        t_n = ca if isinstance(ca, (int, float)) else 0
        if isinstance(ca, str) and ca:
            try:
                import datetime as _dt
                t_n = int(_dt.datetime.fromisoformat(str(ca).replace("Z", "+00:00")).timestamp())
            except (ValueError, TypeError):
                t_n = 0
    except (ValueError, TypeError):
        t_n = 0
    return (si_n, int(t_n))


def _extract_core_keywords(
        core_plot_text: str, text_tools: Any
) -> Tuple[List[str], List[str], List[str]]:
    cfg = _get_injection_cfg()
    noop: Tuple[List[str], List[str], List[str]] = ([], [], [])
    if not isinstance(core_plot_text, str) or not core_plot_text.strip():
        return noop
    text = core_plot_text.strip()
    seen: List[str] = []
    added: set = set()
    keywords_raw: List[str] = []
    words_raw: List[str] = []
    try:
        if text_tools is not None and hasattr(text_tools, "extract_keywords"):
            for w in list(text_tools.extract_keywords(text, top_k=cfg["match_k"], context="剧情核心关键词") or []):
                w = "" if w is None else str(w).strip()
                if w:
                    keywords_raw.append(w)
                if len(w) >= 1 and w and w not in added:
                    added.add(w)
                    seen.append(w)
    except (ValueError, TypeError):
        pass
    try:
        from app.core.services.local_tools import LocalTextTools as _LTT
        _tt = text_tools if text_tools is not None else _LTT.get_instance()
        words = _tt.cut_words(text, filter_stopwords=True, context="剧情核心分词") or []
        words_raw = list(words)
        for w in words:
            w = "" if w is None else str(w).strip()
            if len(w) >= 2 and w and w not in added:
                added.add(w)
                seen.append(w)
    except (ValueError, TypeError):
        pass
    return seen, words_raw, keywords_raw


def _score_and_select(
        entries_raw: List[Any],
        category: str,
        max_count: int,
        max_chars: int,
        keywords: List[str],
) -> Tuple[List[Any], List[str], List[Dict[str, Any]]]:
    if not isinstance(entries_raw, list):
        return [], [], []
    keyword_set = set()
    if isinstance(keywords, list) and keywords:
        keyword_set = {str(x) for x in keywords if x and str(x).strip()}
    rows_with_meta = []
    for idx, entry in enumerate(entries_raw or []):
        if entry is None:
            continue
        full_text = _extract_semantic_entry_text(entry, category)
        score = 0
        if keyword_set:
            for kw in keyword_set:
                if len(kw) >= 2 and kw in full_text:
                    score += 1
        richness_base = min(0.5, (len(full_text) / 100.0) * 0.1) if full_text else 0.0
        richness_bonus = min(richness_base, 0.5 * max(score, 1))
        total_score = score + richness_bonus
        rows_with_meta.append((score, richness_bonus, total_score, _entry_time_sort_key(entry), idx, full_text, entry))
    rows_with_meta.sort(key=lambda x: (-x[2], (-x[3][0], -x[3][1]), x[4]))
    selected_rows: List[Any] = []
    selected_texts: List[str] = []
    for _, _, _, _, _, full_text, entry in rows_with_meta:
        if len(selected_rows) >= max_count:
            break
        if not full_text:
            continue
        selected_rows.append(entry)
        selected_texts.append(full_text)
    all_with_meta: List[Dict[str, Any]] = []
    for score, richness_bonus, _total, _time, _idx, _ft, entry in rows_with_meta:
        all_with_meta.append({
            "entry": entry,
            "score": float(score),
            "richness_bonus": float(richness_bonus),
            "keyword_hits": int(score),
        })
    return selected_rows, selected_texts, all_with_meta


def _validate_selected_ids_list(raw: Any, field_name: str, session_id: str, capability_id: str, summary: str) -> \
        Optional[List[int]]:
    if raw is None:
        return None
    if not isinstance(raw, list):
        logger.error(
            f"[注入参数非法] session_id={session_id!r} capability_id={capability_id!r} "
            f"field={field_name!r} value={raw!r}：必须为整数数组 {summary}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=f"{field_name} 必须为整数数组")
    out: List[int] = []
    for idx, item in enumerate(raw):
        if isinstance(item, bool):
            logger.error(
                f"[注入参数非法] session_id={session_id!r} capability_id={capability_id!r} "
                f"field={field_name!r} idx={idx} value={item!r}：必须为整数数组 {summary}",
                module_name=LOG_MODULE,
                exc_info=True,
            )
            raise HTTPException(status_code=400, detail=f"{field_name} 必须为整数数组")
        if isinstance(item, int):
            if item <= 0:
                logger.error(
                    f"[注入参数非法] session_id={session_id!r} capability_id={capability_id!r} "
                    f"field={field_name!r} idx={idx} value={item!r}：id 必须为正整数 {summary}",
                    module_name=LOG_MODULE,
                    exc_info=True,
                )
                raise HTTPException(status_code=400, detail=f"{field_name} 元素必须为正整数")
            out.append(int(item))
            continue
        if isinstance(item, float):
            i = int(item)
            if i > 0 and float(i) == item:
                out.append(int(i))
                continue
        if isinstance(item, str):
            s = str(item).strip()
            if s and s.lstrip("-").isdigit():
                try:
                    i = int(s)
                    if i > 0:
                        out.append(int(i))
                        continue
                except (ValueError, TypeError):
                    pass
        logger.error(
            f"[注入参数非法] session_id={session_id!r} capability_id={capability_id!r} "
            f"field={field_name!r} idx={idx} value={item!r}：必须为整数数组 {summary}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=f"{field_name} 必须为整数数组")
    return out


def _pick_entries_by_ids(all_entries: List[Any], ids_list: List[int], category_label: str,
                         session_id: str, capability_id: str, summary: str) -> List[Any]:
    id_to_entry: Dict[int, Any] = {}
    for e in all_entries or []:
        eid = _get_entry_id(e)
        if eid is not None:
            id_to_entry[eid] = e
    result: List[Any] = []
    missing: List[int] = []
    for want_id in ids_list:
        if want_id in id_to_entry:
            result.append(id_to_entry[want_id])
        else:
            missing.append(int(want_id))
    if missing:
        logger.warning(
            f"[注入ID缺失] session_id={session_id!r} capability_id={capability_id!r} "
            f"category={category_label!r} missing_ids={missing}：全量里找不到对应条目，已自动忽略 {summary}",
            module_name=LOG_MODULE,
        )
    return result


def _apply_selected_ids_to_injection(
        session_id: str,
        capability_id: str,
        variables: Dict[str, Any],
        effective_vars: Dict[str, Any],
        parts: _InjectionParts,
        engine: Any,
        summary: str,
) -> None:
    """应用用户选择的 ID 到注入 parts 中。
    直接填充角色/时间/地点/会话记忆，最后统一拼装。
    """
    if not isinstance(variables, dict) or not isinstance(effective_vars, dict) or not isinstance(parts, _InjectionParts):
        return

    raw_char = variables.get("selected_character_ids")
    raw_time = variables.get("selected_temporal_ids")
    raw_loc = variables.get("selected_location_ids")
    raw_mem = variables.get("selected_session_memory_ids")
    if raw_char is None and raw_time is None and raw_loc is None and raw_mem is None:
        return

    ids_char = _validate_selected_ids_list(raw_char, "selected_character_ids", session_id, capability_id, summary)
    ids_time = _validate_selected_ids_list(raw_time, "selected_temporal_ids", session_id, capability_id, summary)
    ids_loc = _validate_selected_ids_list(raw_loc, "selected_location_ids", session_id, capability_id, summary)
    ids_mem = _validate_selected_ids_list(raw_mem, "selected_session_memory_ids", session_id, capability_id, summary)

    logger.info(
        f"[注入生效] session_id={session_id!r} capability_id={capability_id!r} "
        f"selected_char_ids={ids_char if ids_char is not None else []} "
        f"n_char={len(ids_char) if ids_char is not None else 0} "
        f"selected_time_ids={ids_time if ids_time is not None else []} "
        f"n_time={len(ids_time) if ids_time is not None else 0} "
        f"selected_loc_ids={ids_loc if ids_loc is not None else []} "
        f"n_loc={len(ids_loc) if ids_loc is not None else 0} "
        f"selected_mem_ids={ids_mem if ids_mem is not None else []} "
        f"n_mem={len(ids_mem) if ids_mem is not None else 0} {summary}",
        module_name=LOG_MODULE,
    )

    if ids_char is None and ids_time is None and ids_loc is None and ids_mem is None:
        return

    # 按真实选择数量计算 cfg
    counts = {
        "char": len(ids_char) if ids_char is not None else 0,
        "time": len(ids_time) if ids_time is not None else 0,
        "loc": len(ids_loc) if ids_loc is not None else 0,
        "mem": len(ids_mem) if ids_mem is not None else 0,
    }
    cfg = _get_injection_cfg(counts=counts)

    # ========== 获取全量条目 ==========
    characters_all: List[Any] = []
    timelines_all: List[Any] = []
    locations_all: List[Any] = []
    memories_all: List[Any] = []
    if ids_char is not None:
        try:
            characters_all = list(engine.semantic_vocabulary_list(session_id, "entity") or [])
        except (ValueError, TypeError):
            characters_all = []
    if ids_time is not None:
        try:
            timelines_all = list(engine.semantic_vocabulary_list(session_id, "temporal") or [])
        except (ValueError, TypeError):
            timelines_all = []
    if ids_loc is not None:
        try:
            locations_all = list(engine.semantic_vocabulary_list(session_id, "location") or [])
        except (ValueError, TypeError):
            locations_all = []
    if ids_mem is not None:
        try:
            memories_all = list(engine.session_memory_list(session_id) or [])
        except (ValueError, TypeError):
            memories_all = []

    # ========== 填充角色 ==========
    if ids_char is not None:
        char_rows_final = _pick_entries_by_ids(characters_all, ids_char, "角色", session_id, capability_id, summary)
        if char_rows_final:
            parts.char_texts = normalize_entries_for_prompt(
                char_rows_final, "entity",
                all_entries=characters_all,
                max_chars_per_entry=cfg["character_chars"],
            )

    # ========== 填充时间 ==========
    if ids_time is not None:
        time_rows_final = _pick_entries_by_ids(timelines_all, ids_time, "时间", session_id, capability_id, summary)
        if time_rows_final:
            parts.time_texts = normalize_entries_for_prompt(
                time_rows_final, "temporal",
                all_entries=timelines_all,
                max_chars_per_entry=cfg["timeline_chars"],
            )

    # ========== 填充地点 ==========
    if ids_loc is not None:
        loc_rows_final = _pick_entries_by_ids(locations_all, ids_loc, "地点", session_id, capability_id, summary)
        if loc_rows_final:
            parts.loc_texts = normalize_entries_for_prompt(
                loc_rows_final, "location",
                all_entries=locations_all,
                max_chars_per_entry=cfg["location_chars"],
            )

    # ========== 填充会话记忆 ==========
    if ids_mem is not None:
        mem_id_to_content: Dict[int, str] = {}
        for m in memories_all or []:
            mid = _get_entry_id(m)
            if mid is None:
                continue
            m_dict = m if isinstance(m, dict) else {}
            content = ""
            for f in ("content", "text", "body", "summary", "memory", "rule"):
                v = m_dict.get(f) if isinstance(m_dict, dict) else (
                    getattr(m, f, None) if not isinstance(m, dict) else None)
                if isinstance(v, str) and v.strip():
                    content = v.strip()
                    break
            if content:
                mem_id_to_content[mid] = _limit_text(content, cfg["session_chars"])
        missing_mem: List[int] = []
        parts.mem_texts = []
        for want_id in ids_mem:
            if want_id in mem_id_to_content:
                parts.mem_texts.append(mem_id_to_content[want_id])
            else:
                missing_mem.append(int(want_id))
        if missing_mem:
            logger.warning(
                f"[注入ID缺失] session_id={session_id!r} capability_id={capability_id!r} "
                f"category=会话记忆 missing_ids={missing_mem}：全量里找不到对应条目，已自动忽略 {summary}",
                module_name=LOG_MODULE,
            )

    # ========== 清理临时字段，统一拼装 ==========
    for tmp_k in (
            "selected_character_ids", "selected_temporal_ids",
            "selected_location_ids", "selected_session_memory_ids",
    ):
        effective_vars.pop(tmp_k, None)

    effective_vars["user_input"] = parts.build_user_input(cfg["user_input_chars"])
    effective_vars["session_memory"] = parts.build_session_memory()


def _auto_recommend_session_memories(
        session_id: str,
        core_plot_text: str,
        engine: Any,
) -> List[Dict[str, Any]]:
    """自动推荐会话记忆：基于关键词匹配打分，返回排序后的会话记忆列表。
    作为独立功能保留，供前端推荐或其他模块调用；不直接注入 parts.mem_texts。
    返回格式：[{"id": int, "content": str, "score": int}, ...]，按 score 降序。
    """
    from app.core.services.local_tools import LocalTextTools

    if not session_id:
        return []

    cfg = _get_injection_cfg()

    try:
        text_tools = LocalTextTools.get_instance()
    except (ValueError, TypeError):
        text_tools = None

    keywords, _, _ = _extract_core_keywords(core_plot_text, text_tools)

    try:
        memories_all = list(engine.session_memory_list(session_id) or [])
    except (ValueError, TypeError):
        memories_all = []

    kw_set = {str(k) for k in keywords if k and len(str(k)) >= 2}
    mem_meta = []
    for idx, m in enumerate(memories_all or []):
        m = m if isinstance(m, dict) else {}
        content = ""
        for field in ("content", "text", "body", "summary", "memory", "rule"):
            v = m.get(field) if isinstance(m, dict) else getattr(m, field, None)
            if isinstance(v, str) and v.strip():
                content = v.strip()
                break
        if not content:
            continue
        content = _limit_text(content, cfg["session_chars"])
        if not content:
            continue
        score = 0
        if kw_set:
            for kw in kw_set:
                if len(kw) >= 2 and kw in content:
                    score += 1
        mem_id = _get_entry_id(m)
        mem_meta.append({
            "idx": idx,
            "id": mem_id if mem_id is not None else idx,
            "content": content,
            "score": score,
            "sort_key": _entry_time_sort_key(m),
        })
    mem_meta.sort(key=lambda x: (-x["score"], (-x["sort_key"][0], -x["sort_key"][1]), x["idx"]))
    return mem_meta


def _build_global_plot_injection_variables(
        session_id: str,
        core_plot_text: str,
        engine: Any,
) -> _InjectionParts:
    """构建注入变量：仅处理用户显式提供的核心走向和标签。
    会话记忆、角色、时间、地点由 _apply_selected_ids_to_injection 根据用户选择填充。
    """
    parts = _InjectionParts()
    if not session_id:
        return parts
    if not isinstance(core_plot_text, str):
        core_plot_text = ""
    core_plot_text = core_plot_text.strip()
    parts.core_plot = core_plot_text

    # ========== 标签 ==========
    try:
        label_obj = engine.label_selection_get(session_id) or {}
    except (ValueError, TypeError):
        label_obj = {}

    label_config = {}
    try:
        label_config_raw = engine.label_config_get(session_id)
        if label_config_raw:
            label_config_raw_dict = dict(label_config_raw)
            config_json_str = label_config_raw_dict.get("config_json")
            if config_json_str:
                import json
                label_config = json.loads(config_json_str)
    except (ValueError, TypeError):
        pass
    label_id_name_map = va.build_label_id_name_map(label_config)

    if isinstance(label_obj, dict):
        sel = label_obj.get("selected_labels") or {}
        if isinstance(sel, dict):
            if sel.get("subject"):
                parts.label_lines.append(f"题材：{va.get_label_name(label_id_name_map, 'subject', sel.get('subject'))}")
            if isinstance(sel.get("style"), list) and sel.get("style"):
                parts.label_lines.append("风格：" + " / ".join(
                    va.get_label_name(label_id_name_map, 'style', str(x)) for x in sel.get("style") if x))
            if sel.get("length"):
                parts.label_lines.append(f"篇幅：{va.get_label_name(label_id_name_map, 'length', sel.get('length'))}")
            if isinstance(sel.get("taboo"), list) and sel.get("taboo"):
                parts.label_lines.append("禁忌：" + " / ".join(str(x) for x in sel.get("taboo") if x))

    return parts


def _limit_text(text: Any, max_chars: int) -> str:
    """句子感知截断：在max_len以内找到最后一个句尾标点作为截断点，复用全局配置正则规则"""
    if text is None:
        return ""
    s = str(text).strip()
    if not max_chars or max_chars <= 0:
        return s
    if len(s) <= max_chars:
        return s
    # 复用全局配置的句子结束正则规则
    sentence_end_pattern = re.compile(config.PARAGRAPH_SPLIT_SENTENCE_PATTERN)
    # 在 max_len 范围内寻找最后一个句尾标点
    window = s[:max_chars]
    last_sentence_end = -1
    for m in sentence_end_pattern.finditer(window):
        last_sentence_end = m.end()
    if last_sentence_end > 0:
        return s[:last_sentence_end] + "…"
    # 如果没有找到句尾标点，直接截断
    return s[: int(max_chars)] + "…"


def _split_and_limit_session_memory(session_value: Any) -> str:
    if session_value is None:
        return ""
    cfg = _get_injection_cfg()
    max_items = cfg["session_count"]
    max_chars_per = cfg["session_chars"]
    max_chars_total = cfg["session_count"] * cfg["session_chars"]
    items: List[str] = []
    if isinstance(session_value, list):
        for x in session_value:
            if x is None:
                continue
            if isinstance(x, dict):
                for field in ("content", "text", "body", "summary", "memory", "rule"):
                    v = x.get(field)
                    if isinstance(v, str) and v.strip():
                        items.append(v.strip())
                        break
                else:
                    flat = json.dumps(x, ensure_ascii=False)
                    if flat.strip():
                        items.append(flat.strip())
            else:
                s = str(x).strip()
                if s:
                    items.append(s)
    else:
        raw = str(session_value)
        blocks = re.split(r"\n\s*\n", raw) if "\n\n" in raw else raw.splitlines()
        for b in blocks:
            s = b.strip()
            if s:
                items.append(s)
    if len(items) > max_items:
        items = items[-max_items:]
    limited = [_limit_text(it, max_chars_per) for it in items]
    joined = "\n".join(limited)
    return _limit_text(joined, max_chars_total)


def _apply_injection_limits(capability_id: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(variables, dict):
        return {}
    cfg = _get_injection_cfg()
    out: Dict[str, Any] = dict(variables)

    # 用户输入预处理（标点修正 + 错别字修正）
    if "user_input" in out and isinstance(out["user_input"], str):
        try:
            # 修正标点
            punctuation_processor = PunctuationProcessor()
            fixed_text, _ = punctuation_processor.auto_fix_punctuation(out["user_input"])

            # 修正错别字
            spell_checker = SpellChecker()
            fixed_text, _ = spell_checker.auto_fix_wrong_characters(fixed_text)
            fixed_text, _ = spell_checker.auto_fix_de_errors(fixed_text)

            out["user_input"] = fixed_text
        except Exception as _e:
            logger.warning(
                f"用户输入预处理失败（标点/错别字修正），将使用原始输入 {capability_id}: {_e}",
                module_name=LOG_MODULE,
                exc_info=True,
            )

    if capability_id in {"global_plot_design", "volume_plot_design", "chapter_plot_design"}:
        if "session_memory" in out:
            out["session_memory"] = _split_and_limit_session_memory(out.get("session_memory"))
        if "user_input" in out:
            out["user_input"] = _limit_text(out.get("user_input"), cfg["user_input_chars"])
        if "global_plot_design" in out and capability_id == "volume_plot_design":
            out["global_plot_design"] = _limit_text(out.get("global_plot_design"), cfg["user_input_chars"])
        if "volume_plot_design" in out and capability_id == "chapter_plot_design":
            out["volume_plot_design"] = _limit_text(out.get("volume_plot_design"), cfg["user_input_chars"])
        if "previous_volume" in out and capability_id == "volume_plot_design":
            out["previous_volume"] = _limit_text(out.get("previous_volume"), cfg["user_input_chars"])
        if "previous_chapter" in out and capability_id == "chapter_plot_design":
            out["previous_chapter"] = _limit_text(out.get("previous_chapter"), cfg["user_input_chars"])
        for alias_key in ("session", "background", "core"):
            if alias_key in out and isinstance(out.get(alias_key), (list, tuple)):
                limited_list: List[str] = []
                total = 0
                for item in list(out.get(alias_key) or []):
                    text = _limit_text(item, cfg["character_chars"])
                    if not text:
                        continue
                    if len(limited_list) >= cfg["character_count"]:
                        break
                    limited_list.append(text)
                    total += len(text)
                    if total >= cfg["user_input_chars"]:
                        break
                out[alias_key] = limited_list
            elif alias_key in out:
                out[alias_key] = _limit_text(out.get(alias_key), cfg["nlp_chars"])
    return out


def _fetch_latest_global_outline_text(session_id: str, engine) -> Optional[Dict[str, str]]:
    if not session_id or engine is None:
        return None
    try:
        rows = list(engine.task_list(session_id, va.VAL_TASK_TYPE_GLOBAL_OUTLINE, "id", True, False) or [])
    except (ValueError, TypeError) as _e:
        logger.warning(
            f"[volume_plot] 读取 global_outline 失败 session={session_id!r}: {_e}",
            module_name=LOG_MODULE,
        )
        return None
    if not rows:
        return None
    candidate: Any = None
    for r in rows:
        if isinstance(r, dict) and str(r.get("status") or "").lower() in {"completed", "success"}:
            candidate = r
            break
    if candidate is None:
        candidate = rows[0]
    if not isinstance(candidate, dict):
        return None
    plot: str = ""
    summary: str = ""
    ct = candidate.get("content_text")
    try:
        obj = json.loads(ct) if isinstance(ct, str) and ct.strip() else None
    except (ValueError, TypeError):
        obj = None
    if isinstance(obj, dict):
        p = obj.get("plot")
        s = obj.get("summary")
        plot = p.strip() if isinstance(p, str) else ""
        summary = s.strip() if isinstance(s, str) else ""
    if not plot and not summary:
        return None
    combined_parts: List[str] = []
    if plot:
        combined_parts.append("【全局剧情】\n" + plot)
    return {
        "plot": plot,
        "summary": summary,
        "combined": "\n\n".join(combined_parts),
    }


def _parse_llm_dict_response(resp_content: Any) -> Dict[str, Any]:
    if resp_content is None:
        return {}
    if isinstance(resp_content, dict):
        return resp_content
    for attr in ("content", "result", "answer", "output", "data", "payload"):
        try:
            candidate = getattr(resp_content, attr, None)
        except (ValueError, TypeError):
            candidate = None
        if isinstance(candidate, dict):
            return candidate
        if isinstance(candidate, str) and candidate.strip():
            resp_content = candidate
            break
    raw_text = ""
    if isinstance(resp_content, str):
        raw_text = resp_content.strip()
    else:
        try:
            raw_text = str(resp_content).strip()
        except (ValueError, TypeError):
            raw_text = ""
    if not raw_text:
        return {}
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict):
            return parsed
    except (ValueError, TypeError):
        pass
    try:
        evaluated = ast.literal_eval(raw_text)
        if isinstance(evaluated, dict):
            return evaluated
    except (ValueError, TypeError):
        pass
    start, end = raw_text.find("{"), raw_text.rfind("}")
    if start >= 0 and end > start:
        sliced = raw_text[start: end + 1]
        try:
            parsed = json.loads(sliced)
            if isinstance(parsed, dict):
                return parsed
        except (ValueError, TypeError):
            pass
        try:
            evaluated = ast.literal_eval(sliced)
            if isinstance(evaluated, dict):
                return evaluated
        except (ValueError, TypeError):
            pass
    return {}


def _escape_static_braces_keep_vars(template: str, variable_names: set) -> str:
    if not isinstance(template, str):
        return ""
    variable_names = {str(n) for n in variable_names}

    protected: Dict[str, str] = {}
    counter = {"n": 0}

    def _guard(match: "re.Match[str]") -> str:
        name = match.group(1)
        if name in variable_names:
            token = f"__CAPVAR_GUARD_{counter['n']}__"
            counter["n"] += 1
            protected[token] = match.group(0)
            return token
        return match.group(0)

    guarded = _VAR_PATTERN.sub(_guard, template)
    escaped = wrap_static_json(guarded)
    for token, orig in protected.items():
        escaped = escaped.replace(token, orig)
    return escaped


async def _resolve_capability(
        session_id: str,
        capability_id: str,
        engine,
        summary: str,
) -> Dict[str, Any]:
    try:
        cap_raw = engine.capability_config_get(session_id, capability_id)
    except (ValueError, TypeError) as e:
        logger.error(
            f"查询能力配置异常 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="查询能力配置失败，请查看后端日志获取详细信息")

    cap = cap_raw if isinstance(cap_raw, dict) else None
    if cap is None:
        logger.warning(
            f"能力配置不存在 {summary}，尝试初始化默认能力后重试",
            module_name=LOG_MODULE,
        )
        try:
            engine.capability_config_init_defaults(session_id)
        except (ValueError, TypeError) as e:
            logger.warning(
                f"初始化默认能力失败 {summary}: {e}",
                module_name=LOG_MODULE,
            )
        try:
            cap_raw = engine.capability_config_get(session_id, capability_id)
            cap = cap_raw if isinstance(cap_raw, dict) else None
        except (ValueError, TypeError) as e:
            logger.error(
                f"重试查询能力配置异常 {summary}: {e}",
                module_name=LOG_MODULE,
                exc_info=True,
            )
            raise HTTPException(status_code=500, detail="查询能力配置失败，请查看后端日志获取详细信息")

    if cap is None:
        logger.error(
            f"能力未找到或未初始化 {summary}",
            module_name=LOG_MODULE,
        )
        raise HTTPException(
            status_code=404,
            detail=f"能力 {capability_id} 未找到，请先初始化该作品的能力配置",
        )
    return cap


def _load_compiled_prompt(
        session_id: str,
        capability_id: str,
        engine,
        summary: str,
) -> str:
    try:
        compiled_prompt = engine.capability_config_get_compiled_prompt(session_id, capability_id)
    except (ValueError, TypeError) as e:
        logger.error(
            f"获取编译后 Prompt 异常 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="获取编译后 Prompt 失败，请查看后端日志获取详细信息")

    if not compiled_prompt or not isinstance(compiled_prompt, str):
        logger.error(
            f"编译后 Prompt 为空 {summary}",
            module_name=LOG_MODULE,
        )
        raise HTTPException(status_code=400, detail=f"能力 {capability_id} 编译后的 Prompt 为空")

    logger.info(
        f"编译后 Prompt 已加载 {summary}, len={len(compiled_prompt)}",
        module_name=LOG_MODULE,
    )
    return compiled_prompt


async def _build_executor(
        cap: Dict[str, Any],
        registry: GlobalSingletonRegistry,
        summary: str,
):
    params_cfg: Dict[str, Any] = cap.get("params") if isinstance(cap.get("params"), dict) else {}
    temperature: Optional[float] = params_cfg.get("temperature")
    top_p: Optional[float] = params_cfg.get("top_p")
    max_tokens: Optional[int] = params_cfg.get("max_tokens")
    response_format = params_cfg.get("response_format")

    if isinstance(temperature, str):
        try:
            temperature = float(temperature)
        except (ValueError, TypeError):
            temperature = None
    if isinstance(top_p, str):
        try:
            top_p = float(top_p)
        except (ValueError, TypeError):
            top_p = None
    if isinstance(max_tokens, str):
        try:
            max_tokens = int(max_tokens)
        except (ValueError, TypeError):
            max_tokens = None

    has_json_rf = isinstance(response_format, dict) and response_format.get("type") == "json_object"
    executor_params_snapshot = {
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "has_response_format": has_json_rf,
    }
    logger.info(
        f"准备执行器 {summary}, params={executor_params_snapshot}",
        module_name=LOG_MODULE,
    )

    try:
        exec_kwargs = {
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        }
        if has_json_rf:
            exec_kwargs["response_format"] = response_format
        executor = await registry.get_executor(**exec_kwargs)
    except (ValueError, TypeError) as e:
        logger.error(
            f"获取执行器失败 {summary}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="获取执行器失败，请查看后端日志获取详细信息")

    expect_json = has_json_rf or cap.get("id") == "extract_session_memory"

    return executor, expect_json


def _write_session_memories(
        session_id: str,
        capability_id: str,
        resp_content: Any,
        summary: str,
        engine,
) -> Tuple[int, List[str]]:
    if capability_id != "extract_session_memory":
        return 0, []

    if isinstance(resp_content, dict):
        parsed_obj = resp_content
    elif isinstance(resp_content, str):
        from app.utils.llm_utils import extract_json_safely

        parsed_obj = extract_json_safely(resp_content.strip())
        if parsed_obj.get(ke.KEY__ERROR):
            logger.warning(
                f"会话记忆提取结果 JSON 解析失败 {summary}: {parsed_obj.get(ke.KEY__ERROR)}",
                module_name=LOG_MODULE,
            )
            parsed_obj = {}
    else:
        parsed_obj = {}

    memories_node = None
    if isinstance(parsed_obj.get("extract_session_memory"), dict):
        memories_node = parsed_obj["extract_session_memory"].get("memories")
    if memories_node is None and isinstance(parsed_obj.get("memories"), list):
        memories_node = parsed_obj["memories"]
    if not isinstance(memories_node, list):
        memories_node = []

    memories_list: List[str] = []
    for m in memories_node:
        if isinstance(m, str):
            s = m.strip()
            # 放宽：> 50 字才直接丢弃；≤ 50 字全量保留并注入（前端展示、后端持久化、模型注入三处一致，均不截断）
            if s and len(s) <= 50:
                memories_list.append(s)

    seen = set()
    dedup_memories: List[str] = []
    for m in memories_list:
        if m not in seen:
            seen.add(m)
            dedup_memories.append(m)

    logger.info(
        f"会话记忆提取 {summary}: 候选{len(memories_node)}条 → 去重后{len(dedup_memories)}条",
        module_name=LOG_MODULE,
    )

    memories_created = 0
    for content in dedup_memories:
        try:
            engine.session_memory_create(
                json.dumps({"session_id": session_id, "content": content}, ensure_ascii=False)
            )
            memories_created += 1
        except (ValueError, TypeError) as e:
            msg_e = str(e)
            if "UNIQUE" in msg_e.upper() or "duplicate" in msg_e.lower():
                logger.debug(
                    f"会话记忆已存在，跳过 {summary}: content_preview={_mask_text(content, 60)!r}",
                    module_name=LOG_MODULE,
                )
            else:
                logger.warning(
                    f"写入会话记忆失败 {summary}: {e}, content_preview={_mask_text(content, 60)!r}",
                    module_name=LOG_MODULE,
                )

    return memories_created, dedup_memories


def _write_llm_log(
        session_id: str,
        capability_id: str,
        task_id: Optional[int],
        formatted_prompt: str,
        resp_content: Any,
        llm_resp: Any,
        summary: str,
        engine,
) -> int:
    cost_dict = getattr(llm_resp, "cost", {}) or {}
    token_cost: float = float(cost_dict.get(ke.KEY_TOTAL) or 0)
    try:
        vendor = str(getattr(llm_resp, "vendor", None) or "unknown").strip() or "unknown"
        model = str(getattr(llm_resp, "model", None) or "unknown").strip() or "unknown"
        elapsed_ms = float(getattr(llm_resp, "elapsed_ms", None) or 0.0)
        latency_sec = round(elapsed_ms / 1000.0, 4)

        extra_meta: Dict[str, Any] = {}
        raw_resp = getattr(llm_resp, "raw", None)
        if raw_resp:
            extra_meta["raw_response"] = str(raw_resp)
        if cost_dict:
            extra_meta["token_usage"] = cost_dict
        if elapsed_ms > 0:
            extra_meta["elapsed_ms"] = elapsed_ms

        err_type = getattr(llm_resp, "err", None)
        err_msg = getattr(llm_resp, "msg", None)
        err_errors = getattr(llm_resp, "errors", None) or []
        llm_valid = getattr(llm_resp, "valid", None)

        has_validation_errors = (not llm_valid) if llm_valid is not None else False
        has_llm_errors = bool(err_type)

        if err_errors:
            extra_meta["validation_errors"] = [str(e) for e in err_errors]

        log_payload: Dict[str, Any] = {
            "session_id": session_id,
            "capability_id": capability_id,
            "vendor": vendor,
            "model": model,
            "prompt": formatted_prompt,
            "response": str(resp_content) if resp_content is not None else "",
            "token_cost": token_cost,
            "latency": latency_sec,
            "extra_meta": extra_meta if extra_meta else None,
        }
        if isinstance(task_id, int):
            log_payload["task_id"] = int(task_id)

        if has_llm_errors or has_validation_errors:
            error_detail_parts: List[str] = []
            if err_errors:
                error_detail_parts.extend(str(e) for e in err_errors)
            if err_msg:
                error_detail_parts.append(str(err_msg))
            if error_detail_parts:
                detail_joined = "; ".join(error_detail_parts)
                if err_type:
                    log_payload["error"] = f"{err_type}: {detail_joined}"
                else:
                    log_payload["error"] = detail_joined
            elif err_type:
                log_payload["error"] = str(err_type)
            else:
                log_payload["error"] = "validation"

        engine.llm_invoke_log_create(json.dumps(log_payload, ensure_ascii=False))
    except (ValueError, TypeError, RuntimeError) as e:
        logger.warning(
            f"写入 LLM 调用日志失败 {summary}: {type(e).__name__}: {e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
    return int(token_cost)


# ========== 能力幂等检查与 SSE meta 构造（公共复用）==========
# 能力索引匹配维度：定义每个 capability 在幂等检查和 SSE 推送时需要的索引字段。
# - None：该能力为全局类（无卷章索引），不参与幂等检查。
# - "volume"：仅按 volume_index 唯一标识。
#   注意 chapter_plot_design 的 chapter_index 在引擎层固定为 0（见 _precreate_chapter_plot_task），
#   故归入 "volume" 维度，避免误用 chapter_index 匹配。
# - "chapter"：按 volume_index + chapter_index 双重标识。
_CAPABILITY_INDEX_DIMENSIONS: Dict[str, Optional[str]] = {
    va.VAL_TASK_TYPE_EXTRACTION: None,
    va.VAL_TASK_TYPE_GLOBAL_OUTLINE: None,
    va.VAL_TASK_TYPE_VOLUME_OUTLINE: "volume",
    va.VAL_TASK_TYPE_CHAPTER_OUTLINE: "volume",
    va.VAL_TASK_TYPE_CHAPTER_EVENTS: "chapter",
    va.VAL_TASK_TYPE_CHAPTER_CONTENT: "chapter",
}

# 任务进行中状态集合（与 Rust src/entity/task.rs TaskStatus 枚举严格对齐）
_TASK_IN_PROGRESS_STATUSES = frozenset({"pending", "running"})

# 陈旧任务判定阈值：超过此时间的 pending/running 任务视为残留（服务重启或异常中断）
_STALE_TASK_THRESHOLD = timedelta(minutes=30)


def _is_task_stale(task: Dict[str, Any]) -> bool:
    """判断任务是否陈旧（updated_at 距今超过阈值）。

    SQLite 存储格式: datetime('now', 'localtime') → "YYYY-MM-DD HH:MM:SS"
    无时间戳或无法解析时视为陈旧（保守策略，允许重试）。
    """
    ts_str = task.get("updated_at") or task.get("created_at") or ""
    if not ts_str:
        return True
    try:
        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return True
    return datetime.now() - ts > _STALE_TASK_THRESHOLD


def _capability_index_dimension(capability_id: str) -> Optional[str]:
    """返回该能力的索引匹配维度；未登记返回 None（视为不参与幂等检查）。"""
    return _CAPABILITY_INDEX_DIMENSIONS.get(capability_id)


def _build_sse_meta(
        capability_id: str,
        *,
        progress: int,
        success: Optional[bool] = None,
        session_id: Optional[str] = None,
        volume_index: Optional[int] = None,
        chapter_index: Optional[int] = None,
        **extras: Any,
) -> Dict[str, Any]:
    """统一构造 SSE task_progress 的 meta 字段，按能力维度自动带上索引，禁止散写。"""
    meta: Dict[str, Any] = {"progress": int(progress), "capability_id": capability_id}
    if success is not None:
        meta["success"] = bool(success)
    if session_id is not None:
        meta["session_id"] = session_id
    dim = _capability_index_dimension(capability_id)
    if dim == "volume":
        if volume_index is not None:
            meta["volume_index"] = int(volume_index)
    elif dim == "chapter":
        if volume_index is not None:
            meta["volume_index"] = int(volume_index)
        if chapter_index is not None:
            meta["chapter_index"] = int(chapter_index)
    if extras:
        meta.update(extras)
    return meta


def _find_in_progress_capability_task(
        engine,
        session_id: str,
        capability_id: str,
        volume_index: Optional[int],
        chapter_index: Optional[int],
) -> Optional[Dict[str, Any]]:
    """查找同 capability_id 下进行中的同维度任务，返回冲突任务或 None。

    仅对 _CAPABILITY_INDEX_DIMENSIONS 中登记的能力进行检查；
    全局类能力（global/extract）返回 None，语义上允许重新生成。
    """
    dim = _capability_index_dimension(capability_id)
    if dim is None:
        return None
    try:
        existing = list(engine.task_list(session_id, capability_id, "created_at", False, False) or [])
    except (ValueError, TypeError):
        return None
    vi = int(volume_index) if volume_index is not None else 0
    ci = int(chapter_index) if chapter_index is not None else 0
    for t in existing:
        if not isinstance(t, dict):
            continue
        if str(t.get("status") or "").lower() not in _TASK_IN_PROGRESS_STATUSES:
            continue
        t_vol = t.get("volume_index")
        t_chap = t.get("chapter_index")
        # 维度匹配
        if dim == "volume":
            matched = t_vol is not None and int(t_vol) == vi
        elif dim == "chapter":
            matched = (t_vol is not None and int(t_vol) == vi
                       and t_chap is not None and int(t_chap) == ci)
        else:
            matched = False
        if not matched:
            continue
        # 陈旧检测：服务重启或异常中断后残留的 running/pending 任务自动清理，允许重试
        if _is_task_stale(t):
            _stale_id = t.get("id")
            logger.warning(
                f"检测到陈旧任务（task_id={_stale_id}, status={t.get('status')}, "
                f"updated_at={t.get('updated_at')}），自动标记为 failed 以解除幂等锁",
                module_name=LOG_MODULE,
            )
            try:
                engine.task_update(str(_stale_id), json.dumps({"status": "failed"}))
            except Exception as cleanup_err:
                logger.error(f"清理陈旧任务失败（task_id={_stale_id}）：{cleanup_err}", module_name=LOG_MODULE)
            continue  # 清理后继续查找其他冲突
        return t
    return None


async def _check_capability_idempotency(
        sse,
        capability_name: str,
        capability_id: str,
        session_id: str,
        engine,
        volume_index: Optional[int],
        chapter_index: Optional[int],
) -> None:
    """幂等检查：同维度任务进行中时广播失败事件并抛 409 Conflict。

    前端依据 409 与 SSE 中的 error=ALREADY_IN_PROGRESS 给出友好提示，
    避免用户重复点击触发数据竞争。
    """
    conflict = _find_in_progress_capability_task(
        engine, session_id, capability_id, volume_index, chapter_index
    )
    if conflict is None:
        return
    dim = _capability_index_dimension(capability_id)
    if dim == "volume":
        loc = f"第 {int(volume_index or 0) + 1} 卷"
    else:
        loc = f"第 {int(volume_index or 0) + 1} 卷第 {int(chapter_index or 0) + 1} 章"
    logger.warning(
        f"幂等检查：{capability_name}({capability_id}) {loc}已有进行中任务 (task_id={conflict.get('id')})",
        module_name=LOG_MODULE,
    )
    await sse.broadcast("task_progress", {
        ke.KEY_TITLE: capability_name,
        ke.KEY_CONTENT: f"{loc}该任务正在生成中，请稍候...",
        ke.KEY_META: _build_sse_meta(
            capability_id, progress=0, success=False,
            volume_index=volume_index, chapter_index=chapter_index,
            error="ALREADY_IN_PROGRESS",
            message=f"{loc}该任务正在生成中，请稍候...",
        ),
    })
    raise HTTPException(
        status_code=409,
        detail=f"{loc}{capability_name}正在生成中，请稍候再试",
    )


async def _invoke_capability_single(
        session_id: str,
        capability_id: str,
        variables: Dict[str, Any],
        engine,
        registry: GlobalSingletonRegistry,
        *,
        task_id: Optional[int] = None,
        pre_resolved_cap: Optional[Dict[str, Any]] = None,
        pre_compiled_prompt: Optional[str] = None,
        shared_executor=None,
        shared_expect_json: Optional[bool] = None,
) -> Dict[str, Any]:
    from app.core.domain.capabilities.handlers_core import (
        _parse_index_params,
        _precreate_task_for_capability,
        _prepare_and_render_prompt,
        _invoke_llm_and_get_response,
        _parse_response_and_write_logs,
        _build_result,
        _finalize_task_on_success,
    )

    sse = get_sse_manager()
    var_keys = sorted(list(variables.keys()))
    summary = f"session_id={session_id!r}, capability_id={capability_id!r}, variables_keys={var_keys}"

    capability_names = {
        va.VAL_TASK_TYPE_EXTRACTION: "提取会话记忆",
        va.VAL_TASK_TYPE_GLOBAL_OUTLINE: "生成全局剧情",
        va.VAL_TASK_TYPE_VOLUME_OUTLINE: "生成卷纲剧情",
        va.VAL_TASK_TYPE_CHAPTER_OUTLINE: "生成章纲剧情",
        va.VAL_TASK_TYPE_CHAPTER_EVENTS: "生成章节事件链",
        va.VAL_TASK_TYPE_CHAPTER_CONTENT: "生成正文",
    }
    capability_name = capability_names.get(capability_id, capability_id)

    if not session_id or not capability_id:
        raise HTTPException(status_code=400, detail="session_id 和 capability_id 均为必填")

    logger.info(f"调用能力 {summary}", module_name=LOG_MODULE)

    # 开始执行事件在索引解析之前，不带 volume/chapter_index；
    # 前端匹配最终态事件即可，无需匹配此进度事件。
    await sse.broadcast("task_progress", {
        ke.KEY_TITLE: capability_name,
        ke.KEY_CONTENT: "开始执行...",
        ke.KEY_META: _build_sse_meta(
            capability_id, progress=0, session_id=session_id,
        )
    })

    stat_tracker: Dict[str, Any] = {"cost": 0.0, "finalized": False}

    memory_task_owned_by_me: bool = False
    global_plot_task_owned_by_me: bool = False
    volume_task_owned_by_me: bool = False
    chapter_task_owned_by_me: bool = False
    chapter_events_task_owned_by_me: bool = False
    chapter_content_task_owned_by_me: bool = False

    def _finalize_stat(success: bool, cost: Optional[float] = None):
        if stat_tracker.get("finalized"):
            return
        stat_tracker["finalized"] = True
        real_cost = stat_tracker["cost"] if cost is None else float(cost or 0.0)
        _record_capability_stat_safely(engine, capability_id, success, real_cost)

    # 预初始化，确保 except 块中变量已绑定，避免 if 'xxx' in locals() 兜底
    effective_task_id: Optional[int] = None
    memory_task_owned_by_me = False
    global_plot_task_owned_by_me = False
    volume_task_owned_by_me = False
    chapter_task_owned_by_me = False
    chapter_events_task_owned_by_me = False
    chapter_content_task_owned_by_me = False
    # 预初始化索引参数，防止 _parse_index_params 抛异常时 except 块中引用未绑定变量
    parsed_volume_index: int = 0
    parsed_chapter_index: int = 0

    def _finalize_on_failure():
        """异常路径统一收尾：str 参数传空串，Optional 参数传 None。"""
        _finalize_task_on_success(
            capability_id, effective_task_id, False, engine, session_id, 0,
            memory_task_owned_by_me, global_plot_task_owned_by_me, volume_task_owned_by_me,
            chapter_task_owned_by_me, chapter_events_task_owned_by_me, chapter_content_task_owned_by_me,
            None, None, None, None, None, "",
            None, None, "", None,
            None, "", "", None, None,
            "", None, None,
        )

    try:
        parsed_volume_index, parsed_chapter_index = _parse_index_params(variables)

        if capability_id == va.VAL_TASK_TYPE_VOLUME_OUTLINE and parsed_volume_index <= 0:
            try:
                _existing = list(engine.task_list(session_id, va.VAL_TASK_TYPE_VOLUME_OUTLINE, "sequence", False, False) or [])
                _completed = [t for t in _existing
                              if isinstance(t, dict) and str(t.get("status") or "").lower() in {"completed", "success"}]
                parsed_volume_index = len(_completed)
            except (ValueError, TypeError):
                parsed_volume_index = 0

        # ========== 幂等检查：同维度任务进行中时拒绝重复生成（统一入口）==========
        # 覆盖 volume/chapter_plot/chapter_events/chapter_content；
        # global/extract_session_memory 维度为 None，跳过检查（语义上允许重新生成）。
        await _check_capability_idempotency(
            sse, capability_name, capability_id, session_id, engine,
            parsed_volume_index, parsed_chapter_index,
        )

        await sse.broadcast("task_progress", {
            ke.KEY_TITLE: capability_name,
            ke.KEY_CONTENT: "初始化任务...",
            ke.KEY_META: _build_sse_meta(
                capability_id, progress=10, session_id=session_id,
                volume_index=parsed_volume_index, chapter_index=parsed_chapter_index,
            )
        })

        effective_task_id, memory_task_owned_by_me, global_plot_task_owned_by_me, volume_task_owned_by_me, chapter_task_owned_by_me, chapter_events_task_owned_by_me, chapter_content_task_owned_by_me = _precreate_task_for_capability(
            capability_id, task_id, engine, session_id, parsed_volume_index, parsed_chapter_index)

        await sse.broadcast("task_progress", {
            ke.KEY_TITLE: capability_name,
            ke.KEY_CONTENT: "准备 Prompt...",
            ke.KEY_META: _build_sse_meta(
                capability_id, progress=20,
                volume_index=parsed_volume_index, chapter_index=parsed_chapter_index,
            )
        })

        cap = pre_resolved_cap if isinstance(pre_resolved_cap, dict) else await _resolve_capability(
            session_id, capability_id, engine, summary
        )

        compiled_prompt = (
            pre_compiled_prompt
            if isinstance(pre_compiled_prompt, str)
            else _load_compiled_prompt(session_id, capability_id, engine, summary)
        )

        try:
            await sse.broadcast("task_progress", {
                ke.KEY_TITLE: capability_name,
                ke.KEY_CONTENT: "渲染 Prompt...",
                ke.KEY_META: _build_sse_meta(
                    capability_id, progress=30,
                    volume_index=parsed_volume_index, chapter_index=parsed_chapter_index,
                )
            })

            formatted_prompt, _, last_volume_global_plot_ref, last_chapter_volume_plot_ref, last_chapter_volume_index, last_chapter_events_volume_index, last_chapter_events_chapter_index, last_chapter_content_volume_index, last_chapter_content_chapter_index = _prepare_and_render_prompt(
                session_id, capability_id, variables, engine,
                compiled_prompt, summary, parsed_volume_index, parsed_chapter_index)
        except ValueError as e:
            logger.warning(f"Prompt 变量缺失 {summary}: {e}", module_name=LOG_MODULE)
            _finalize_stat(False)
            await sse.broadcast("task_progress", {
                ke.KEY_TITLE: capability_name,
                ke.KEY_CONTENT: f"Prompt 变量缺失: {str(e)}",
                ke.KEY_META: _build_sse_meta(
                    capability_id, progress=100, success=False,
                    volume_index=parsed_volume_index, chapter_index=parsed_chapter_index,
                )
            })
            raise HTTPException(status_code=400, detail="Prompt 变量缺失，请检查输入参数是否完整")
        except (ValueError, TypeError) as e:
            logger.error(f"Prompt 渲染异常 {summary}: {e}", module_name=LOG_MODULE, exc_info=True)
            _finalize_stat(False)
            await sse.broadcast("task_progress", {
                ke.KEY_TITLE: capability_name,
                ke.KEY_CONTENT: f"Prompt 渲染失败: {str(e)}",
                ke.KEY_META: _build_sse_meta(
                    capability_id, progress=100, success=False,
                    volume_index=parsed_volume_index, chapter_index=parsed_chapter_index,
                )
            })
            raise HTTPException(status_code=500, detail="Prompt 渲染失败，请查看后端日志获取详细信息")

        try:
            await sse.broadcast("task_progress", {
                ke.KEY_TITLE: capability_name,
                ke.KEY_CONTENT: "调用大模型...",
                ke.KEY_META: _build_sse_meta(
                    capability_id, progress=50,
                    volume_index=parsed_volume_index, chapter_index=parsed_chapter_index,
                )
            })

            llm_resp = await _invoke_llm_and_get_response(
                cap, registry, formatted_prompt, session_id, capability_id,
                shared_executor, shared_expect_json
            )
        except (ValueError, TypeError) as e:
            logger.error(f"模型调用异常 {summary}: {e}", module_name=LOG_MODULE, exc_info=True)
            _finalize_stat(False)
            await sse.broadcast("task_progress", {
                ke.KEY_TITLE: capability_name,
                ke.KEY_CONTENT: f"模型调用失败: {str(e)}",
                ke.KEY_META: _build_sse_meta(
                    capability_id, progress=100, success=False,
                    volume_index=parsed_volume_index, chapter_index=parsed_chapter_index,
                )
            })
            raise HTTPException(status_code=500, detail="模型调用异常，请查看后端日志获取详细信息")

        if not llm_resp or not getattr(llm_resp, "ok", False):
            msg = getattr(llm_resp, "msg", None) or "模型调用失败"
            err = getattr(llm_resp, "err", "")
            logger.error(f"模型调用未成功 {summary}: err={err}, msg={msg}", module_name=LOG_MODULE)
            _finalize_stat(False)
            await sse.broadcast("task_progress", {
                ke.KEY_TITLE: capability_name,
                ke.KEY_CONTENT: f"模型调用失败: {msg}",
                ke.KEY_META: _build_sse_meta(
                    capability_id, progress=100, success=False,
                    volume_index=parsed_volume_index, chapter_index=parsed_chapter_index,
                )
            })
            raise HTTPException(status_code=502, detail=f"模型调用失败: {msg}")

        # 临时调试日志：检查验证器是否拒绝了响应
        llm_resp_ok = getattr(llm_resp, "ok", False)
        llm_resp_valid = getattr(llm_resp, "valid", False)
        llm_resp_content = getattr(llm_resp, "content", None)
        llm_resp_errors = getattr(llm_resp, "errors", [])
        logger.info(f"[调试] llm_resp.ok={llm_resp_ok}, llm_resp.valid={llm_resp_valid}, content_type={type(llm_resp_content).__name__}, content_value={repr(llm_resp_content)[:200]}, errors={llm_resp_errors[:5]} {summary}", module_name=LOG_MODULE)
        
        raw_resp_for_log = _mask_text(str(getattr(llm_resp, "content", None)), 300)
        logger.info(f"模型调用完成 {summary}, content_preview={raw_resp_for_log!r}", module_name=LOG_MODULE)

        await sse.broadcast("task_progress", {
            ke.KEY_TITLE: capability_name,
            ke.KEY_CONTENT: "解析结果...",
            ke.KEY_META: _build_sse_meta(
                capability_id, progress=80,
                volume_index=parsed_volume_index, chapter_index=parsed_chapter_index,
            )
        })

        (_, memories_created, last_token_cost, last_dedup_memories,
         last_plot_text, last_summary_text,
         last_volume_plot_text, last_volume_summary_text,
         last_chapter_plot_text, last_chapter_summary_text,
         last_chapter_events_list, last_chapter_events_chapter_plot_ref,
         last_chapter_events_chapter_summary_ref,
         chapter_content_text) = _parse_response_and_write_logs(capability_id, llm_resp, session_id, summary,
                                                                engine, effective_task_id, formatted_prompt, variables)

        stat_tracker["cost"] = last_token_cost

        await sse.broadcast("task_progress", {
            ke.KEY_TITLE: capability_name,
            ke.KEY_CONTENT: "保存结果...",
            ke.KEY_META: _build_sse_meta(
                capability_id, progress=90,
                volume_index=parsed_volume_index, chapter_index=parsed_chapter_index,
            )
        })

        result = _build_result(
            capability_id, last_token_cost, session_id, memories_created,
            last_dedup_memories, effective_task_id,
            last_plot_text, last_summary_text,
            last_volume_plot_text, last_volume_summary_text, last_volume_global_plot_ref,
            last_chapter_plot_text, last_chapter_summary_text, last_chapter_volume_plot_ref, last_chapter_volume_index,
            last_chapter_events_list, last_chapter_events_chapter_plot_ref, last_chapter_events_chapter_summary_ref,
            last_chapter_events_volume_index, last_chapter_events_chapter_index,
            chapter_content_text
        )

        _finalize_stat(True, last_token_cost)
        _finalize_task_on_success(
            capability_id, effective_task_id, True, engine, session_id, last_token_cost,
            memory_task_owned_by_me, global_plot_task_owned_by_me, volume_task_owned_by_me,
            chapter_task_owned_by_me, chapter_events_task_owned_by_me, chapter_content_task_owned_by_me,
            last_dedup_memories, last_plot_text, last_summary_text,
            last_volume_plot_text, last_volume_summary_text, last_volume_global_plot_ref,
            last_chapter_plot_text, last_chapter_summary_text, last_chapter_volume_plot_ref, last_chapter_volume_index,
            last_chapter_events_list, last_chapter_events_chapter_plot_ref, last_chapter_events_chapter_summary_ref,
            last_chapter_events_volume_index, last_chapter_events_chapter_index,
            chapter_content_text, last_chapter_content_volume_index, last_chapter_content_chapter_index
        )

        await sse.broadcast("task_progress", {
            ke.KEY_TITLE: capability_name,
            ke.KEY_CONTENT: f"执行完成 (token: {last_token_cost})",
            ke.KEY_META: _build_sse_meta(
                capability_id, progress=100, success=True,
                volume_index=parsed_volume_index, chapter_index=parsed_chapter_index,
                token_cost=last_token_cost, task_id=effective_task_id,
            )
        })

        logger.info(
            f"能力执行完成 {summary}: memories_created={memories_created}, token={last_token_cost}, task_id={effective_task_id!r}",
            module_name=LOG_MODULE)
        return result

    except HTTPException as he:
        _finalize_stat(False)
        _finalize_on_failure()
        await sse.broadcast("task_progress", {
            ke.KEY_TITLE: capability_name,
            ke.KEY_CONTENT: f"执行失败: {he.detail}",
            ke.KEY_META: _build_sse_meta(
                capability_id, progress=100, success=False,
                volume_index=parsed_volume_index, chapter_index=parsed_chapter_index,
            )
        })
        raise he
    except asyncio.CancelledError:
        # 客户端断开连接（刷新/关闭页面）时 FastAPI cancel 协程，CancelledError 继承 BaseException
        # 不被 except Exception 捕获；必须在此显式处理，确保任务状态回写为 failed，否则永久卡在 pending
        _finalize_stat(False)
        _finalize_on_failure()
        logger.warning(f"能力执行被取消（客户端断开） {summary}", module_name=LOG_MODULE)
        raise
    except Exception as e:
        logger.error(f"能力执行未知异常 {summary}: {e}", module_name=LOG_MODULE, exc_info=True)
        _finalize_stat(False)
        _finalize_on_failure()
        await sse.broadcast("task_progress", {
            ke.KEY_TITLE: capability_name,
            ke.KEY_CONTENT: f"执行失败: {str(e)}",
            ke.KEY_META: _build_sse_meta(
                capability_id, progress=100, success=False,
                volume_index=parsed_volume_index, chapter_index=parsed_chapter_index,
            )
        })
        raise HTTPException(status_code=500, detail="能力执行失败，请查看后端日志获取详细信息")


def _parse_task_id(payload: Dict[str, Any]) -> Optional[int]:
    """安全地从 payload 解析 task_id；非法或空返回 None。"""
    raw = payload.get("task_id")
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return int(raw) if raw > 0 else None
    if isinstance(raw, float):
        i = int(raw)
        return i if i > 0 and float(i) == raw else None
    if isinstance(raw, str):
        s = raw.strip()
        if not s or not s.lstrip("-").isdigit():
            return None
        try:
            i = int(s)
            return i if i > 0 else None
        except (ValueError, TypeError):
            return None
    return None


def _get_entry_id(entry: Any) -> Optional[int]:
    """统一从语义词汇/会话记忆 entry 中取整型 id；拿不到返回 None。

    兼容 PyO3 Rust 对象（.id 属性）和 Python dict（["id"] 键）两种形态。
    """
    entry_id: Any = None
    if isinstance(entry, dict):
        entry_id = entry.get("id")
    else:
        try:
            entry_id = getattr(entry, "id", None)
        except (ValueError, TypeError):
            entry_id = None
    if entry_id is None:
        return None
    if isinstance(entry_id, bool):
        return None
    if isinstance(entry_id, int):
        return int(entry_id) if entry_id > 0 else None
    if isinstance(entry_id, float):
        i = int(entry_id)
        return i if i > 0 and float(i) == entry_id else None
    if isinstance(entry_id, str):
        s = str(entry_id).strip()
        if not s or not s.lstrip("-").isdigit():
            return None
        try:
            i = int(s)
            return i if i > 0 else None
        except (ValueError, TypeError):
            return None
    return None


def _semantic_entry_name(entry: Any, category: str) -> str:
    """统一取语义词汇/会话记忆的展示名称（字符 50 字截断）。"""
    name = _extract_semantic_entry_text(entry, category)
    if not name:
        if isinstance(entry, dict):
            name = str(entry.get("name") or entry.get("content") or "")
        else:
            try:
                name = str(getattr(entry, "name", None) or getattr(entry, "content", None) or "")
            except (ValueError, TypeError):
                name = ""
    return _limit_text(name, 50)


def _semantic_entry_completeness_pct(entry: Any, category: str) -> int:
    """计算条目完整度 %；基于 attributes / aliases 非空字段，全量条目上限 6 个字段 → 100%。"""
    attrs: Dict[str, Any] = {}
    aliases: List[Any] = []
    if isinstance(entry, dict):
        attrs = entry.get("attributes") or {}
        aliases = entry.get("aliases") or []
        if not isinstance(attrs, dict):
            attrs = {}
        if not isinstance(aliases, list):
            aliases = []
    else:
        try:
            a = getattr(entry, "attributes", None)
            attrs = a if isinstance(a, dict) else {}
            al = getattr(entry, "aliases", None)
            aliases = al if isinstance(al, list) else []
        except (ValueError, TypeError):
            attrs = {}
            aliases = []
    non_empty_attrs = sum(1 for v in (attrs or {}).values() if isinstance(v, str) and v.strip())
    non_empty_aliases = sum(1 for v in (aliases or []) if isinstance(v, str) and v.strip())
    denom = 6
    numer = min(denom, non_empty_attrs + non_empty_aliases)
    if category == "session_memory":
        raw_content = _extract_semantic_entry_text(entry, category) or ""
        numer = min(3, 1 if raw_content.strip() else 0 + (1 if len(raw_content.strip()) > 20 else 0) + (
            1 if len(raw_content.strip()) > 100 else 0))
        denom = 3
    return int(round(numer / denom * 100)) if denom > 0 else 0


def _entry_display_meta(entry: Any, category: str) -> Dict[str, Any]:
    """从语义词汇 entry 中提取前端展示用的干净元数据（不含匹配用的拼接文本）：

    返回：{
      "display_name": str,  # 干净的 entry.name（不拼 aliases/attributes，50字截断）
      "aliases": List[str], # 干净的昵称列表（过滤空/与原名重复，顺序保持）
      "type_label": str,    # 类型中文标签（角色→男主/女主；时间→节日/朝代；地点→城市/门派；无则空串）
      "attrs_summary": str, # 核心属性摘要串（如"男 / 22岁 / 学生"，无则空串）
    }
    会话记忆（category=="session_memory"）：type_label/attrs_summary 置空，aliases 留空，display_name 取内容前50字。
    """
    display_name = ""
    aliases: List[str] = []
    type_label = ""
    attrs_summary = ""

    # ---- ① dict / PyO3 对象统一取字段工具 ----
    def _get_field(obj: Any, key: str) -> Any:
        if isinstance(obj, dict):
            return obj.get(key)
        try:
            return getattr(obj, key, None)
        except (ValueError, TypeError):
            return None

    def _str_list(val: Any) -> List[str]:
        if not isinstance(val, (list, tuple, set)):
            return []
        out: List[str] = []
        for v in val:
            if v is None:
                continue
            s = str(v).strip()
            if s:
                out.append(s)
        return out

    if category == "session_memory":
        # 会话记忆：display_name 用 content/text 前50字
        for f in ("content", "text", "body", "summary", "memory", "rule"):
            v = _get_field(entry, f)
            if isinstance(v, str) and v.strip():
                display_name = _limit_text(v.strip(), 50)
                break
        return {"display_name": display_name, "aliases": [], "type_label": "", "attrs_summary": ""}

    # ---- ② display_name（干净的 name，不含 aliases/attributes 拼接）----
    name_raw = _get_field(entry, "name")
    if not isinstance(name_raw, str) or not name_raw.strip():
        name_raw = _get_field(entry, "content")
        if not isinstance(name_raw, str) or not name_raw.strip():
            name_raw = ""
    display_name = _limit_text(str(name_raw).strip() if name_raw else "", 50)

    # ---- ③ aliases（昵称列表，过滤空和与原名重复）----
    aliases_raw = _str_list(_get_field(entry, "aliases"))
    seen_alias: set = set()
    if display_name:
        seen_alias.add(display_name)
    for a in aliases_raw:
        if a and a not in seen_alias:
            seen_alias.add(a)
            aliases.append(a)

    # ---- ④ type_label：按 category 选择映射字段键，通过 VAL_PROMPT_VALUE_ZH 中文化 ----
    value_zh_map = va.VAL_PROMPT_VALUE_ZH if isinstance(va.VAL_PROMPT_VALUE_ZH, dict) else {}

    def _lookup_zh(field_key_in_map: str, raw_value: Any) -> str:
        """从 VAL_PROMPT_VALUE_ZH[field_key_in_map] 中查表返回中文；查不到返回 raw_value 原字符串（空则""）。"""
        if raw_value is None:
            return ""
        s_raw = str(raw_value).strip()
        if not s_raw:
            return ""
        sub_map = value_zh_map.get(field_key_in_map) if isinstance(value_zh_map.get(field_key_in_map), dict) else {}
        if not sub_map:
            return s_raw
        low = s_raw.lower()
        if low in sub_map and isinstance(sub_map[low], str) and sub_map[low].strip():
            return sub_map[low].strip()
        for k, v in sub_map.items():
            if isinstance(k, str) and k.lower() == low and isinstance(v, str) and v.strip():
                return v.strip()
        return s_raw

    if category == "entity":
        # 角色：映射字段 key = "type"（VAL_PROMPT_VALUE_ZH["type"] 含 hero→男主/mentor→导师 …）
        type_raw = _get_field(entry, "type")
        type_label = _lookup_zh("type", type_raw)
    elif category == "temporal":
        # 时间：映射字段 key = "time_type"（VAL_PROMPT_VALUE_ZH["time_type"] 含 era→时代/festival→节日 …）
        type_raw = _get_field(entry, "type")
        type_label = _lookup_zh("time_type", type_raw)
    elif category == "location":
        # 地点：先试 location_type 字段，再回退 type 字段；映射字段 key = "location_type"
        type_raw = _get_field(entry, "location_type")
        if type_raw is None or (isinstance(type_raw, str) and not type_raw.strip()):
            type_raw = _get_field(entry, "type")
        type_label = _lookup_zh("location_type", type_raw)

    # ---- ⑤ attrs_summary：核心属性拼接（角色→性别/年龄/职业；时间→start/end/描述；地点→parent/描述）----
    attr_parts: List[str] = []
    if category == "entity":
        # 性别（中文化）+ 年龄 + 职业 + 身份
        gender_raw = _get_field(entry, "gender")
        if isinstance(gender_raw, str) and not gender_raw.strip():
            # 如果顶层没取到，尝试 attributes["gender"]
            attrs = _get_field(entry, "attributes")
            if isinstance(attrs, dict):
                gender_raw = attrs.get("gender")
        gender_zh = _lookup_zh("gender", gender_raw)
        if gender_zh:
            attr_parts.append(gender_zh)
        for f in ("age", "profession", "identity"):
            v = _get_field(entry, f)
            if isinstance(v, str) and v.strip():
                attr_parts.append(_limit_text(v.strip(), 20))
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                attr_parts.append(str(v))
    elif category == "temporal":
        for f in ("start", "end", "duration", "description"):
            v = _get_field(entry, f)
            if isinstance(v, str) and v.strip():
                attr_parts.append(_limit_text(v.strip(), 30))
                if len(attr_parts) >= 2:
                    break
    elif category == "location":
        for f in ("description", "size", "population"):
            v = _get_field(entry, f)
            if isinstance(v, str) and v.strip():
                attr_parts.append(_limit_text(v.strip(), 30))
                if len(attr_parts) >= 2:
                    break
    if attr_parts:
        # 过滤掉与 type_label / display_name 完全重复的条目（避免视觉冗余）
        clean_parts: List[str] = []
        for p in attr_parts:
            if not p:
                continue
            if type_label and p == type_label:
                continue
            if display_name and p == display_name:
                continue
            clean_parts.append(p)
        attrs_summary = " / ".join(clean_parts[:3])

    return {
        "display_name": display_name,
        "aliases": aliases,
        "type_label": type_label,
        "attrs_summary": attrs_summary,
    }


def _split_slot_by_selected_ids(
        all_with_meta: List[Dict[str, Any]],
        selected_ids_set: set,
        category: str,
        max_score: float,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """把 all_with_meta 按 selected_ids 拆成 selected/unselected 两个展示列表，带 match_pct 和 completeness_pct。"""
    selected: List[Dict[str, Any]] = []
    unselected: List[Dict[str, Any]] = []
    for meta in all_with_meta:
        entry = meta["entry"]
        eid = _get_entry_id(entry)
        if eid is None:
            continue
        total_score = float(meta["score"]) + float(meta["richness_bonus"])

        # ---- match_pct：max_score<=0 降级为完整度近似匹配（下限30%，避免视觉全灰死区）----
        if max_score <= 0:
            comp_raw = _semantic_entry_completeness_pct(entry, category)
            match_pct = max(30, int(round(comp_raw * 0.6)))
            # 降级不弹"无命中关键词"，视觉保持正向体验
            reason = ""
        else:
            match_pct = int(round(min(1.0, total_score / max_score) * 100))
            if match_pct < 30:
                if meta["keyword_hits"] <= 0:
                    reason = "不推荐：无命中关键词"
                else:
                    reason = "不推荐：与当前剧情相关性弱"
            else:
                reason = ""

        display_meta = _entry_display_meta(entry, category)
        display_name = display_meta["display_name"]
        if not display_name:
            continue
        item = {
            "id": eid,
            "name": display_name,
            "aliases": display_meta["aliases"],
            "type_label": display_meta["type_label"],
            "attrs_summary": display_meta["attrs_summary"],
            "match_pct": match_pct,
            "completeness_pct": _semantic_entry_completeness_pct(entry, category),
            "reason": reason,
        }
        if eid in selected_ids_set:
            selected.append(item)
        else:
            unselected.append(item)
    return selected, unselected


def build_preview_injection(
        session_id: str,
        capability_id: str,
        variables: Dict[str, Any],
        engine,
) -> Dict[str, Any]:
    """注入预览业务逻辑：提取关键词 → 拉取候选 → 四类打分 → 归一化 → 构造预览结果。

    供路由层 preview-injection 端点调用的纯业务函数，不处理 HTTP 参数校验。
    """
    summary = (
        f"session_id={session_id!r}, capability_id={capability_id!r}, "
        f"variables_keys={sorted(list(variables.keys())) if isinstance(variables, dict) else []}"
    )
    logger.info(f"[预览注入入口] {summary}", module_name=LOG_MODULE)

    try:
        from app.core.services.local_tools import LocalTextTools
    except (ValueError, TypeError):
        LocalTextTools = None  # type: ignore

    cfg = _get_injection_cfg()

    # 从 variables 中提取「剧情核心文本」：5 个能力的入参字段不完全相同，统一按优先级取第一个非空
    core_plot_candidates: List[str] = []
    for k in ("core_plot_text", "global_plot_text", "volume_plot_text", "source_text", "chapter_plot_text"):
        v = variables.get(k)
        if isinstance(v, str) and v.strip():
            core_plot_candidates.append(v.strip())
    core_plot_text = core_plot_candidates[0] if core_plot_candidates else ""

    # 1) 提取剧情核心关键词
    try:
        text_tools = LocalTextTools.get_instance() if LocalTextTools is not None else None
    except (ValueError, TypeError):
        text_tools = None
    keywords, _c, _e = _extract_core_keywords(core_plot_text, text_tools)

    # 2) 拉取全量候选
    try:
        characters_all = list(engine.semantic_vocabulary_list(session_id, "entity") or [])
    except (ValueError, TypeError):
        characters_all = []
    try:
        timelines_all = list(engine.semantic_vocabulary_list(session_id, "temporal") or [])
    except (ValueError, TypeError):
        timelines_all = []
    try:
        locations_all = list(engine.semantic_vocabulary_list(session_id, "location") or [])
    except (ValueError, TypeError):
        locations_all = []
    try:
        memories_all = list(engine.session_memory_list(session_id) or [])
    except (ValueError, TypeError):
        memories_all = []

    # 3) 四类打分（语义词汇三类 + 会话记忆单独）
    char_sel, _, char_all_meta = _score_and_select(characters_all, "entity", cfg["character_count"],
                                                   cfg["character_chars"], keywords)
    time_sel, _, time_all_meta = _score_and_select(timelines_all, "temporal", cfg["timeline_count"],
                                                   cfg["timeline_chars"], keywords)
    loc_sel, _, loc_all_meta = _score_and_select(locations_all, "location", cfg["location_count"],
                                                 cfg["location_chars"], keywords)

    # 会话记忆：复用 _build_global_plot_injection_variables 里的打分逻辑，同时构造 all_meta
    kw_set = {str(k) for k in keywords if k and len(str(k)) >= 2}
    mem_meta_raw = []
    for idx, m in enumerate(memories_all or []):
        m = m if isinstance(m, dict) else {}
        content = ""
        for field in ("content", "text", "body", "summary", "memory", "rule"):
            v = m.get(field) if isinstance(m, dict) else (getattr(m, field, None) if not isinstance(m, dict) else None)
            if isinstance(v, str) and v.strip():
                content = v.strip()
                break
        if not content:
            continue
        content = _limit_text(content, cfg["session_chars"])
        if not content:
            continue
        score = 0
        if kw_set:
            for kw in kw_set:
                if len(kw) >= 2 and kw in content:
                    score += 1
        richness_base = min(0.5, (len(content) / 100.0) * 0.1) if content else 0.0
        richness_bonus = min(richness_base, 0.5 * max(score, 1))
        mem_meta_raw.append({
            "entry": m,
            "score": float(score),
            "richness_bonus": float(richness_bonus),
            "keyword_hits": int(score),
            "_time_key": _entry_time_sort_key(m),
            "_idx": idx,
        })
    mem_meta_raw.sort(
        key=lambda x: (-(x["score"] + x["richness_bonus"]), (-x["_time_key"][0], -x["_time_key"][1]), x["_idx"]))
    mem_selected_ids: List[int] = []
    mem_all_meta: List[Dict[str, Any]] = []
    for m in mem_meta_raw:
        eid = _get_entry_id(m["entry"])
        mem_all_meta.append({k: v for k, v in m.items() if not k.startswith("_")})  # 去掉内部字段
        if len(mem_selected_ids) < cfg["session_count"] and eid is not None and m["entry"] is not None:
            content_ok = any(
                isinstance((m["entry"].get(f) if isinstance(m["entry"], dict) else getattr(m["entry"], f, None)), str)
                and ((m["entry"].get(f) if isinstance(m["entry"], dict) else getattr(m["entry"], f,
                                                                                     None)) or "").strip()
                for f in ("content", "text", "body", "summary", "memory", "rule")
            )
            if content_ok:
                mem_selected_ids.append(eid)

    # 取四类 selected id 集合
    char_selected_ids_set = {x for x in (_get_entry_id(e) for e in char_sel) if x is not None}
    time_selected_ids_set = {x for x in (_get_entry_id(e) for e in time_sel) if x is not None}
    loc_selected_ids_set = {x for x in (_get_entry_id(e) for e in loc_sel) if x is not None}
    mem_selected_ids_set = set(mem_selected_ids)

    # 归一化 max_score（每类独立归一，每类最高分=100%；0 分保护打 warning）
    def _max_total_score(meta_list: List[Dict[str, Any]]) -> float:
        if not meta_list:
            return 0.0
        return max((float(m["score"]) + float(m["richness_bonus"])) for m in meta_list)

    char_max = _max_total_score(char_all_meta)
    time_max = _max_total_score(time_all_meta)
    loc_max = _max_total_score(loc_all_meta)
    mem_max = _max_total_score(mem_all_meta)
    for cat_name, cat_max in [("角色", char_max), ("时间", time_max), ("地点", loc_max), ("会话记忆", mem_max)]:
        if cat_max <= 0 and len(
                char_all_meta if cat_name == "角色" else time_all_meta if cat_name == "时间" else loc_all_meta if cat_name == "地点" else mem_all_meta) > 0:
            logger.warning(
                f"[预览注入打分归一化失败] {summary} category={cat_name!r}：所有条目 score=0，已降级为 match_pct 全 0 展示",
                module_name=LOG_MODULE,
            )

    char_selected, char_unselected = _split_slot_by_selected_ids(char_all_meta, char_selected_ids_set, "entity",
                                                                 char_max)
    time_selected, time_unselected = _split_slot_by_selected_ids(time_all_meta, time_selected_ids_set, "temporal",
                                                                 time_max)
    loc_selected, loc_unselected = _split_slot_by_selected_ids(loc_all_meta, loc_selected_ids_set, "location", loc_max)
    mem_selected, mem_unselected = _split_slot_by_selected_ids(mem_all_meta, mem_selected_ids_set, "session_memory",
                                                               mem_max)

    # summary：总字数 / tokens 预估（1 字≈1.5 token，context_usage_pct 按 1M 上限估）
    per_cat_est = {
        "entity": {"selected_count": len(char_selected), "max_count": cfg["character_count"],
                   "max_chars_per_entry": cfg["character_chars"], "expand_times": 1},
        "temporal": {"selected_count": len(time_selected), "max_count": cfg["timeline_count"],
                     "max_chars_per_entry": cfg["timeline_chars"], "expand_times": 1},
        "location": {"selected_count": len(loc_selected), "max_count": cfg["location_count"],
                     "max_chars_per_entry": cfg["location_chars"], "expand_times": 1},
        "session_mem": {"selected_count": len(mem_selected), "max_count": cfg["session_count"],
                        "max_chars_per_entry": cfg["session_chars"], "expand_times": 1},
    }
    total_chars = (
            per_cat_est["entity"]["selected_count"] * per_cat_est["entity"]["max_chars_per_entry"] *
            per_cat_est["entity"]["expand_times"]
            + per_cat_est["temporal"]["selected_count"] * per_cat_est["temporal"]["max_chars_per_entry"] *
            per_cat_est["temporal"]["expand_times"]
            + per_cat_est["location"]["selected_count"] * per_cat_est["location"]["max_chars_per_entry"] *
            per_cat_est["location"]["expand_times"]
            + per_cat_est["session_mem"]["selected_count"] * per_cat_est["session_mem"]["max_chars_per_entry"] *
            per_cat_est["session_mem"]["expand_times"]
            + len(core_plot_text)
    )
    total_tokens = int(total_chars / 1.5)
    context_capacity = 1_000_000  # DeepSeek V4 1M context
    context_usage_pct = round(total_tokens / context_capacity * 100, 1)

    payload_return = {
        "summary": {
            "total_chars": int(total_chars),
            "total_tokens": int(total_tokens),
            "context_usage_pct": float(context_usage_pct),
            "per_category_budget": {
                "entity": {
                    "max_count": per_cat_est["entity"]["max_count"],
                    "max_chars_per_entry": per_cat_est["entity"]["max_chars_per_entry"],
                    "expand_times": per_cat_est["entity"]["expand_times"],
                },
                "temporal": {
                    "max_count": per_cat_est["temporal"]["max_count"],
                    "max_chars_per_entry": per_cat_est["temporal"]["max_chars_per_entry"],
                    "expand_times": per_cat_est["temporal"]["expand_times"],
                },
                "location": {
                    "max_count": per_cat_est["location"]["max_count"],
                    "max_chars_per_entry": per_cat_est["location"]["max_chars_per_entry"],
                    "expand_times": per_cat_est["location"]["expand_times"],
                },
                "session_mem": {
                    "max_count": per_cat_est["session_mem"]["max_count"],
                    "max_chars_per_entry": per_cat_est["session_mem"]["max_chars_per_entry"],
                    "expand_times": per_cat_est["session_mem"]["expand_times"],
                },
            },
        },
        "slots": {
            "characters": {"selected": char_selected, "unselected": char_unselected},
            "temporals": {"selected": time_selected, "unselected": time_unselected},
            "locations": {"selected": loc_selected, "unselected": loc_unselected},
            "session_memories": {"selected": mem_selected, "unselected": mem_unselected},
        },
        "defaults": {
            "selected_character_ids": sorted(char_selected_ids_set),
            "selected_temporal_ids": sorted(time_selected_ids_set),
            "selected_location_ids": sorted(loc_selected_ids_set),
            "selected_session_memory_ids": sorted(mem_selected_ids_set),
        },
    }

    logger.info(
        f"[预览注入下发] {summary} char_sel={len(char_selected)} char_unsel={len(char_unselected)} "
        f"time_sel={len(time_selected)} time_unsel={len(time_unselected)} "
        f"loc_sel={len(loc_selected)} loc_unsel={len(loc_unselected)} "
        f"mem_sel={len(mem_selected)} mem_unsel={len(mem_unselected)} total_chars={total_chars}",
        module_name=LOG_MODULE,
    )
    return payload_return
