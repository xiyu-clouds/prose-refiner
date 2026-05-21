"""
上帝之眼（看全局）+ 上帝之手（做决策）+ 双角色辩论（提视角）+ 插件验证（查事实）+ 安全兜底（保稳定）+ 全链路持久化（可追溯）
"""

import json
from typing import List, Dict, Any, Optional, Callable, Awaitable, Tuple
from datetime import datetime, timezone
from typing import cast
from app.config.config import config
from app.core.collector.execution_context import ExecutionCollector
from app.core.engine.executor import LLMExecutor
from app.core.meta.state import MetacognitiveOptimizerState, DataPayload, TraceNode, DivineEyeInsight, \
    DivineHandVerdict, AnalysisTurn, DaoInsightRecord
from app.common import keys as ke
from app.common import enums as en
from app.common import values as va
from app.core.prompt.prompt_builder import PromptBuilder
from app.db.memory_db import MemoryPhaseDB
from app.utils.logger import LoggerManager as logger

CHINESE_NAME = "元认知工具"


def _update_state(
        state: MetacognitiveOptimizerState,
        *,
        current_data: Optional[DataPayload] = None,
        execution_trace: Optional[List[TraceNode]] = None,
        eye_reports: Optional[List[DivineEyeInsight]] = None,
        hand_reports: Optional[List[DivineHandVerdict]] = None,
        analysis_reports: Optional[List[AnalysisTurn]] = None,
        dao_reports: Optional[List[DaoInsightRecord]] = None,
        llm_calls_count: Optional[int] = None,
        max_chars_per_turn: Optional[int] = None,
        max_debate_turns_to_inject: Optional[int] = None,
        max_issues_to_display: Optional[int] = None,
        user_clarification: Optional[str] = None,
        status: Optional[str] = None,
        message: Optional[str] = None,
        metacognition_signature: Optional[str] = None,
        revised_text: Optional[str] = None,
        revision_fix_records: Optional[List[Dict[str, Any]]] = None
) -> MetacognitiveOptimizerState:
    """
    不可变状态更新器。
    仅开放可变字段的更新入口，保护 id、initial_snapshot 等核心元数据不被意外修改。
    所有引用类型参数均做浅拷贝，防止外部引用污染状态内部数据。
    """
    if ke.KEY_ID not in state:
        raise ValueError(f"状态非法：缺失必要字段 '{ke.KEY_ID}'")

    updates: Dict[str, Any] = {}
    changed_fields: List[str] = []

    # —— 引用类型：浅拷贝后写入 ——
    if current_data is not None:
        updates[ke.KEY_CURRENT_DATA] = dict(current_data)
        changed_fields.append(ke.KEY_CURRENT_DATA)

    if execution_trace is not None:
        updates[ke.KEY_EXECUTION_TRACE] = list(execution_trace)
        changed_fields.append(ke.KEY_EXECUTION_TRACE)

    if eye_reports is not None:
        updates[ke.KEY_EYE_REPORTS] = list(eye_reports)
        changed_fields.append(ke.KEY_EYE_REPORTS)

    if hand_reports is not None:
        updates[ke.KEY_HAND_REPORTS] = list(hand_reports)
        changed_fields.append(ke.KEY_HAND_REPORTS)

    if analysis_reports is not None:
        updates[ke.KEY_ANALYSIS_REPORTS] = list(analysis_reports)
        changed_fields.append(ke.KEY_ANALYSIS_REPORTS)

    if dao_reports is not None:
        updates[ke.KEY_DAO_REPORTS] = list(dao_reports)
        changed_fields.append(ke.KEY_DAO_REPORTS)

    if revision_fix_records is not None:
        updates[ke.KEY_REVISION_FIX_RECORDS] = list(revision_fix_records)
        changed_fields.append(ke.KEY_REVISION_FIX_RECORDS)

    # —— 整数类型：合法性校验后写入 ——
    if llm_calls_count is not None:
        updates[ke.KEY_LLM_CALLS_COUNT] = max(0, int(llm_calls_count))
        changed_fields.append(ke.KEY_LLM_CALLS_COUNT)

    if max_chars_per_turn is not None:
        updates[ke.KEY_MAX_CHARS_PER_TURN] = max(1500, int(max_chars_per_turn))
        changed_fields.append(ke.KEY_MAX_CHARS_PER_TURN)

    if max_debate_turns_to_inject is not None:
        updates[ke.KEY_MAX_DEBATE_TURNS_TO_INJECT] = max(2, int(max_debate_turns_to_inject))
        changed_fields.append(ke.KEY_MAX_DEBATE_TURNS_TO_INJECT)

    if max_issues_to_display is not None:
        updates[ke.KEY_MAX_ISSUES_TO_DISPLAY] = max(1, int(max_issues_to_display))
        changed_fields.append(ke.KEY_MAX_ISSUES_TO_DISPLAY)

    # —— 字符串类型：空值清理后写入 ——
    if user_clarification is not None:
        cleaned = str(user_clarification).strip()
        updates[ke.KEY_USER_CLARIFICATION] = cleaned if cleaned else None
        changed_fields.append(ke.KEY_USER_CLARIFICATION)

    if status is not None:
        updates[ke.KEY_STATUS] = str(status).strip()
        changed_fields.append(ke.KEY_STATUS)

    if message is not None:
        updates[ke.KEY_MESSAGE] = str(message).strip()
        changed_fields.append(ke.KEY_MESSAGE)

    if metacognition_signature is not None:
        cleaned = str(metacognition_signature).strip()
        updates[ke.KEY_METACOGNITION_SIGNATURE] = cleaned if cleaned else None
        changed_fields.append(ke.KEY_METACOGNITION_SIGNATURE)

    if revised_text is not None:
        updates[ke.KEY_REVISED_TEXT] = str(revised_text)
        changed_fields.append(ke.KEY_REVISED_TEXT)

    # —— 记录变更日志 ——
    if changed_fields:
        task_id = state[ke.KEY_ID]  # type: ignore
        logger.debug(
            f"状态更新 | 任务: {task_id} | 变更: {', '.join(changed_fields)}",
            module_name=CHINESE_NAME,
        )

    return cast(MetacognitiveOptimizerState, {**state, **updates})


def deep_merge(base: dict, patch: dict) -> dict:
    """递归合并 patch 到 base，支持 null 删除字段"""
    result = base.copy()
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _create_empty_turn(role: str, reason: str) -> AnalysisTurn:
    """创建空的辩论轮次占位符，用于异常降级或跳过场景"""
    return cast(AnalysisTurn, {
        ke.KEY_TIMESTAMP: datetime.now(timezone.utc).timestamp(),
        ke.KEY_ROLE: role,
        ke.KEY_CONTENT: f"({reason})",
        ke.KEY_CONFIDENCE: 0.0,
        ke.KEY_PLUGIN_RESULT: None,
    })


def _create_empty_hand(reason: str) -> DivineHandVerdict:
    """创建空的上帝之手裁决占位符，用于异常降级或资源耗尽场景"""
    return cast(DivineHandVerdict, {
        ke.KEY_TIMESTAMP: datetime.now(timezone.utc).timestamp(),
        ke.KEY_DECISION: en.DecisionType.ACCEPT_CURRENT,
        ke.KEY_CONTENT: reason,
        ke.KEY_PRIORITY_ISSUES: [],
        ke.KEY_CONFIDENCE: 0.0,
    })


def _create_empty_eye(reason: str) -> DivineEyeInsight:
    """创建空的上帝之眼觉知占位符，用于异常降级场景"""
    return cast(DivineEyeInsight, {
        ke.KEY_TIMESTAMP: datetime.now(timezone.utc).timestamp(),
        ke.KEY_STRATEGY: en.StrategyCode.TERMINATE_TRIVIAL,
        ke.KEY_CONTENT: reason,
        ke.KEY_CONFIDENCE: 0.0,
        ke.KEY_REQUESTED_LEVEL: 0,
        ke.KEY_ABORT_RECOMMENDATION: True,
        ke.KEY_ABORT_REASON: reason,
    })


def _create_empty_dao(caller: str, reason: str) -> DaoInsightRecord:
    """创建空的道操作记录占位符，用于道调用失败或跳过场景"""
    return cast(DaoInsightRecord, {
        ke.KEY_TIMESTAMP: datetime.now(timezone.utc).timestamp(),
        ke.KEY_CALLER: caller,
        ke.KEY_CONTENT: f"({reason})",
        ke.KEY_CONFIDENCE: 0.0,
    })


def _filter_valid_focus_areas(candidate_areas: List[en.FocusArea]) -> List[en.FocusArea]:
    """
    过滤并验证聚焦领域列表。
    """
    if not candidate_areas:
        return []

    valid_areas = [
        cast(en.FocusArea, area)
        for area in candidate_areas
        if area in en.VAL_VALID_FOCUS_AREA
    ]
    return valid_areas


def _get_active_focus_areas(state: MetacognitiveOptimizerState) -> List[en.FocusArea]:
    """获取当前战略聚焦领域"""
    reports = state.get(ke.KEY_EYE_REPORTS, [])  # type: ignore
    default_areas = [en.FocusArea.BALANCE]
    if not reports:
        return default_areas

    last_report = reports[-1]

    strategic_code: Optional[en.StrategyCode] = last_report.get(ke.KEY_STRATEGY)
    if not strategic_code:
        return default_areas

    if strategic_code in en.VAL_STRATEGY_CONFIGS:
        cfg = en.VAL_STRATEGY_CONFIGS[strategic_code]
        focus_areas = cfg.get(ke.KEY_FOCUS_AREAS, [])  # type: ignore
        filtered_areas = _filter_valid_focus_areas(focus_areas)
        if filtered_areas:
            return filtered_areas

        logger.warning(f"⚠️ 战略配置异常：'{strategic_code}' 的 {ke.KEY_FOCUS_AREAS} 存在非法值，已降级为默认平衡模式。",
                       module_name=CHINESE_NAME)
    return default_areas


def _is_plugin_enabled_and_valid(plugin_id: str, plugin_type: str) -> bool:
    if not isinstance(plugin_id, str):
        return False

    try:
        prompt_builder = PromptBuilder()
        valid_ids = prompt_builder.get_ids_by_type(plugin_type, False)
        return plugin_id in valid_ids
    except Exception:
        return False


def _format_plugin_report(
        plugin_result: Optional[Dict[str, Any]],
        max_chars: int,
) -> str:
    """格式化插件验证报告，超出限制自动截断"""
    if not plugin_result or not isinstance(plugin_result, dict):
        return ""

    lines: List[str] = []
    for pid, raw_content in plugin_result.items():
        if not raw_content:
            continue
        content_str = (
            json.dumps(raw_content, ensure_ascii=False, indent=2)
            if isinstance(raw_content, dict)
            else str(raw_content)
        )
        if len(content_str) > max_chars:
            content_str = (
                    content_str[:max_chars]
                    + f"\n... [已截断，剩余 {len(content_str) - max_chars} 字符]"
            )
        lines.append(f"### 插件 [{pid}] 查证结果:\n{content_str}")

    return "\n\n".join(lines) if lines else ""


def _format_analysis_report_md(
        state: MetacognitiveOptimizerState,
        fallback_message: str = "暂无辩论记录",
) -> str:
    """格式化辩论发言记录，注入指定轮次并附加各视角插件验证报告"""
    analysis_reports = state.get(ke.KEY_ANALYSIS_REPORTS, [])  # type: ignore
    if not analysis_reports:
        return fallback_message

    max_turns = state.get(ke.KEY_MAX_DEBATE_TURNS_TO_INJECT, 2)  # type: ignore
    max_chars = state.get(ke.KEY_MAX_CHARS_PER_TURN, 800)  # type: ignore

    log_lines: List[str] = []
    for turn in analysis_reports[-max_turns:]:
        role = turn.get(ke.KEY_ROLE, "未知")
        content = turn.get(ke.KEY_CONTENT, "")
        log_lines.append(f"[{role}] {content}")

        plugin_report = _format_plugin_report(
            turn.get(ke.KEY_PLUGIN_RESULT), max_chars
        )
        if plugin_report:
            log_lines.append(f"\n{plugin_report}")

    return "### 辩论实录\n" + "\n\n".join(log_lines)


def _format_eye_report_md(state: MetacognitiveOptimizerState) -> str:
    """格式化上帝之眼最新觉知报告"""
    reports = state.get(ke.KEY_EYE_REPORTS, [])  # type: ignore
    if not reports:
        return "暂无上帝之眼战略报告，请基于现有上下文独立判断。"

    last = reports[-1]
    strategy_code = last.get(ke.KEY_STRATEGY, "")
    cfg = VAL_STRATEGY_CONFIGS.get(strategy_code, {})  # type: ignore
    strategy_desc = cfg.get(ke.KEY_DESCRIPTION, "")

    parts: List[str] = []
    strategy_text = f"{strategy_code}: {strategy_desc}" if strategy_desc else str(strategy_code)
    parts.append(f"- **建议战略**: `{strategy_text}`")

    raw_areas = cfg.get(ke.KEY_FOCUS_AREAS, [])
    valid_areas = _filter_valid_focus_areas(raw_areas)
    if valid_areas:
        area_texts = [
            f"{area}: {desc}"
            for area in valid_areas
            if (desc := va.VAL_FOCUS_AREA_DEFINITIONS.get(area))
        ]
        if area_texts:
            parts.append(f"- **战略聚焦**: {'; '.join(area_texts)}")

    if last.get(ke.KEY_ABORT_RECOMMENDATION):
        reason = last.get(ke.KEY_ABORT_REASON)
        if reason:
            parts.append(f"- **终止建议**: 是 ({reason})")

    parts.append(f"- **觉知概要**:\n{last[ke.KEY_CONTENT]}")
    return "\n".join(parts)


def _format_hand_report_md(state: MetacognitiveOptimizerState) -> str:
    """格式化上帝之手最新裁决报告"""
    reports = state.get(ke.KEY_HAND_REPORTS, [])  # type: ignore
    if not reports:
        return "暂无上帝之手裁决记录，请基于当前态势自主推演。"

    last = reports[-1]
    decision_code = last.get(ke.KEY_DECISION, "")
    cfg = en.VAL_DECISION_CONFIGS.get(decision_code, {})
    description = cfg.get(ke.KEY_DESCRIPTION, "")

    parts: List[str] = []
    dec_text = f"{decision_code}: {description}" if description else str(decision_code)
    parts.append(f"- **裁决方向**: `{dec_text}`")
    parts.append(f"- **裁决依据**: {last[ke.KEY_CONTENT]}")

    priority_issues = last.get(ke.KEY_PRIORITY_ISSUES, [])
    if priority_issues:
        max_issues = state.get(ke.KEY_MAX_ISSUES_TO_DISPLAY, 5)  # type: ignore
        parts.append(f"- **问题清单**: {len(priority_issues)} 项待修复")
        for issue in priority_issues[:max_issues]:
            parts.append(
                f"  - [{issue.get(ke.KEY_PRIORITY, '?')}] "
                f"{issue.get(ke.KEY_CATEGORY, '')}: "
                f"{issue.get(ke.KEY_ISSUE, '')}"
            )

    return "\n".join(parts)


def _format_dao_report_md(state: MetacognitiveOptimizerState) -> str:
    """格式化道节点最新直觉报告"""
    reports = state.get(ke.KEY_DAO_REPORTS, [])  # type: ignore
    if not reports:
        return "暂无道之洞见记录，请基于现有上下文独立判断。"

    last = reports[-1]
    return f"- **道之洞见**: {last[ke.KEY_CONTENT]}"


def check_llm_budget(state: MetacognitiveOptimizerState, node_name: str, reserved: int = 2) -> bool:
    """
    检查 LLM 预算。
    Returns:
        True: 预算充足，可以继续执行。
        False: 预算耗尽，记录日志。调用者需立即执行 fallback 逻辑并返回。
    """
    current_calls = state.get(ke.KEY_LLM_CALLS_COUNT, 0)  # type: ignore
    max_budget = state.get(ke.KEY_MAX_LLM_CALLS, 30)  # type: ignore
    budget = max_budget - reserved

    if current_calls >= budget:
        logger.warning(
            f"⛔ [{node_name}] 预算耗尽 (已用:{current_calls}/{max_budget}, "
            f"其中为语义签名预留{reserved}次, 实际可用前序预算:{budget})。触发资源终止。",
            module_name=CHINESE_NAME
        )
        return False

    return True


def _append_trace(
        trace: List[TraceNode],
        node_id: str,
        node_status: en.NodeStatusLiteral,
        next_status: str,
) -> List[TraceNode]:
    """构建并追加一条轨迹节点，返回新轨迹列表。"""
    seq_id = len(trace) + 1
    next_node_id = en.VAL_STATUS_TO_NODE_MAP.get(next_status)
    prev_node_id = trace[-1][ke.KEY_NODE_ID] if trace else ke.KEY_UP_INIT  # type: ignore
    trace_node = {
        ke.KEY_SEQ_ID: seq_id,
        ke.KEY_NODE_ID: node_id,
        ke.KEY_NEXT_NODE_ID: next_node_id,
        ke.KEY_STATUS: node_status,
        ke.KEY_PREV_NODE_ID: prev_node_id
    }
    return trace + [trace_node]


def _build_trace_node(
        trace: List[TraceNode],
        node_id: str,
        node_status: en.NodeStatusLiteral,
        next_node_id: str
):
    seq_id = len(trace) + 1
    prev_node_id = trace[-1][ke.KEY_NODE_ID] if trace else None  # type: ignore
    trace_node = {
        ke.KEY_SEQ_ID: seq_id,
        ke.KEY_NODE_ID: node_id,
        ke.KEY_NEXT_NODE_ID: next_node_id,
        ke.KEY_STATUS: node_status,
        ke.KEY_PREV_NODE_ID: prev_node_id,
    }
    return trace + [trace_node]


def fix_trace_next_node_ids(trace: List[TraceNode]) -> List[TraceNode]:
    """
    因为 trace 记录时用了静态意图，没有反映实际路由结果，
    根据实际的执行顺序，修正每条记录的 next_node_id。
    """
    if not trace:
        return trace

    # 构建 seq_id -> 实际下一节点 node_id 的映射
    seq_to_next_node = {}
    for i, current in enumerate(trace):
        if i + 1 < len(trace):
            next_node_id = trace[i + 1][ke.KEY_NODE_ID]  # type: ignore
        else:
            # 最后一条，根据状态或约定设为 "END" 或保持原值
            next_node_id = ke.KEY_UP_END
        seq_to_next_node[current[ke.KEY_SEQ_ID]] = next_node_id  # type: ignore

    # 复制并修正
    fixed = []
    for item in trace:
        new_item = item.copy()
        correct_next = seq_to_next_node.get(item[ke.KEY_SEQ_ID])  # type: ignore
        if correct_next is not None:
            new_item[ke.KEY_NEXT_NODE_ID] = correct_next
        fixed.append(new_item)
    return fixed


def get_last_report_content(state: MetacognitiveOptimizerState, caller: str) -> str:
    """获取指定节点最近一份报告的 content，无记录则返回空字符串"""
    list_key = va.VAL_CALLER_REPORT_KEY_MAP.get(caller)
    if not list_key:
        return ""
    reports = state.get(list_key, [])  # type: ignore
    if not reports:
        return ""
    # 辩论角色需额外过滤：只取自己的发言
    if caller in (va.VAL_RATIONAL_TYRANT, va.VAL_EMOTIONAL_VIRGIN_MARY):
        reports = [r for r in reports if r.get(ke.KEY_ROLE) == caller]
        if not reports:
            return ""
    return reports[-1].get(ke.KEY_CONTENT, "")


async def process_data_granularity(
        task_id: str,
        requested_level: int,
        current_level: int,
        data_store: Dict[int, str]
) -> Tuple[Dict[int, str], str, int]:
    """
    增量加载数据层级，管理缓存，处理增量标记的添加与清理。

    1. 加载缺失层级 (current_level 到 requested_level)
    2. 已加载过的层级直接复用缓存
    3. 新增内容前清理旧标记，避免重复
    """
    db = MemoryPhaseDB.get_instance(config.DB_PATH)
    store = {int(k): v for k, v in data_store.items()}

    full_data = await db.get_text_processing_data(task_id)
    if not full_data:
        return store, "", current_level

    level_fetchers: Dict[int, Any] = {
        0: db.fetch_level_0_content,
        1: db.fetch_level_1_content,
        2: db.fetch_level_2_content
    }

    for lvl in range(current_level, requested_level + 1):
        if lvl not in store or not store[lvl]:
            fetcher = level_fetchers.get(lvl)
            if fetcher is not None:
                store[lvl] = await fetcher(full_data)

    NEW_DATA_MARKER = "[补充数据]"

    parts = []
    # 隐式背景
    background = [store[l] for l in range(current_level + 1) if l in store and store[l]]
    if background:
        parts.append("\n".join(background))

    # 显式新增
    if requested_level > current_level:
        new_parts = [store[l] for l in range(current_level + 1, requested_level + 1) if l in store and store[l]]
        if new_parts:
            joined = "\n".join(new_parts)
            # 清理旧标记
            joined = joined.replace(NEW_DATA_MARKER, "")
            parts.append(f"{NEW_DATA_MARKER}\n{joined}")

    final_content = "\n\n".join(parts) if parts else ""
    return store, final_content, requested_level


def convert_int_keys_to_str(d):
    """递归地将字典中的整数键转换为字符串键"""
    if isinstance(d, dict):
        return {str(k): convert_int_keys_to_str(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [convert_int_keys_to_str(item) for item in d]
    return d


# ==============================================================================
# 通用异步节点工厂 (Universal Async Node Factory)
# ==============================================================================
def make_async_node(
        async_func: Callable[
            [MetacognitiveOptimizerState, LLMExecutor, ExecutionCollector], Awaitable[MetacognitiveOptimizerState]],
        executor: LLMExecutor,
        collector: ExecutionCollector
) -> Callable[[MetacognitiveOptimizerState], Awaitable[MetacognitiveOptimizerState]]:
    async def node_runner(state: MetacognitiveOptimizerState) -> MetacognitiveOptimizerState:
        return await async_func(state, executor, collector)

    return node_runner


def make_async_node_no_args(
        async_func: Callable[[MetacognitiveOptimizerState], Awaitable[MetacognitiveOptimizerState]]
) -> Callable[[MetacognitiveOptimizerState], Awaitable[MetacognitiveOptimizerState]]:
    async def node_runner(state: MetacognitiveOptimizerState) -> MetacognitiveOptimizerState:
        return await async_func(state)

    return node_runner


def make_async_node_with_dao(
        async_func: Callable[
            [MetacognitiveOptimizerState, LLMExecutor, ExecutionCollector, str, str], Awaitable[
                MetacognitiveOptimizerState]],
        executor: LLMExecutor,
        collector: ExecutionCollector,
        caller: str,
        internal_next_dest: Optional[str] = None
) -> Callable[[MetacognitiveOptimizerState], Awaitable[MetacognitiveOptimizerState]]:
    """
    包装需要道注入的智能节点。
    在执行原节点逻辑前，自动调用 dao_node 并传入 caller 标识。
    """

    async def wrapped(state: MetacognitiveOptimizerState) -> MetacognitiveOptimizerState:
        # 调用道节点，注入当前节点标识
        caller_last_report = get_last_report_content(state, caller)
        dao_last_insight = get_last_report_content(state, va.VAL_DAO)
        from app.core.meta.nodes.dao import dao_node
        state = await dao_node(state, executor, collector, caller, caller_last_report, dao_last_insight)
        # 决定 next_dest：优先用内部流转目标；否则查兜底映射；都兜不住就上帝之眼
        if internal_next_dest:
            next_dest = internal_next_dest
        else:
            next_dest = va.VAL_DEFAULT_NEXT_DEST_MAP.get(caller, va.VAL_STATUS_GOTO_DIVINE_EYE)

        return await async_func(state, executor, collector, caller_last_report, next_dest)

    return wrapped
