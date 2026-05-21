import time
import traceback
from typing import Dict, Any, cast
from app.common.enums import get_status_from_node
from app.core.collector.execution_context import ExecutionCollector
from app.core.engine.executor import LLMExecutor
from app.core.meta.state import MetacognitiveOptimizerState, DivineHandVerdict
from app.core.meta.utils import (
    _update_state,
    check_llm_budget,
    _create_empty_hand,
    _append_trace,
    _format_analysis_report_md,
)
from app.common import keys as ke
from app.common import enums as en
from app.common import values as va
from app.core.prompt.prompt_builder import PromptBuilder
from app.core.services.sse_manager import get_sse_manager
from app.core.validators.validator_adapter import validate_metacognition_rules
from app.utils.llm_utils import format_llm_error
from app.utils.logger import LoggerManager as logger
from app.utils.prompt_util import safe_format_prompt


CHINESE_NAME = "上帝之手"


async def divine_hand_node(
        state: MetacognitiveOptimizerState,
        executor: LLMExecutor,
        collector: ExecutionCollector,
        caller_last_report: str,
        next_dest: str
) -> MetacognitiveOptimizerState:
    # ——— 前置属性（全节点复用）———
    updates: Dict[str, Any] = {}
    current_trace = state.get(ke.KEY_EXECUTION_TRACE, [])  # type: ignore
    current_hand_reports = state.get(ke.KEY_HAND_REPORTS, [])  # type: ignore
    node_id = va.VAL_NODE_DIVINE_HAND
    task_id = state.get(ke.KEY_ID) or ""  # type: ignore
    sse = get_sse_manager()

    message = f"{va.VAL_HAND_OF_GOD} 节点被调用。"
    logger.debug(message, module_name=CHINESE_NAME)
    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_HAND_OF_GOD,
        ke.KEY_CONTENT: "开始综合裁决当前文本状态",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_START}
    })

    # ——— 预算校验 ———
    if not check_llm_budget(state, va.VAL_HAND_OF_GOD):
        message = f"{va.VAL_HAND_OF_GOD} | LLM 调用预算耗尽"
        updates[ke.KEY_MESSAGE] = message
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_HAND_OF_GOD,
            ke.KEY_CONTENT: "调用次数已达上限，无法进行裁决",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        empty_hand = _create_empty_hand(message)
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED,
            next_status=va.VAL_STATUS_COMPLETED_BY_BUDGET,
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_HAND_REPORTS] = current_hand_reports + [empty_hand]
        updates[ke.KEY_STATUS] = va.VAL_STATUS_COMPLETED_BY_BUDGET
        return _update_state(state, **updates)

    # ——— 配置获取 ———
    builder = PromptBuilder()
    hand_cfg = builder.get_full_config(va.VAL_INTERNAL_DIVINE_HAND_VERDICT, is_prompt=False)
    if not hand_cfg:
        message = f"{va.VAL_HAND_OF_GOD} | 配置缺失 ({va.VAL_INTERNAL_DIVINE_HAND_VERDICT})"
        updates[ke.KEY_MESSAGE] = message
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_HAND_OF_GOD,
            ke.KEY_CONTENT: "缺少必要插件配置，分析无法启动",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        empty_hand = _create_empty_hand(message)
        new_trace = _append_trace(
            current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED,
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_HAND_REPORTS] = current_hand_reports + [empty_hand]
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        return _update_state(state, **updates)

    # ——— 数据准备 ———
    current_calls = state.get(ke.KEY_LLM_CALLS_COUNT, 0)  # type: ignore

    # 道之洞见
    dao_reports = state.get(ke.KEY_DAO_REPORTS, [])  # type: ignore
    dao_insight = dao_reports[-1][ke.KEY_CONTENT] if dao_reports else ""

    # 上帝之眼研判
    eye_reports = state.get(ke.KEY_EYE_REPORTS, [])  # type: ignore
    eye_insight = eye_reports[-1][ke.KEY_CONTENT] if eye_reports else ""

    # 辩论记录
    debate_context = _format_analysis_report_md(state)

    plugin_id = hand_cfg[ke.KEY_ID]
    type_str = hand_cfg[ke.KEY_TYPE]

    current_data = state.get(ke.KEY_CURRENT_DATA, {})  # type: ignore
    current_text = current_data.get(ke.KEY_CONTENT, "") if isinstance(current_data, dict) else ""

    # ——— Prompt 渲染 ———
    try:
        rendered_prompt = safe_format_prompt(
            template=hand_cfg[ke.KEY_PROMPT_TEMPLATE],
            dao_insight=dao_insight,
            eye_insight=eye_insight,
            debate_context=debate_context,
            auxiliary_context=caller_last_report,
        )
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_HAND_OF_GOD,
            ke.KEY_CONTENT: "正在提交分析请求...",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_RUNNING}
        })
    except Exception as e:
        message = f"{va.VAL_HAND_OF_GOD} | Prompt 渲染失败: {e}"
        updates[ke.KEY_MESSAGE] = message
        logger.exception(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_HAND_OF_GOD,
            ke.KEY_CONTENT: "Prompt 模板配置有误，渲染失败",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        collector.errors.append({
            ke.KEY_KEY: plugin_id,
            ke.KEY_VALUE: message,
            ke.KEY_TRACEBACK: traceback.format_exc(),
        })
        empty_hand = _create_empty_hand(message)
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED,
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_HAND_REPORTS] = current_hand_reports + [empty_hand]
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        return _update_state(state, **updates)

    # ——— LLM 调用 ———
    try:
        response = await executor.json(
            prompt=rendered_prompt,
            prompt_id=plugin_id,
            type_str=type_str,
            params=hand_cfg[ke.KEY_PARAMS],
            current_text=current_text,
            validator_func=validate_metacognition_rules,
        )
        await collector.record_step_data(response, type_str, plugin_id, rendered_prompt)
    except Exception as e:
        message = f"{va.VAL_HAND_OF_GOD} | LLM 调度异常: {e}"
        updates[ke.KEY_MESSAGE] = message
        logger.exception(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_HAND_OF_GOD,
            ke.KEY_CONTENT: "模型服务调用异常，请稍后重试",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        collector.errors.append({
            ke.KEY_KEY: plugin_id,
            ke.KEY_VALUE: message,
            ke.KEY_TRACEBACK: traceback.format_exc(),
        })
        empty_hand = _create_empty_hand(message)
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED,
            next_status=va.VAL_STATUS_GOTO_DIVINE_EYE,
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_HAND_REPORTS] = current_hand_reports + [empty_hand]
        updates[ke.KEY_STATUS] = va.VAL_STATUS_GOTO_DIVINE_EYE
        return _update_state(state, **updates)

    # ——— 响应处理 ———
    updates[ke.KEY_LLM_CALLS_COUNT] = current_calls + 1

    if not response.ok:
        error_detail = format_llm_error(response)
        message = f"{va.VAL_HAND_OF_GOD} | API 调用失败: {error_detail}"
        updates[ke.KEY_MESSAGE] = message
        logger.warning(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_HAND_OF_GOD,
            ke.KEY_CONTENT: "API 调用失败，分析未能完成",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        empty_hand = _create_empty_hand(message)
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED,
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_HAND_REPORTS] = current_hand_reports + [empty_hand]
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        return _update_state(state, **updates)

    if not response.valid:
        error_detail = format_llm_error(response)
        message = f"{va.VAL_HAND_OF_GOD} | 数据校验失败: {error_detail}"
        updates[ke.KEY_MESSAGE] = message
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_HAND_OF_GOD,
            ke.KEY_CONTENT: "数据校验失败，分析未能完成",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        empty_hand = _create_empty_hand(message)
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED,
            next_status=va.VAL_STATUS_GOTO_DIVINE_EYE,
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_HAND_REPORTS] = current_hand_reports + [empty_hand]
        updates[ke.KEY_STATUS] = va.VAL_STATUS_GOTO_DIVINE_EYE
        return _update_state(state, **updates)

    # ——— 解析有效响应 ———
    parsed = response.content.get(ke.KEY_DIVINE_HAND, {}) if isinstance(response.content, dict) else {}
    if not isinstance(parsed, dict) or ke.KEY_DECISION not in parsed:
        message = f"{va.VAL_HAND_OF_GOD} | 返回结构缺失必要字段"
        updates[ke.KEY_MESSAGE] = message
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_HAND_OF_GOD,
            ke.KEY_CONTENT: "返回结构缺失必要字段，分析未能完成",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        empty_hand = _create_empty_hand(message)
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED,
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_HAND_REPORTS] = current_hand_reports + [empty_hand]
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        return _update_state(state, **updates)

    # 提取并校验决策代码
    raw_decision = parsed.get(ke.KEY_DECISION)
    decision_code = raw_decision.strip() if isinstance(raw_decision, str) else ""

    if decision_code not in en.VAL_VALID_DECISIONS:
        message = f"{va.VAL_HAND_OF_GOD} | 无效决策码: {decision_code}"
        updates[ke.KEY_MESSAGE] = message
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_HAND_OF_GOD,
            ke.KEY_CONTENT: "返回无效决策码，分析未能完成",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        empty_hand = _create_empty_hand(message)
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED,
            next_status=va.VAL_STATUS_GOTO_DIVINE_EYE,
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_HAND_REPORTS] = current_hand_reports + [empty_hand]
        updates[ke.KEY_STATUS] = va.VAL_STATUS_GOTO_DIVINE_EYE
        return _update_state(state, **updates)

    # ——— 构建报告 ———
    priority_issues = parsed.get(ke.KEY_PRIORITY_ISSUES, [])
    if not isinstance(priority_issues, list):
        priority_issues = []

    new_verdict = cast(DivineHandVerdict, {
        ke.KEY_TIMESTAMP: time.time(),
        ke.KEY_DECISION: decision_code,
        ke.KEY_CONTENT: str(parsed.get(ke.KEY_CONTENT, "")),
        ke.KEY_CONFIDENCE: float(parsed.get(ke.KEY_CONFIDENCE, 0.0)),
        ke.KEY_PRIORITY_ISSUES: priority_issues
    })

    updates[ke.KEY_HAND_REPORTS] = current_hand_reports + [new_verdict]

    # ——— 路由决策 ———
    cfg = en.VAL_DECISION_CONFIGS.get(cast(en.DecisionType, decision_code))
    if cfg:
        next_node = cfg.get(ke.KEY_NEXT_STEP)  # type: ignore
        if next_node and next_node in en.VAL_VALID_NODE_IDS:
            target_status = get_status_from_node(cast(str, next_node))
            message = f"{va.VAL_HAND_OF_GOD} | 执行裁决: {decision_code} → {next_node}"
            updates[ke.KEY_MESSAGE] = message
            logger.info(message, module_name=CHINESE_NAME)
            await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
                ke.KEY_TITLE: va.VAL_HAND_OF_GOD,
                ke.KEY_CONTENT: f"分析完成，置信度 {new_verdict[ke.KEY_CONFIDENCE]:.2f}",
                ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
            })

            new_trace = _append_trace(
                trace=current_trace,
                node_id=node_id,
                node_status=va.VAL_STATUS_COMPLETED,
                next_status=target_status,
            )
            updates[ke.KEY_EXECUTION_TRACE] = new_trace
            updates[ke.KEY_STATUS] = target_status
            return _update_state(state, **updates)

    # 兜底：无效配置
    message = f"{va.VAL_HAND_OF_GOD} | 无有效路由，兜底转上帝之眼"
    updates[ke.KEY_MESSAGE] = message
    logger.error(message, module_name=CHINESE_NAME)
    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_HAND_OF_GOD,
        ke.KEY_CONTENT: "无有效路由，已移交上帝之眼兜底处理",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
    })

    new_trace = _append_trace(
        trace=current_trace,
        node_id=node_id,
        node_status=va.VAL_STATUS_COMPLETED,
        next_status=next_dest,
    )
    updates[ke.KEY_EXECUTION_TRACE] = new_trace
    updates[ke.KEY_STATUS] = next_dest
    return _update_state(state, **updates)
