"""能力执行处理器核心业务逻辑（domain 层）。

从 routers/capability_handlers.py 整体迁移：能力参数预处理、响应解析、
结果构造、Prompt 渲染、LLM 调用、任务回填等。
依赖 core.py 提供的注入与工具能力，被 core.py 在 _invoke_capability_single
中懒加载引用，构成 domain 层内部协作。
"""

from typing import Dict, Any, List, Optional, Tuple
import json
from app.common import values as va
from app.common import keys as ke
from app.core.validators.validator_adapter import validate_capability_output
from app.core.registry.global_singleton_registry import GlobalSingletonRegistry
from app.utils.logger import LoggerManager as logger
from app.core.domain.capabilities.core import (
    _build_global_plot_injection_variables,
    _apply_selected_ids_to_injection,
    _parse_llm_dict_response,
    _fetch_latest_global_outline_text,
    LOG_MODULE, _precreate_extract_memory_task, _precreate_global_plot_task, _precreate_chapter_plot_task,
    _precreate_volume_plot_task, _precreate_chapter_events_task, _precreate_chapter_content_task,
    _apply_injection_limits, _escape_static_braces_keep_vars, _build_executor, _write_session_memories, _write_llm_log,
    _finalize_extract_memory_task_safely, _finalize_global_plot_task_safely, _finalize_volume_plot_task_safely,
    _finalize_chapter_plot_task_safely, _finalize_chapter_events_task_safely, _finalize_chapter_content_task_safely,
    _get_injection_cfg, _number_items,
)
from app.utils.prompt_util import safe_format_prompt
from app.utils.llm_utils import resolve_max_tokens


def _extract_plot_from_volume_content(content_text: str) -> str:
    if not isinstance(content_text, str) or not content_text.strip():
        return ""
    try:
        obj = json.loads(content_text)
    except (ValueError, TypeError):
        return ""
    if not isinstance(obj, dict):
        return ""
    direct = obj.get("plot", "")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    volumes = obj.get("volumes", [])
    if isinstance(volumes, list) and volumes:
        last = volumes[-1]
        if isinstance(last, dict):
            vp = last.get("plot", "")
            if isinstance(vp, str) and vp.strip():
                return vp.strip()
    return ""


def _prepare_effective_vars_global_plot(
        session_id: str,
        variables: Dict[str, Any],
        engine: Any,
        summary: str,
) -> Tuple[Dict[str, Any], str]:
    effective_vars: Dict[str, Any] = dict(variables) if isinstance(variables, dict) else {}
    core_plot_text = ""
    for k in ("core_plot_text", "core"):
        v = effective_vars.get(k)
        if isinstance(v, str) and v.strip():
            core_plot_text = v.strip()
            break
    if not core_plot_text:
        ui = effective_vars.get("user_input")
        if isinstance(ui, str) and ui.strip():
            core_plot_text = ui.strip()

    parts = _build_global_plot_injection_variables(
        session_id, core_plot_text, engine
    )

    # 第二阶段：应用用户选择的 ID（角色、时间、地点、会话记忆）
    _apply_selected_ids_to_injection(
        session_id, "global_plot_design", variables, effective_vars, parts, engine, summary
    )

    if not effective_vars.get("user_input"):
        cfg = _get_injection_cfg()
        effective_vars["user_input"] = parts.build_user_input(cfg["user_input_chars"])
        effective_vars["session_memory"] = parts.build_session_memory()

    effective_vars.pop("core_plot_text", None)
    effective_vars.pop("core", None)
    return effective_vars, core_plot_text


def _prepare_effective_vars_volume_plot(
        session_id: str,
        variables: Dict[str, Any],
        engine: Any,
        summary: str,
) -> Tuple[Dict[str, Any], str, str]:
    effective_vars: Dict[str, Any] = dict(variables) if isinstance(variables, dict) else {}

    # global_plot_design 使用纯文本（模板已有【全局剧情】:\n标签，避免重复）
    outline_info = _fetch_latest_global_outline_text(session_id, engine)
    global_design_text = ""
    if isinstance(outline_info, dict):
        if isinstance(outline_info.get("plot"), str) and outline_info["plot"].strip():
            global_design_text = outline_info["plot"].strip()
    if not global_design_text:
        for k in ("global_plot_text", "global_plot_design"):
            v = effective_vars.get(k)
            if isinstance(v, str) and v.strip():
                global_design_text = v.strip()
                break
    effective_vars["global_plot_design"] = global_design_text
    last_volume_global_plot_ref = global_design_text

    # 用户设定：core_plot_text 来自用户输入，不是全局剧情
    user_core_text = ""
    for k in ("core_plot_text", "core"):
        v = effective_vars.get(k)
        if isinstance(v, str) and v.strip():
            user_core_text = v.strip()
            break

    parts = _build_global_plot_injection_variables(
        session_id, user_core_text, engine
    )
    _apply_selected_ids_to_injection(
        session_id, "volume_plot_design", variables, effective_vars, parts, engine, summary
    )
    if not effective_vars.get("user_input"):
        cfg = _get_injection_cfg()
        effective_vars["user_input"] = parts.build_user_input(cfg["user_input_chars"])
        effective_vars["session_memory"] = parts.build_session_memory()

    # 解析卷序号，确定是否第一卷，注入上一卷剧情
    parsed_volume_index, _ = _parse_index_params(variables)
    if parsed_volume_index <= 0:
        try:
            existing = list(engine.task_list(session_id, va.VAL_TASK_TYPE_VOLUME_OUTLINE, "sequence", False, False) or [])
            completed = [t for t in existing
                         if isinstance(t, dict) and str(t.get("status") or "").lower() in {"completed", "success"}]
            parsed_volume_index = len(completed)
        except (ValueError, TypeError):
            parsed_volume_index = 0

    if parsed_volume_index > 0:
        try:
            prev_tasks = list(engine.task_list(session_id, va.VAL_TASK_TYPE_VOLUME_OUTLINE, "sequence", False, False) or [])
            completed = [t for t in prev_tasks
                         if isinstance(t, dict) and str(t.get("status") or "").lower() in {"completed", "success"}]
            if completed:
                prev_task = completed[-1]
                ct = prev_task.get("content_text")
                prev_plot = _extract_plot_from_volume_content(ct if isinstance(ct, str) else "")
                effective_vars["previous_volume"] = prev_plot
                logger.info(
                    f"[volume_plot] 上一卷查找: found_task_id={prev_task.get('id') if isinstance(prev_task, dict) else '?'}, "
                    f"has_previous_volume=bool({bool(prev_plot)}), prev_plot_len={len(prev_plot)}",
                    module_name=LOG_MODULE,
                )
            else:
                effective_vars["previous_volume"] = ""
                logger.info(
                    f"[volume_plot] 上一卷查找: 无已完成卷任务 (共{len(prev_tasks)}条)",
                    module_name=LOG_MODULE,
                )
        except (ValueError, TypeError) as e:
            effective_vars["previous_volume"] = ""
            logger.warning(
                f"[volume_plot] 上一卷查找异常: {e}",
                module_name=LOG_MODULE,
                exc_info=True,
            )
    else:
        effective_vars["previous_volume"] = ""

    for tmp_k in ("global_plot_text", "core_plot_text", "core"):
        effective_vars.pop(tmp_k, None)
    logger.info(
        f"[volume_plot] 最终注入变量键集合 {summary}: effective_keys={sorted(list(effective_vars.keys()))}, "
        f"has_nlp_summary={'nlp_summary' in effective_vars}, "
        f"has_session_memory={'session_memory' in effective_vars}, "
        f"has_global_plot_design={'global_plot_design' in effective_vars}, "
        f"has_previous_volume={'previous_volume' in effective_vars and bool(effective_vars.get('previous_volume'))}, "
        f"volume_index={parsed_volume_index}",
        module_name=LOG_MODULE,
    )
    return effective_vars, user_core_text, last_volume_global_plot_ref


def _prepare_effective_vars_chapter_plot(
        session_id: str,
        variables: Dict[str, Any],
        engine: Any,
        summary: str,
        last_chapter_volume_index: Optional[int],
) -> Tuple[Dict[str, Any], str, str, Optional[int]]:
    effective_vars: Dict[str, Any] = dict(variables) if isinstance(variables, dict) else {}

    # volume_plot_design 使用纯文本（模板已有【卷纲剧情】:标签）
    volume_plot_text = ""
    if isinstance(variables, dict):
        for _k in ("volume_plot_text", "volume_plot_design", "volume_plot", "volume_event"):
            _v = variables.get(_k)
            if isinstance(_v, str) and _v.strip():
                volume_plot_text = _v.strip()
                break
    if not volume_plot_text:
        for _k in ("volume_plot_text", "volume_plot_design", "volume_plot"):
            _v = effective_vars.get(_k)
            if isinstance(_v, str) and _v.strip():
                volume_plot_text = _v.strip()
                break
    effective_vars["volume_plot_design"] = volume_plot_text
    last_chapter_volume_plot_ref = volume_plot_text

    # 用户设定：core_plot_text 来自用户输入，不是卷纲或全局剧情
    user_core_text = ""
    for k in ("core_plot_text", "core"):
        v = effective_vars.get(k)
        if isinstance(v, str) and v.strip():
            user_core_text = v.strip()
            break

    parts = _build_global_plot_injection_variables(
        session_id, user_core_text, engine
    )
    _apply_selected_ids_to_injection(
        session_id, "chapter_plot_design", variables, effective_vars, parts, engine, summary
    )
    if not effective_vars.get("user_input"):
        cfg = _get_injection_cfg()
        effective_vars["user_input"] = parts.build_user_input(cfg["user_input_chars"])
        effective_vars["session_memory"] = parts.build_session_memory()

    # 注入上一章剧情：优先使用前端传入的值（续生成模式），否则从引擎查找
    existing_prev = effective_vars.get("previous_chapter")
    if isinstance(existing_prev, str) and existing_prev.strip():
        pass
    else:
        effective_vars["previous_chapter"] = ""
        vi_val = int(last_chapter_volume_index) if isinstance(last_chapter_volume_index, (int, float)) else 0
        if vi_val > 0:
            try:
                prev_vol = vi_val - 1
                vol_tasks = list(engine.task_list(session_id, va.VAL_TASK_TYPE_VOLUME_OUTLINE, "created_at", False, False) or [])
                prev_vol_task = None
                prev_vol_tasks = []
                for vt in vol_tasks:
                    if isinstance(vt, dict) and int(vt.get("sort_order") or 0) == prev_vol:
                        prev_vol_task = vt
                        break
                if prev_vol_task:
                    prev_tasks = list(engine.task_list(session_id, va.VAL_TASK_TYPE_CHAPTER_OUTLINE, "sequence", False, False) or [])
                    completed = [t for t in prev_tasks
                                 if isinstance(t, dict) and str(t.get("status") or "").lower() in {"completed", "success"}]
                    prev_vol_tasks = [t for t in completed
                                      if isinstance(t, dict) and int(t.get("parent_id") or 0) == int(prev_vol_task.get("id") or 0)]
                if prev_vol_tasks:
                    prev_vol_tasks.sort(key=lambda t: int(t.get("sequence") or 0))
                    prev_task = prev_vol_tasks[-1]
                    ct = prev_task.get("content_text")
                    if isinstance(ct, str) and ct.strip():
                        try:
                            obj = json.loads(ct)
                            chapters = obj.get("chapters", []) if isinstance(obj, dict) else []
                            if chapters and isinstance(chapters[-1], dict):
                                prev_plot = chapters[-1].get("plot", "")
                                effective_vars["previous_chapter"] = str(prev_plot) if prev_plot else ""
                        except (ValueError, TypeError):
                            pass
            except (ValueError, TypeError):
                pass

    for tmp_k in (
            "global_plot_text", "core_plot_text", "core",
            "volume_plot_text", "volume_plot", "volume_event",
            "global_plot_design",
            "volume_index", "volume_idx", "sequence", "seq",
            "chapter_index", "chapter_idx",
    ):
        effective_vars.pop(tmp_k, None)
    logger.info(
        f"[chapter_plot] 最终注入变量键集合 {summary}: effective_keys={sorted(list(effective_vars.keys()))}, "
        f"has_nlp_summary={'nlp_summary' in effective_vars}, "
        f"has_session_memory={'session_memory' in effective_vars}, "
        f"has_volume_plot_design={'volume_plot_design' in effective_vars}, "
        f"has_previous_chapter={'previous_chapter' in effective_vars and bool(effective_vars.get('previous_chapter'))}, "
        f"volume_index={last_chapter_volume_index!r}",
        module_name=LOG_MODULE,
    )
    return effective_vars, user_core_text, last_chapter_volume_plot_ref, last_chapter_volume_index


def _prepare_effective_vars_chapter_events(
        session_id: str,
        variables: Dict[str, Any],
        engine: Any,
        summary: str,
        last_chapter_events_volume_index: Optional[int],
        last_chapter_events_chapter_index: Optional[int],
) -> Tuple[Dict[str, Any], str, Optional[int], Optional[int]]:
    effective_vars: Dict[str, Any] = dict(variables) if isinstance(variables, dict) else {}

    # chapter_plot_design 使用纯文本（模板已有【章纲剧情】:标签）
    chapter_plot_text = ""
    if isinstance(variables, dict):
        for _k in ("chapter_plot_text", "chapter_plot_design", "chapter_plot", "chapter_event"):
            _v = variables.get(_k)
            if isinstance(_v, str) and _v.strip():
                chapter_plot_text = _v.strip()
                break
    if not chapter_plot_text:
        for _k in ("chapter_plot_text", "chapter_plot_design", "chapter_plot"):
            _v = effective_vars.get(_k)
            if isinstance(_v, str) and _v.strip():
                chapter_plot_text = _v.strip()
                break
    effective_vars["chapter_plot_design"] = chapter_plot_text

    # 用户设定：core_plot_text 来自用户输入，不是章纲/卷纲/全局剧情
    user_core_text = ""
    for k in ("core_plot_text", "core"):
        v = effective_vars.get(k)
        if isinstance(v, str) and v.strip():
            user_core_text = v.strip()
            break

    parts = _build_global_plot_injection_variables(
        session_id, user_core_text, engine
    )
    _apply_selected_ids_to_injection(
        session_id, "chapter_events_design", variables, effective_vars, parts, engine, summary
    )
    if not effective_vars.get("user_input"):
        cfg = _get_injection_cfg()
        effective_vars["user_input"] = parts.build_user_input(cfg["user_input_chars"])
        effective_vars["session_memory"] = parts.build_session_memory()
    for tmp_k in (
            "global_plot_text", "core_plot_text", "core",
            "volume_plot_text", "volume_plot", "volume_event",
            "chapter_plot_text", "chapter_plot", "chapter_event",
            "chapter_summary",
            "global_plot_design", "volume_plot_design",
            "volume_index", "volume_idx", "chapter_index", "chapter_idx",
            "sequence", "seq",
    ):
        effective_vars.pop(tmp_k, None)
    logger.info(
        f"[chapter_events] 最终注入变量键集合 {summary}: effective_keys={sorted(list(effective_vars.keys()))}, "
        f"has_nlp_summary={'nlp_summary' in effective_vars}, "
        f"has_session_memory={'session_memory' in effective_vars}, "
        f"has_user_input={'user_input' in effective_vars}, "
        f"has_chapter_plot_design={'chapter_plot_design' in effective_vars}",
        module_name=LOG_MODULE,
    )
    return effective_vars, user_core_text, last_chapter_events_volume_index, last_chapter_events_chapter_index


def _prepare_effective_vars_chapter_content(
        session_id: str,
        variables: Dict[str, Any],
        engine: Any,
        summary: str,
        last_chapter_content_volume_index: Optional[int],
        last_chapter_content_chapter_index: Optional[int],
) -> Tuple[Dict[str, Any], str, Optional[int], Optional[int]]:
    effective_vars: Dict[str, Any] = dict(variables) if isinstance(variables, dict) else {}

    # chapter_plot_design 使用纯文本（模板已有【当前章纲剧情】:标签）
    chapter_plot_text = ""
    if isinstance(variables, dict):
        for _k in ("chapter_plot_text", "chapter_plot_design", "chapter_plot", "chapter_event"):
            _v = variables.get(_k)
            if isinstance(_v, str) and _v.strip():
                chapter_plot_text = _v.strip()
                break
    if not chapter_plot_text:
        for _k in ("chapter_plot_text", "chapter_plot_design", "chapter_plot"):
            _v = effective_vars.get(_k)
            if isinstance(_v, str) and _v.strip():
                chapter_plot_text = _v.strip()
                break
    effective_vars["chapter_plot_design"] = chapter_plot_text

    # chapter_events 使用纯文本（模板已有【当前章节事件链】:标签），按行加序号
    chapter_events_text = ""
    for _k in ("chapter_events", "chapter_events_text", "chapter_events_design"):
        _v = effective_vars.get(_k)
        if isinstance(_v, str) and _v.strip():
            chapter_events_text = _v.strip()
            break
    if chapter_events_text:
        lines = [_l.strip() for _l in chapter_events_text.split("\n") if _l.strip()]
        effective_vars["chapter_events"] = _number_items(lines)

    # 用户设定：core_plot_text 来自用户输入，不是章纲/卷纲/全局剧情
    user_core_text = ""
    for k in ("core_plot_text", "core"):
        v = effective_vars.get(k)
        if isinstance(v, str) and v.strip():
            user_core_text = v.strip()
            break

    parts = _build_global_plot_injection_variables(
        session_id, user_core_text, engine
    )
    _apply_selected_ids_to_injection(
        session_id, "chapter_content_generation", variables, effective_vars, parts, engine, summary
    )
    if not effective_vars.get("user_input"):
        cfg = _get_injection_cfg()
        effective_vars["user_input"] = parts.build_user_input(cfg["user_input_chars"])
        effective_vars["session_memory"] = parts.build_session_memory()
    for tmp_k in (
            "global_plot_text", "core_plot_text", "core",
            "volume_plot_text", "volume_plot", "volume_event",
            "chapter_plot_text", "chapter_plot", "chapter_event",
            "chapter_events_text", "chapter_events_design",
            "chapter_summary",
            "global_plot_design", "volume_plot_design",
            "volume_index", "volume_idx", "chapter_index", "chapter_idx",
            "sequence", "seq",
    ):
        effective_vars.pop(tmp_k, None)
    logger.info(
        f"[chapter_content] 最终注入变量键集合 {summary}: effective_keys={sorted(list(effective_vars.keys()))}, "
        f"has_nlp_summary={'nlp_summary' in effective_vars}, "
        f"has_session_memory={'session_memory' in effective_vars}, "
        f"has_user_input={'user_input' in effective_vars}, "
        f"has_chapter_plot_design={'chapter_plot_design' in effective_vars}, "
        f"has_chapter_events={'chapter_events' in effective_vars}",
        module_name=LOG_MODULE,
    )
    return effective_vars, user_core_text, last_chapter_content_volume_index, last_chapter_content_chapter_index


def _parse_response_global_plot(resp_content: Any, summary: str) -> Tuple[str, str]:
    last_plot_text = ""
    last_summary_text = ""
    try:
        parsed = _parse_llm_dict_response(resp_content)
        inner = None
        if isinstance(parsed, dict):
            if isinstance(parsed.get("global_plot_design"), dict):
                inner = parsed["global_plot_design"]
            elif isinstance(parsed.get("result"), dict) and isinstance(
                    parsed["result"].get("global_plot_design"), dict):
                inner = parsed["result"]["global_plot_design"]
        if isinstance(inner, dict):
            plot_raw = inner.get("plot")
            summary_raw = inner.get("summary")
            last_plot_text = "" if plot_raw is None else str(plot_raw).strip()
            last_summary_text = "" if summary_raw is None else str(summary_raw).strip()
    except Exception as _e:
        logger.warning(
            f"解析 global_plot_design 响应出错，将使用原始文本兜底 {summary}: {_e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
    raw = "" if resp_content is None else str(resp_content).strip()
    if raw and not (isinstance(last_plot_text, str) and last_plot_text.strip()):
        last_plot_text = raw
        logger.warning(
            f"global_plot_design 响应结构缺少 plot/summary 字段，已用原始文本兜底为 plot，长度={len(raw)} chars {summary}",
            module_name=LOG_MODULE,
        )
    return last_plot_text, last_summary_text


def _parse_response_volume_plot(resp_content: Any, summary: str) -> Tuple[str, str]:
    last_plot_text = ""
    last_summary_text = ""
    try:
        parsed = _parse_llm_dict_response(resp_content)
        inner = None
        if isinstance(parsed, dict):
            if isinstance(parsed.get("volume_plot_design"), dict):
                inner = parsed["volume_plot_design"]
            elif isinstance(parsed.get("result"), dict) and isinstance(
                    parsed["result"].get("volume_plot_design"), dict):
                inner = parsed["result"]["volume_plot_design"]
        if isinstance(inner, dict):
            plot_raw = inner.get("plot")
            summary_raw = inner.get("summary")
            last_plot_text = "" if plot_raw is None else str(plot_raw).strip()
            last_summary_text = "" if summary_raw is None else str(summary_raw).strip()
    except Exception as _e:
        logger.warning(
            f"解析 volume_plot_design 响应出错，将使用原始文本兜底 {summary}: {_e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
    raw = "" if resp_content is None else str(resp_content).strip()
    if raw and not (isinstance(last_plot_text, str) and last_plot_text.strip()):
        last_plot_text = raw
        logger.warning(
            f"volume_plot_design 响应结构缺少 plot/summary 字段，已用原始文本兜底为 plot，长度={len(raw)} chars {summary}",
            module_name=LOG_MODULE,
        )
    return last_plot_text, last_summary_text


def _parse_response_chapter_plot(resp_content: Any, summary: str) -> Tuple[str, str]:
    last_plot_text = ""
    last_summary_text = ""
    try:
        parsed = _parse_llm_dict_response(resp_content)
        inner = None
        if isinstance(parsed, dict):
            if isinstance(parsed.get("chapter_plot_design"), dict):
                inner = parsed["chapter_plot_design"]
            elif isinstance(parsed.get("result"), dict) and isinstance(
                    parsed["result"].get("chapter_plot_design"), dict):
                inner = parsed["result"]["chapter_plot_design"]
        if isinstance(inner, dict):
            plot_raw = inner.get("plot")
            summary_raw = inner.get("summary")
            last_plot_text = "" if plot_raw is None else str(plot_raw).strip()
            last_summary_text = "" if summary_raw is None else str(summary_raw).strip()
    except Exception as _e:
        logger.warning(
            f"解析 chapter_plot_design 响应出错，将使用原始文本兜底 {summary}: {_e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
    raw = "" if resp_content is None else str(resp_content).strip()
    if raw and not (isinstance(last_plot_text, str) and last_plot_text.strip()):
        last_plot_text = raw
        logger.warning(
            f"chapter_plot_design 响应结构缺少 plot/summary 字段，已用原始文本兜底为 plot，长度={len(raw)} chars {summary}",
            module_name=LOG_MODULE,
        )
    return last_plot_text, last_summary_text


def _parse_response_chapter_events(resp_content: Any, variables: Dict[str, Any], summary: str) -> Tuple[List[str], str, str]:
    chapter_events: List[Any] = []
    try:
        parsed = _parse_llm_dict_response(resp_content)
        if isinstance(parsed, dict):
            candidate: Any = None
            if isinstance(parsed.get("chapter_events_design"), dict):
                candidate = parsed["chapter_events_design"]
            elif isinstance(parsed.get("result"), dict) and isinstance(
                    parsed["result"].get("chapter_events_design"), dict):
                candidate = parsed["result"]["chapter_events_design"]
            if candidate is None and isinstance(parsed.get("events"), list):
                chapter_events = list(parsed["events"])
            if isinstance(candidate, dict) and isinstance(candidate.get("events"), list):
                chapter_events = list(candidate["events"])
    except Exception as _e:
        logger.warning(
            f"解析 chapter_events_design 响应出错（将尝试顶层兜底） {summary}: {_e}",
            module_name=LOG_MODULE,
            exc_info=True,
        )
    if not isinstance(chapter_events, list) or not chapter_events:
        raw = "" if resp_content is None else str(resp_content).strip()
        if raw and raw[0:1] == "[":
            try:
                arr = json.loads(raw)
                if isinstance(arr, list):
                    chapter_events = arr
            except Exception:
                pass
    if isinstance(chapter_events, list) and chapter_events:
        clean: List[str] = []
        for e in chapter_events:
            if e is None:
                continue
            if isinstance(e, str):
                s = e.strip()
                if s:
                    clean.append(s)
                continue
            if isinstance(e, dict):
                for _k in ("event", "summary", "text", "desc", "description", "content"):
                    _v = e.get(_k)
                    if isinstance(_v, str) and _v.strip():
                        clean.append(_v.strip())
                        break
        last_chapter_events_list = clean if clean else []
    else:
        last_chapter_events_list = []
    last_chapter_events_chapter_plot_ref = ""
    last_chapter_events_chapter_summary_ref = ""
    if isinstance(variables, dict):
        for _k in ("chapter_plot_text", "chapter_plot_design", "chapter_plot", "chapter_event"):
            _v = variables.get(_k)
            if isinstance(_v, str) and _v.strip():
                last_chapter_events_chapter_plot_ref = _v.strip()[:400]
                break
        for _k in ("chapter_summary", "chapter_summary_text", "chapter_summary_design"):
            _v = variables.get(_k)
            if isinstance(_v, str) and _v.strip():
                last_chapter_events_chapter_summary_ref = _v.strip()[:400]
                break
    if last_chapter_events_list and not (2 <= len(last_chapter_events_list) <= 30):
        logger.warning(
            f"章节事件链结果越界事件数={len(last_chapter_events_list)}，建议区间 [2,30]，前端可手动增删调整 {summary}",
            module_name=LOG_MODULE,
        )
    if not last_chapter_events_list:
        raw_resp = "" if resp_content is None else str(resp_content).strip()
        logger.warning(
            f"chapter_events_design 响应缺少 chapter_events_design.events 字符串数组，兜底解析后仍为空（长度={len(raw_resp)} chars，首300字={raw_resp[:300]!r}）{summary}",
            module_name=LOG_MODULE,
        )
    return last_chapter_events_list, last_chapter_events_chapter_plot_ref, last_chapter_events_chapter_summary_ref


def _parse_response_chapter_content(resp_content: Any, llm_resp: Any, summary: str) -> str:
    llm_valid = getattr(llm_resp, "valid", None)
    llm_errors = getattr(llm_resp, "errors", [])
    logger.info(
        f"[chapter_content_generation] llm_resp.valid={llm_valid}, errors={llm_errors}",
        module_name=LOG_MODULE,
    )
    # 文本模式：执行器走 executor.text()，resp_content 为纯文本字符串
    if isinstance(resp_content, str) and resp_content.strip():
        return resp_content.strip()
    raw = "" if resp_content is None else str(resp_content).strip()
    if raw:
        return raw
    logger.warning(
        f"chapter_content_generation 响应为空（长度={len(raw)} chars，首300字={raw[:300]!r}）{summary}",
        module_name=LOG_MODULE,
    )
    return ""


def _build_result_extract_memory(
        capability_id: str,
        memories_created: int,
        dedup_memories: Optional[List[Any]],
        effective_task_id: Optional[int],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "capability": capability_id,
        "memories_count": len(dedup_memories) if dedup_memories is not None else 0,
        "memories_created": memories_created,
    }
    return result


def _build_result_global_plot(
        capability_id: str,
        last_plot_text: str,
        last_summary_text: str,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "capability": capability_id,
        "plot": last_plot_text or "",
        "summary": last_summary_text or "",
    }
    return result


def _build_result_volume_plot(
        capability_id: str,
        plot_text: str,
        summary_text: str,
        last_volume_global_plot_ref: str,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "capability": capability_id,
        "volume_plot_design": {
            "plot": plot_text or "",
            "summary": summary_text or "",
            "global_plot_ref": last_volume_global_plot_ref,
        },
    }
    return result


def _build_result_chapter_plot(
        capability_id: str,
        plot_text: str,
        summary_text: str,
        last_chapter_volume_plot_ref: str,
        last_chapter_volume_index: Optional[int],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "capability": capability_id,
        "chapter_plot_design": {
            "plot": plot_text or "",
            "summary": summary_text or "",
        },
    }
    return result


def _build_result_chapter_events(
        capability_id: str,
        last_chapter_events_list: List[str],
        last_chapter_events_chapter_plot_ref: str,
        last_chapter_events_volume_index: Optional[int],
        last_chapter_events_chapter_index: Optional[int],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "capability": capability_id,
        "chapter_events_design": {
            "events": list(last_chapter_events_list or []),
            "chapter_plot_ref": last_chapter_events_chapter_plot_ref,
            "volume_index": last_chapter_events_volume_index,
            "chapter_index": last_chapter_events_chapter_index,
        },
    }
    return result


def _build_result_chapter_content(
        capability_id: str,
        chapter_content_text: str,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "capability": capability_id,
        "chapter_content_generation": {
            "content_text": chapter_content_text or "",
        },
    }
    return result


CAPABILITY_HANDLERS: Dict[str, Dict[str, Any]] = {
    "extract_session_memory": {
        "prepare_vars": None,
        "parse_response": None,
        "build_result": _build_result_extract_memory,
    },
    "global_plot_design": {
        "prepare_vars": _prepare_effective_vars_global_plot,
        "parse_response": _parse_response_global_plot,
        "build_result": _build_result_global_plot,
    },
    "volume_plot_design": {
        "prepare_vars": _prepare_effective_vars_volume_plot,
        "parse_response": _parse_response_volume_plot,
        "build_result": _build_result_volume_plot,
    },
    "chapter_plot_design": {
        "prepare_vars": _prepare_effective_vars_chapter_plot,
        "parse_response": _parse_response_chapter_plot,
        "build_result": _build_result_chapter_plot,
    },
    "chapter_events_design": {
        "prepare_vars": _prepare_effective_vars_chapter_events,
        "parse_response": _parse_response_chapter_events,
        "build_result": _build_result_chapter_events,
    },
    "chapter_content_generation": {
        "prepare_vars": _prepare_effective_vars_chapter_content,
        "parse_response": _parse_response_chapter_content,
        "build_result": _build_result_chapter_content,
    },
}


def _parse_index_params(variables: Dict[str, Any]) -> Tuple[int, int]:
    parsed_volume_index: int = 0
    parsed_chapter_index: int = 0
    if isinstance(variables, dict):
        vi_raw = None
        for _k in ("volume_index", "volume_idx", "sequence", "seq"):
            _v = variables.get(_k)
            if isinstance(_v, (int, float)) or (isinstance(_v, str) and _v.strip().isdigit()):
                vi_raw = _v
                break
        if vi_raw is not None:
            try:
                vi_cand = int(vi_raw)
                parsed_volume_index = vi_cand if vi_cand >= 0 else 0
            except Exception:
                parsed_volume_index = 0
        ci_raw = None
        for _k in ("chapter_index", "chapter_idx", "chap_index", "chap_idx"):
            _v = variables.get(_k)
            if isinstance(_v, (int, float)) or (isinstance(_v, str) and _v.strip().isdigit()):
                ci_raw = _v
                break
        if ci_raw is not None:
            try:
                ci_cand = int(ci_raw)
                parsed_chapter_index = ci_cand if ci_cand >= 0 else 0
            except Exception:
                parsed_chapter_index = 0
    return parsed_volume_index, parsed_chapter_index


def _precreate_task_for_capability(
        capability_id: str,
        effective_task_id: Optional[int],
        engine,
        session_id: str,
        parsed_volume_index: int,
        parsed_chapter_index: int,
) -> Tuple[Optional[int], bool, bool, bool, bool, bool, bool]:
    memory_task_owned_by_me = False
    global_plot_task_owned_by_me = False
    volume_task_owned_by_me = False
    chapter_task_owned_by_me = False
    chapter_events_task_owned_by_me = False
    chapter_content_task_owned_by_me = False

    if effective_task_id is not None:
        return effective_task_id, memory_task_owned_by_me, global_plot_task_owned_by_me, \
            volume_task_owned_by_me, chapter_task_owned_by_me, \
            chapter_events_task_owned_by_me, chapter_content_task_owned_by_me

    if capability_id == "extract_session_memory":
        effective_task_id = _precreate_extract_memory_task(engine, session_id)
        memory_task_owned_by_me = isinstance(effective_task_id, int)
    elif capability_id == "global_plot_design":
        effective_task_id = _precreate_global_plot_task(engine, session_id)
        global_plot_task_owned_by_me = isinstance(effective_task_id, int)
    elif capability_id == "volume_plot_design":
        effective_task_id = _precreate_volume_plot_task(engine, session_id, parsed_volume_index)
        volume_task_owned_by_me = isinstance(effective_task_id, int)
    elif capability_id == "chapter_plot_design":
        effective_task_id = _precreate_chapter_plot_task(engine, session_id, parsed_volume_index)
        chapter_task_owned_by_me = isinstance(effective_task_id, int)
    elif capability_id == "chapter_events_design":
        effective_task_id = _precreate_chapter_events_task(engine, session_id, parsed_volume_index,
                                                           parsed_chapter_index)
        chapter_events_task_owned_by_me = isinstance(effective_task_id, int)
    elif capability_id == "chapter_content_generation":
        effective_task_id = _precreate_chapter_content_task(engine, session_id, parsed_volume_index,
                                                            parsed_chapter_index)
        chapter_content_task_owned_by_me = isinstance(effective_task_id, int)

    return effective_task_id, memory_task_owned_by_me, global_plot_task_owned_by_me, \
        volume_task_owned_by_me, chapter_task_owned_by_me, \
        chapter_events_task_owned_by_me, chapter_content_task_owned_by_me


# 空 section 的标识列表（格式：【标识】:\n 后面无内容时需要移除整个 section）
_EMPTY_SECTION_MARKERS = [
    "【上一卷剧情】",
    "【上一章剧情】",
    "【上一章事件链】",
]


def _clean_empty_sections(prompt: str) -> str:
    """清理 prompt 中空的可选 section，避免误导模型。

    判定逻辑：当 section 标识行（如【上一卷剧情】）本身无内联内容时，
    向前 peek 下一个非空行——若该行以【开头则说明已进入下一个 section，
    当前 section 确为空可安全移除；若该行不以【开头则是当前 section 的
    跨多行内容，必须保留标识行。
    """
    if not prompt:
        return prompt

    lines = prompt.split("\n")
    result_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        is_empty_section = False
        for marker in _EMPTY_SECTION_MARKERS:
            if stripped.startswith(marker):
                rest = stripped[len(marker):].strip().lstrip(":：").strip()
                if not rest:
                    has_content_next_line = False
                    peek = i + 1
                    while peek < len(lines) and not lines[peek].strip():
                        peek += 1
                    if peek < len(lines):
                        next_stripped = lines[peek].strip()
                        if not next_stripped.startswith("【"):
                            has_content_next_line = True
                    if not has_content_next_line:
                        is_empty_section = True
                        i += 1
                        while i < len(lines) and not lines[i].strip():
                            i += 1
                    break

        if not is_empty_section:
            result_lines.append(line)
            i += 1

    # 清理多余的连续空行（最多保留两个连续空行）
    cleaned = []
    consecutive_empty = 0
    for line in result_lines:
        if not line.strip():
            consecutive_empty += 1
            if consecutive_empty <= 2:
                cleaned.append(line)
        else:
            consecutive_empty = 0
            cleaned.append(line)

    return "\n".join(cleaned).strip()


def _prepare_and_render_prompt(
        session_id: str,
        capability_id: str,
        variables: Dict[str, Any],
        engine,
        compiled_prompt: str,
        summary: str,
        parsed_volume_index: int,
        parsed_chapter_index: int,
) -> Tuple[str, Dict[str, Any], str, str, Optional[int], Optional[int], Optional[int], Optional[int], Optional[int]]:
    effective_vars: Dict[str, Any] = dict(variables) if isinstance(variables, dict) else {}

    handler = CAPABILITY_HANDLERS.get(capability_id)
    prepare_func = handler["prepare_vars"] if handler else None

    last_volume_global_plot_ref = ""
    last_chapter_volume_plot_ref = ""
    last_chapter_volume_index = parsed_volume_index
    last_chapter_events_volume_index = parsed_volume_index
    last_chapter_events_chapter_index = parsed_chapter_index
    last_chapter_content_volume_index = parsed_volume_index
    last_chapter_content_chapter_index = parsed_chapter_index

    if prepare_func is not None:
        if capability_id == "global_plot_design":
            effective_vars, _ = prepare_func(session_id, variables, engine, summary)
        elif capability_id == "volume_plot_design":
            effective_vars, _, last_volume_global_plot_ref = prepare_func(session_id, variables, engine, summary)
        elif capability_id == "chapter_plot_design":
            effective_vars, _, last_chapter_volume_plot_ref, last_chapter_volume_index = prepare_func(
                session_id, variables, engine, summary, parsed_volume_index
            )
        elif capability_id == "chapter_events_design":
            effective_vars, _, last_chapter_events_volume_index, last_chapter_events_chapter_index = prepare_func(
                session_id, variables, engine, summary, parsed_volume_index, parsed_chapter_index
            )
        elif capability_id == "chapter_content_generation":
            effective_vars, _, last_chapter_content_volume_index, last_chapter_content_chapter_index = prepare_func(
                session_id, variables, engine, summary, parsed_volume_index, parsed_chapter_index
            )

    limited_vars = _apply_injection_limits(capability_id, effective_vars)
    inject_vars: Dict[str, Any] = {}
    for k, v in limited_vars.items():
        if isinstance(v, (list, tuple)):
            try:
                inject_vars[str(k)] = json.dumps(v, ensure_ascii=False)
            except Exception:
                inject_vars[str(k)] = "\n".join(
                    "" if x is None else str(x) for x in v
                )
        else:
            inject_vars[str(k)] = "" if v is None else str(v)

    escaped_template = _escape_static_braces_keep_vars(
        compiled_prompt, set(inject_vars.keys())
    )
    formatted_prompt = safe_format_prompt(escaped_template, **inject_vars)

    # 清理空的可选 section（如【上一卷剧情】后面无内容时移除整个 section）
    formatted_prompt = _clean_empty_sections(formatted_prompt)

    return (
        formatted_prompt,
        effective_vars,
        last_volume_global_plot_ref,
        last_chapter_volume_plot_ref,
        last_chapter_volume_index,
        last_chapter_events_volume_index,
        last_chapter_events_chapter_index,
        last_chapter_content_volume_index,
        last_chapter_content_chapter_index,
    )


async def _invoke_llm_and_get_response(
        cap: Dict[str, Any],
        registry: GlobalSingletonRegistry,
        formatted_prompt: str,
        session_id: str,
        capability_id: str,
        shared_executor=None,
        shared_expect_json: Optional[bool] = None,
) -> Any:
    if shared_executor is None or shared_expect_json is None:
        executor, expect_json = await _build_executor(cap, registry,
                                                      f"session_id={session_id!r}, capability_id={capability_id!r}, variables_keys=[]")
    else:
        executor, expect_json = shared_executor, shared_expect_json

    # 动态计算 max_tokens 基准值：取「基于输入长度的动态值」和「能力配置值」的较大者。
    # 动态值 = resolve_max_tokens(len(formatted_prompt))，使 FULL_TEXT_TOKENS_RATIO 生效；
    # 能力配置值作为下限保证，确保短文本能力也有足够空间。
    # 传入 executor 后，DeepSeek 推理扩容因子在此基准上乘以 MAX_TOKENS_EXPANSION_FACTOR。
    dynamic_max = resolve_max_tokens(len(formatted_prompt))
    cap_params = cap.get("params") if isinstance(cap.get("params"), dict) else {}
    cap_max_tokens = cap_params.get("max_tokens")
    extra_kwargs: Dict[str, Any] = {}
    if cap_max_tokens is not None:
        try:
            extra_kwargs[ke.KEY_MAX_TOKENS] = max(dynamic_max, int(cap_max_tokens))
        except (ValueError, TypeError):
            extra_kwargs[ke.KEY_MAX_TOKENS] = dynamic_max
    else:
        extra_kwargs[ke.KEY_MAX_TOKENS] = dynamic_max

    if expect_json:
        llm_resp = await executor.json(
            formatted_prompt,
            type_str=capability_id,
            prompt_id=f"{session_id}::{capability_id}",
            validator_func=validate_capability_output,
            **extra_kwargs,
        )
    else:
        llm_resp = await executor.text(
            formatted_prompt,
            type_str=capability_id,
            prompt_id=f"{session_id}::{capability_id}",
            **extra_kwargs,
        )

    return llm_resp


def _parse_response_and_write_logs(
        capability_id: str,
        llm_resp: Any,
        session_id: str,
        summary: str,
        engine,
        effective_task_id: Optional[int],
        formatted_prompt: str,
        variables: Dict[str, Any],
) -> Tuple[Any, int, int, List[str], Optional[str], Optional[str], Optional[str], Optional[str], Optional[str], Optional[str], Optional[List[str]], str, str, str]:
    resp_content = getattr(llm_resp, "content", None)

    handler = CAPABILITY_HANDLERS.get(capability_id)
    parse_func = handler["parse_response"] if handler else None

    last_plot_text: Optional[str] = None
    last_summary_text: Optional[str] = None
    last_volume_plot_text: Optional[str] = None
    last_volume_summary_text: Optional[str] = None
    last_chapter_plot_text: Optional[str] = None
    last_chapter_summary_text: Optional[str] = None
    last_chapter_events_list: Optional[List[str]] = None
    last_chapter_events_chapter_plot_ref: str = ""
    last_chapter_events_chapter_summary_ref: str = ""
    chapter_content_text: str = ""

    if parse_func is not None:
        if capability_id == "global_plot_design":
            last_plot_text, last_summary_text = parse_func(resp_content, summary)
        elif capability_id == "volume_plot_design":
            last_volume_plot_text, last_volume_summary_text = parse_func(resp_content, summary)
        elif capability_id == "chapter_plot_design":
            last_chapter_plot_text, last_chapter_summary_text = parse_func(resp_content, summary)
        elif capability_id == "chapter_events_design":
            last_chapter_events_list, last_chapter_events_chapter_plot_ref, last_chapter_events_chapter_summary_ref = parse_func(resp_content, variables,
                                                                                        summary)
        elif capability_id == "chapter_content_generation":
            chapter_content_text = parse_func(resp_content, llm_resp, summary)

    memories_created, dedup_memories = _write_session_memories(
        session_id, capability_id, resp_content, summary, engine
    )
    last_dedup_memories = list(dedup_memories) if dedup_memories is not None else []

    token_cost = _write_llm_log(
        session_id, capability_id, effective_task_id,
        formatted_prompt, resp_content, llm_resp, summary, engine
    )
    last_token_cost = int(token_cost or 0)

    return (
        resp_content,
        memories_created,
        last_token_cost,
        last_dedup_memories,
        last_plot_text,
        last_summary_text,
        last_volume_plot_text,
        last_volume_summary_text,
        last_chapter_plot_text,
        last_chapter_summary_text,
        last_chapter_events_list,
        last_chapter_events_chapter_plot_ref,
        last_chapter_events_chapter_summary_ref,
        chapter_content_text,
    )


def _build_result(
        capability_id: str,
        token_cost: int,
        session_id: str,
        memories_created: int,
        last_dedup_memories: Optional[List[str]],
        effective_task_id: Optional[int],
        last_plot_text: Optional[str],
        last_summary_text: Optional[str],
        last_volume_plot_text: Optional[str],
        last_volume_summary_text: Optional[str],
        last_volume_global_plot_ref: str,
        last_chapter_plot_text: Optional[str],
        last_chapter_summary_text: Optional[str],
        last_chapter_volume_plot_ref: str,
        last_chapter_volume_index: Optional[int],
        last_chapter_events_list: Optional[List[str]],
        last_chapter_events_chapter_plot_ref: str,
        last_chapter_events_chapter_summary_ref: str,
        last_chapter_events_volume_index: Optional[int],
        last_chapter_events_chapter_index: Optional[int],
        chapter_content_text: str,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ok": True,
        "session_id": session_id,
        "capability_id": capability_id,
        "token_cost": token_cost,
    }

    handler = CAPABILITY_HANDLERS.get(capability_id)
    build_result_func = handler["build_result"] if handler else None

    if build_result_func is not None:
        if capability_id == "extract_session_memory":
            result["result"] = build_result_func(
                capability_id, memories_created, last_dedup_memories, effective_task_id
            )
        elif capability_id == "global_plot_design":
            result["result"] = build_result_func(capability_id, last_plot_text, last_summary_text)
        elif capability_id == "volume_plot_design":
            result["result"] = build_result_func(capability_id, last_volume_plot_text, last_volume_summary_text, last_volume_global_plot_ref)
        elif capability_id == "chapter_plot_design":
            result["result"] = build_result_func(capability_id, last_chapter_plot_text, last_chapter_summary_text, last_chapter_volume_plot_ref,
                                                 last_chapter_volume_index)
        elif capability_id == "chapter_events_design":
            result["result"] = build_result_func(
                capability_id, last_chapter_events_list, last_chapter_events_chapter_plot_ref,
                last_chapter_events_volume_index, last_chapter_events_chapter_index
            )
        elif capability_id == "chapter_content_generation":
            result["result"] = build_result_func(capability_id, chapter_content_text)

    if isinstance(effective_task_id, int):
        result["task_id"] = int(effective_task_id)

    return result


def _finalize_task_on_success(
        capability_id: str,
        effective_task_id: Optional[int],
        success: bool,
        engine,
        session_id: str,
        token_cost: int,
        memory_task_owned_by_me: bool,
        global_plot_task_owned_by_me: bool,
        volume_task_owned_by_me: bool,
        chapter_task_owned_by_me: bool,
        chapter_events_task_owned_by_me: bool,
        chapter_content_task_owned_by_me: bool,
        last_dedup_memories: Optional[List[str]],
        last_plot_text: Optional[str],
        last_summary_text: Optional[str],
        last_volume_plot_text: Optional[str],
        last_volume_summary_text: Optional[str],
        last_volume_global_plot_ref: str,
        last_chapter_plot_text: Optional[str],
        last_chapter_summary_text: Optional[str],
        last_chapter_volume_plot_ref: str,
        last_chapter_volume_index: Optional[int],
        last_chapter_events_list: Optional[List[str]],
        last_chapter_events_chapter_plot_ref: str,
        last_chapter_events_chapter_summary_ref: str,
        last_chapter_events_volume_index: Optional[int],
        last_chapter_events_chapter_index: Optional[int],
        chapter_content_text: str,
        last_chapter_content_volume_index: Optional[int],
        last_chapter_content_chapter_index: Optional[int],
):
    if not isinstance(effective_task_id, int):
        return

    if capability_id == "extract_session_memory" and memory_task_owned_by_me:
        _finalize_extract_memory_task_safely(
            engine, session_id, capability_id, effective_task_id, success,
            list(last_dedup_memories) if last_dedup_memories else None, token_cost
        )
    elif capability_id == "global_plot_design" and global_plot_task_owned_by_me:
        _finalize_global_plot_task_safely(
            engine, session_id, capability_id, effective_task_id, success,
            last_plot_text, last_summary_text, token_cost
        )
    elif capability_id == "volume_plot_design" and volume_task_owned_by_me:
        _finalize_volume_plot_task_safely(
            engine, session_id, capability_id, effective_task_id, success,
            last_volume_plot_text, last_volume_summary_text, last_volume_global_plot_ref, token_cost
        )
    elif capability_id == "chapter_plot_design" and chapter_task_owned_by_me:
        _finalize_chapter_plot_task_safely(
            engine, session_id, capability_id, effective_task_id, success,
            last_chapter_plot_text, last_chapter_summary_text, last_chapter_volume_plot_ref,
            last_chapter_volume_index, token_cost
        )
    elif capability_id == "chapter_events_design" and chapter_events_task_owned_by_me:
        _finalize_chapter_events_task_safely(
            engine, session_id, capability_id, effective_task_id, success,
            list(last_chapter_events_list or []), last_chapter_events_chapter_plot_ref,
            last_chapter_events_chapter_summary_ref,
            last_chapter_events_volume_index, last_chapter_events_chapter_index, token_cost
        )
    elif capability_id == "chapter_content_generation" and chapter_content_task_owned_by_me:
        _finalize_chapter_content_task_safely(
            engine, session_id, capability_id, effective_task_id, success,
            chapter_content_text, last_chapter_content_volume_index,
            last_chapter_content_chapter_index, token_cost
        )
