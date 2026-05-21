import traceback
from datetime import datetime, timezone
from typing import Dict, Any, List, cast
from app.core.prompt.prompt_builder import PromptBuilder
from app.core.services.sse_manager import get_sse_manager
from app.core.validators.validator_adapter import validate_metacognition_rules
from app.utils.llm_utils import format_llm_error
from app.utils.logger import LoggerManager as logger
from app.core.collector.execution_context import ExecutionCollector
from app.core.engine.executor import LLMExecutor
from app.core.meta.state import MetacognitiveOptimizerState, TraceNode, DaoInsightRecord
from app.core.meta.utils import _update_state, _create_empty_dao, check_llm_budget, _append_trace
from app.common import keys as ke
from app.common import values as va
from app.utils.prompt_util import safe_format_prompt


CHINESE_NAME = "道之洞见"


async def dao_node(state: MetacognitiveOptimizerState, executor: LLMExecutor, collector: ExecutionCollector, caller: str, caller_last_report: str, dao_last_insight: str) -> MetacognitiveOptimizerState:
    updates: Dict[str, Any] = {}
    current_trace: List[TraceNode] = state.get(ke.KEY_EXECUTION_TRACE, [])  # type: ignore
    current_dao_reports = state.get(ke.KEY_DAO_REPORTS, [])  # type: ignore
    node_id = va.VAL_NODE_DAO
    task_id = state.get(ke.KEY_ID) or ""  # type: ignore
    sse = get_sse_manager()

    message = f"{va.VAL_DAO} 节点被调用 | 调用方: {caller}"
    logger.debug(message, module_name=CHINESE_NAME)
    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_DAO,
        ke.KEY_CONTENT: f"应 {caller} 请求，开始生成{va.VAL_DAO}",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_START}
    })

    if not check_llm_budget(state, va.VAL_DAO):
        message = f"{va.VAL_DAO} | 调用方: {caller} | LLM 调用预算耗尽"
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_DAO,
            ke.KEY_CONTENT: "调用次数已达上限，无法继续分析",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
        empty_dao = _create_empty_dao(va.VAL_DAO, message)
        new_trace = _append_trace(
            current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED_BY_BUDGET,
            next_status=va.VAL_STATUS_COMPLETED_BY_BUDGET,
        )

        updates[ke.KEY_MESSAGE] = message
        updates[ke.KEY_DAO_REPORTS] = current_dao_reports + [empty_dao]
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_COMPLETED_BY_BUDGET
        return _update_state(state, **updates)

    builder = PromptBuilder()
    dao_cfg = builder.get_full_config(va.VAL_INTERNAL_DAO_INSIGHT, is_prompt=False)
    if not dao_cfg:
        message = f"{va.VAL_DAO} | 调用方: {caller} | 配置缺失 ({va.VAL_INTERNAL_DAO_INSIGHT})"
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_DAO,
            ke.KEY_CONTENT: "缺少必要插件配置，分析无法启动",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
        empty_dao = _create_empty_dao(va.VAL_DAO, message)
        new_trace = _append_trace(
            current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED,
        )

        updates[ke.KEY_MESSAGE] = message
        updates[ke.KEY_DAO_REPORTS] = current_dao_reports + [empty_dao]
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        return _update_state(state, **updates)

    type_str = dao_cfg[ke.KEY_TYPE]

    # 准备占位符变量
    current_data = state.get(ke.KEY_CURRENT_DATA, {})  # type: ignore
    current_text = current_data.get(ke.KEY_CONTENT, "") if isinstance(current_data, dict) else ""
    supplement_details = state.get(ke.KEY_USER_CLARIFICATION, "") or ""  # type: ignore
    if supplement_details:
        supplement_details = "### 用户补充细节\n" + supplement_details

    # 道元规则文本
    dao_text = builder.build_dao_section()
    # 按需构建辅助上下文
    auxiliary_context_parts = []
    if caller_last_report:
        auxiliary_context_parts.append(f"### {caller}上一轮诊断\n{caller_last_report}")
    if dao_last_insight:
        auxiliary_context_parts.append(f"### 道之洞见上一轮研判\n{dao_last_insight}")

    auxiliary_context = "### 辅助上下文" + "\n".join(auxiliary_context_parts) if auxiliary_context_parts else ""
    try:
        rendered_prompt = safe_format_prompt(
            template=dao_cfg[ke.KEY_PROMPT_TEMPLATE],
            dao=dao_text,
            current_text=current_text,
            supplement_details=supplement_details,
            auxiliary_context=auxiliary_context
        )
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_DAO,
            ke.KEY_CONTENT: "正在提交分析请求...",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_RUNNING}
        })
    except KeyError as e:
        message = f"{va.VAL_DAO} | 调用方: {caller} | Prompt 模板占位符缺失: {e}"
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_DAO,
            ke.KEY_CONTENT: "Prompt 模板配置有误，渲染失败",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
        empty_dao = _create_empty_dao(va.VAL_DAO, message)
        new_trace = _append_trace(
            current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED,
        )

        updates[ke.KEY_MESSAGE] = message
        updates[ke.KEY_DAO_REPORTS] = current_dao_reports + [empty_dao]
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        return _update_state(state, **updates)

    try:
        response = await executor.json(
            prompt=rendered_prompt,
            type_str=type_str,
            prompt_id=va.VAL_INTERNAL_DAO_INSIGHT,
            params=dao_cfg[ke.KEY_PARAMS],
            current_text=current_text,
            validator_func=validate_metacognition_rules
        )
        await collector.record_step_data(response, type_str, va.VAL_INTERNAL_DAO_INSIGHT, rendered_prompt)
    except Exception as e:
        message = f"{va.VAL_DAO} | 调用方: {caller} | LLM 调度崩溃: {e}"
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_DAO,
            ke.KEY_CONTENT: "模型服务调用异常，请稍后重试",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
        collector.errors.append({
            ke.KEY_KEY: va.VAL_INTERNAL_DAO_INSIGHT,
            ke.KEY_VALUE: message,
            ke.KEY_TRACEBACK: traceback.format_exc(),
        })
        empty_dao = _create_empty_dao(va.VAL_DAO, message)
        new_trace = _append_trace(
            current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED,
        )

        updates[ke.KEY_MESSAGE] = message
        updates[ke.KEY_DAO_REPORTS] = current_dao_reports + [empty_dao]
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        return _update_state(state, **updates)

    # 5. 处理响应
    llm_calls = state.get(ke.KEY_LLM_CALLS_COUNT, 0) + 1  # type: ignore
    updates[ke.KEY_LLM_CALLS_COUNT] = llm_calls

    if not response.ok:
        error_detail = format_llm_error(response)
        message = f"{va.VAL_DAO} | 调用方: {caller} | API 失败: {error_detail}"
        logger.warning(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_DAO,
            ke.KEY_CONTENT: "API 调用失败，分析未能完成",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
        empty_dao = _create_empty_dao(va.VAL_DAO, message)
        new_trace = _append_trace(
            current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED,
        )

        updates[ke.KEY_MESSAGE] = message
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_DAO_REPORTS] = current_dao_reports + [empty_dao]
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        return _update_state(state, **updates)

    if not response.valid:
        error_detail = format_llm_error(response)
        message = f"{va.VAL_DAO} | 调用方: {caller} | 数据校验失败: {error_detail}"
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_DAO,
            ke.KEY_CONTENT: "数据校验失败，分析未能完成",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
        empty_dao = _create_empty_dao(va.VAL_DAO, message)
        new_trace = _append_trace(
            current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED,
        )

        updates[ke.KEY_MESSAGE] = message
        updates[ke.KEY_DAO_REPORTS] = current_dao_reports + [empty_dao]
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        return _update_state(state, **updates)

    parsed = response.content.get(ke.KEY_DAO, {}) if isinstance(response.content, dict) else {}
    if not isinstance(parsed, dict) or ke.KEY_CONTENT not in parsed or ke.KEY_CONFIDENCE not in parsed:
        message = f"{va.VAL_DAO} | 调用方: {caller} | 返回结构不完整"
        updates[ke.KEY_MESSAGE] = message
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_DAO,
            ke.KEY_CONTENT: "返回结构缺失必要字段，分析未能完成",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        empty_dao = _create_empty_dao(va.VAL_DAO, message)
        updates[ke.KEY_DAO_REPORTS] = state.get(ke.KEY_DAO_REPORTS, []) + [empty_dao]  # type: ignore
        new_trace = _append_trace(
            current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED,
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        return _update_state(state, **updates)

    dao_record = cast(DaoInsightRecord, {
        ke.KEY_TIMESTAMP: datetime.now(timezone.utc).timestamp(),
        ke.KEY_CALLER: va.VAL_DAO,
        ke.KEY_CONTENT: str(parsed[ke.KEY_CONTENT]),
        ke.KEY_CONFIDENCE: float(parsed.get(ke.KEY_CONFIDENCE, 0.0)),
    })

    updates[ke.KEY_DAO_REPORTS] = current_dao_reports + [dao_record]
    new_trace = _append_trace(
        current_trace,
        node_id=node_id,
        node_status=va.VAL_STATUS_COMPLETED,
        next_status=state.get(ke.KEY_STATUS, va.VAL_STATUS_RUNNING),  # type: ignore
    )
    updates[ke.KEY_EXECUTION_TRACE] = new_trace
    message = f"{va.VAL_DAO}已生成 | 调用方: {caller} | 置信度: {dao_record[ke.KEY_CONFIDENCE]:.2f}"
    logger.info(message, module_name=CHINESE_NAME,)
    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_DAO,
        ke.KEY_CONTENT: f"分析完成，置信度 {dao_record[ke.KEY_CONFIDENCE]:.2f}",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
    })

    return _update_state(state, **updates)
