import time
import traceback
from typing import Dict, Any, List, cast
from app.core.prompt.prompt_builder import PromptBuilder
from app.core.services.sse_manager import get_sse_manager
from app.core.validators.validator_adapter import validate_metacognition_rules
from app.utils.llm_utils import format_llm_error
from app.utils.logger import LoggerManager as logger
from app.core.collector.execution_context import ExecutionCollector
from app.core.engine.executor import LLMExecutor
from app.core.meta.state import MetacognitiveOptimizerState, TraceNode, AnalysisTurn
from app.core.meta.utils import _update_state, check_llm_budget, _append_trace, _create_empty_turn
from app.common import keys as ke
from app.common import values as va
from app.utils.prompt_util import safe_format_prompt


CHINESE_NAME = "元认知辩论"


async def _run_debate_analyzer(
        state: MetacognitiveOptimizerState,
        executor: LLMExecutor,
        collector: ExecutionCollector,
        plugin_id: str,
        role_name: str,
        caller_last_report: str,
        next_dest: str
) -> MetacognitiveOptimizerState:
    """
    通用辩论节点执行器。
    """
    updates: Dict[str, Any] = {}
    current_trace: List[TraceNode] = state.get(ke.KEY_EXECUTION_TRACE, [])  # type: ignore
    current_analysis_reports = state.get(ke.KEY_ANALYSIS_REPORTS, [])  # type: ignore
    node_id = None
    task_id = state.get(ke.KEY_ID) or ""  # type: ignore
    sse = get_sse_manager()

    msg = f"开始 {role_name} 视角分析。"
    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: role_name,
        ke.KEY_CONTENT: msg,
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_START}
    })

    # 确定节点 ID（用于轨迹记录）
    if role_name == va.VAL_RATIONAL_TYRANT:
        node_id = va.VAL_NODE_RATIONAL_SINGLE
    elif role_name == va.VAL_EMOTIONAL_VIRGIN_MARY:
        node_id = va.VAL_NODE_EMOTIONAL_SINGLE

    # ——— 预算校验 ———
    if not check_llm_budget(state, role_name):
        message = f"{role_name} | LLM 调用预算耗尽"
        updates[ke.KEY_MESSAGE] = message
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: role_name,
            ke.KEY_CONTENT: "调用次数已达上限，无法继续分析",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        empty_turn = _create_empty_turn(role_name, message)
        updates[ke.KEY_ANALYSIS_REPORTS] = current_analysis_reports + [empty_turn]
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED,
            next_status=va.VAL_STATUS_COMPLETED_BY_BUDGET,
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_COMPLETED_BY_BUDGET
        return _update_state(state, **updates)

    # ——— 配置获取 ———
    builder = PromptBuilder()
    cfg = builder.get_full_config(plugin_id, is_prompt=False)
    type_str = cfg[ke.KEY_TYPE]
    if not cfg:
        message = f"{role_name} | 配置缺失 ({plugin_id})"
        updates[ke.KEY_MESSAGE] = message
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: role_name,
            ke.KEY_CONTENT: "缺少必要插件配置，分析无法启动",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        empty_turn = _create_empty_turn(role_name, message)
        updates[ke.KEY_ANALYSIS_REPORTS] = current_analysis_reports + [empty_turn]
        new_trace = _append_trace(
            current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED,
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        return _update_state(state, **updates)

    # ——— 数据准备 ———
    current_calls = state.get(ke.KEY_LLM_CALLS_COUNT, 0)  # type: ignore

    # 当前文本
    current_data = state.get(ke.KEY_CURRENT_DATA, {})  # type: ignore
    current_text = current_data.get(ke.KEY_CONTENT, "") if isinstance(current_data, dict) else ""

    # 道之洞见（最后一条）
    dao_reports = state.get(ke.KEY_DAO_REPORTS, [])  # type: ignore
    dao_insight = dao_reports[-1][ke.KEY_CONTENT] if dao_reports else ""

    # 上帝之眼研判（最后一条）
    eye_reports = state.get(ke.KEY_EYE_REPORTS, [])  # type: ignore
    eye_insight = eye_reports[-1][ke.KEY_CONTENT] if eye_reports else ""

    # ——— Prompt 渲染 ———
    try:
        rendered_prompt = safe_format_prompt(
            template=cfg[ke.KEY_PROMPT_TEMPLATE],
            current_text=current_text,
            dao_insight=dao_insight,
            eye_insight=eye_insight,
            auxiliary_context=caller_last_report
        )
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: role_name,
            ke.KEY_CONTENT: "正在提交分析请求...",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_RUNNING}
        })
    except Exception as e:
        message = f"{role_name} | Prompt 渲染失败: {e}"
        updates[ke.KEY_MESSAGE] = message
        logger.exception(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: role_name,
            ke.KEY_CONTENT: "Prompt 模板配置有误，渲染失败",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        collector.errors.append({
            ke.KEY_KEY: plugin_id,
            ke.KEY_VALUE: message,
            ke.KEY_TRACEBACK: traceback.format_exc(),
        })
        empty_turn = _create_empty_turn(role_name, message)
        updates[ke.KEY_ANALYSIS_REPORTS] = current_analysis_reports + [empty_turn]
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED,
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        return _update_state(state, **updates)

    # ——— LLM 调用 ———
    try:
        response = await executor.json(
            prompt=rendered_prompt,
            prompt_id=plugin_id,
            type_str=type_str,
            params=cfg[ke.KEY_PARAMS],
            current_text=current_text,
            validator_func=validate_metacognition_rules,
        )
        await collector.record_step_data(response, type_str, plugin_id, rendered_prompt)
    except Exception as e:
        message = f"{role_name} | LLM 调度异常: {e}"
        updates[ke.KEY_MESSAGE] = message
        logger.exception(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: role_name,
            ke.KEY_CONTENT: "模型服务调用异常，请稍后重试",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        collector.errors.append({
            ke.KEY_KEY: plugin_id,
            ke.KEY_VALUE: message,
            ke.KEY_TRACEBACK: traceback.format_exc(),
        })
        empty_turn = _create_empty_turn(role_name, message)
        updates[ke.KEY_ANALYSIS_REPORTS] = current_analysis_reports + [empty_turn]
        updates[ke.KEY_LLM_CALLS_COUNT] = current_calls + 1
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED,
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        return _update_state(state, **updates)

    # ——— 响应处理 ———
    updates[ke.KEY_LLM_CALLS_COUNT] = current_calls + 1

    if not response.ok:
        error_detail = format_llm_error(response)
        message = f"{role_name} | API 调用失败: {error_detail}"
        updates[ke.KEY_MESSAGE] = message
        logger.warning(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: role_name,
            ke.KEY_CONTENT: "API 调用失败，分析未能完成",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        empty_turn = _create_empty_turn(role_name, message)
        updates[ke.KEY_ANALYSIS_REPORTS] = current_analysis_reports + [empty_turn]
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED,
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        return _update_state(state, **updates)

    if not response.valid:
        error_detail = format_llm_error(response)
        message = f"{role_name} | 数据校验失败: {error_detail}"
        updates[ke.KEY_MESSAGE] = message
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: role_name,
            ke.KEY_CONTENT: "数据校验失败，分析未能完成",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        empty_turn = _create_empty_turn(role_name, message)
        updates[ke.KEY_ANALYSIS_REPORTS] = current_analysis_reports + [empty_turn]
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED,
            next_status=va.VAL_STATUS_GOTO_DIVINE_EYE,
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_GOTO_DIVINE_EYE
        return _update_state(state, **updates)

    # ——— 解析有效响应 ———
    parsed = response.content.get(ke.KEY_ANALYSIS_TURN, {}) if isinstance(response.content, dict) else {}
    if not isinstance(parsed, dict) or ke.KEY_CONTENT not in parsed:
        message = f"{role_name} | 返回结构缺失必要字段"
        updates[ke.KEY_MESSAGE] = message
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: role_name,
            ke.KEY_CONTENT: "返回结构缺失必要字段，分析未能完成",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        empty_turn = _create_empty_turn(role_name, message)
        updates[ke.KEY_ANALYSIS_REPORTS] = current_analysis_reports + [empty_turn]
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED,
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        return _update_state(state, **updates)

    # ——— 构建分析记录 ———
    analysis_turn = cast(AnalysisTurn, {
        ke.KEY_TIMESTAMP: time.time(),
        ke.KEY_ROLE: role_name,
        ke.KEY_CONTENT: str(parsed.get(ke.KEY_CONTENT, "")),
        ke.KEY_CONFIDENCE: float(parsed.get(ke.KEY_CONFIDENCE, 0.0)),
        ke.KEY_PLUGIN_RESULT: None,
    })
    updates[ke.KEY_ANALYSIS_REPORTS] = current_analysis_reports + [analysis_turn]
    new_trace = _append_trace(
        trace=current_trace,
        node_id=node_id,
        node_status=va.VAL_STATUS_COMPLETED,
        next_status=next_dest
    )
    updates[ke.KEY_EXECUTION_TRACE] = new_trace

    message = f"{role_name} 发言完成 | 置信度: {analysis_turn[ke.KEY_CONFIDENCE]:.2f}"
    logger.info(message, module_name=CHINESE_NAME,)
    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_DAO,
        ke.KEY_CONTENT: f"分析完成，置信度 {analysis_turn[ke.KEY_CONFIDENCE]:.2f}",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
    })

    return _update_state(state, **updates)


# ==============================================================================
# 理性暴君
# ==============================================================================
async def rational_tyrant_analyze(state: MetacognitiveOptimizerState, executor: LLMExecutor,
                                   collector: ExecutionCollector,
                                   caller_last_report: str,
                                   next_dest: str) -> MetacognitiveOptimizerState:
    return await _run_debate_analyzer(
        state=state,
        executor=executor,
        collector=collector,
        plugin_id=va.VAL_INTERNAL_RATIONAL_TYRANT_ANALYSIS,
        role_name=va.VAL_RATIONAL_TYRANT,
        caller_last_report=caller_last_report,
        next_dest=next_dest
    )


# ==============================================================================
# 感性圣母
# ==============================================================================
async def emotional_mother_analyze(state: MetacognitiveOptimizerState, executor: LLMExecutor,
                                    collector: ExecutionCollector,
                                    caller_last_report: str,
                                    next_dest: str) -> MetacognitiveOptimizerState:
    return await _run_debate_analyzer(
        state=state,
        executor=executor,
        collector=collector,
        plugin_id=va.VAL_INTERNAL_EMOTIONAL_VIRGIN_MARY_ANALYSIS,
        role_name=va.VAL_EMOTIONAL_VIRGIN_MARY,
        caller_last_report=caller_last_report,
        next_dest=next_dest
    )
