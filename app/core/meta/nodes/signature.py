import traceback
from typing import Any, Dict, List
from app.core.collector.execution_context import ExecutionCollector
from app.core.engine.executor import LLMExecutor
from app.core.meta.state import MetacognitiveOptimizerState, TraceNode
from app.common import keys as ke
from app.common import values as va
from app.core.meta.utils import _update_state, _append_trace, check_llm_budget
from app.core.prompt.prompt_builder import PromptBuilder
from app.core.services.sse_manager import get_sse_manager
from app.core.validators.validator_adapter import validate_metacognition_rules
from app.utils.llm_utils import format_llm_error
from app.utils.logger import LoggerManager as logger
from app.utils.prompt_util import safe_format_prompt

CHINESE_NAME = "语义签名"


async def generate_signature(
        state: MetacognitiveOptimizerState,
        executor: LLMExecutor,
        collector: ExecutionCollector,
) -> MetacognitiveOptimizerState:
    """
    生成元认知语义签名。
    基于优化后的全文，融合道之洞见与上帝之手裁决，
    生成一句带情绪标签的精炼摘要，用于归档与索引。
    """
    updates: Dict[str, Any] = {}
    current_trace: List[TraceNode] = state.get(ke.KEY_EXECUTION_TRACE, [])  # type: ignore
    node_id = va.VAL_NODE_GENERATE_SIGNATURE
    task_id = state.get(ke.KEY_ID) or ""  # type: ignore
    sse = get_sse_manager()

    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_SEMANTIC_SIGNER,
        ke.KEY_CONTENT: "开始生成语义签名",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_START}
    })

    # ——— 预算校验 ———
    if not check_llm_budget(state, va.VAL_SEMANTIC_SIGNER, reserved=0):
        message = f"{va.VAL_SEMANTIC_SIGNER} | LLM 调用预算耗尽"
        updates[ke.KEY_MESSAGE] = message
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_SEMANTIC_SIGNER,
            ke.KEY_CONTENT: "调用次数已达上限，无法生成签名",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        fallback_sig = f"budget_exhausted_{state[ke.KEY_ID][:8]}"  # type: ignore
        updates[ke.KEY_METACOGNITION_SIGNATURE] = fallback_sig
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
    signer_cfg = builder.get_full_config(va.VAL_INTERNAL_METACOGNITION_SIGNATURE, is_prompt=False)
    if not signer_cfg:
        message = f"{va.VAL_SEMANTIC_SIGNER} | 配置缺失 ({va.VAL_INTERNAL_METACOGNITION_SIGNATURE})"
        updates[ke.KEY_MESSAGE] = message
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_SEMANTIC_SIGNER,
            ke.KEY_CONTENT: "缺少必要插件配置，无法生成签名",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        fallback_sig = f"config_missing_{state[ke.KEY_ID][:8]}"  # type: ignore
        updates[ke.KEY_METACOGNITION_SIGNATURE] = fallback_sig
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

    # 优化后的全文
    current_text = state.get(ke.KEY_REVISED_TEXT) or state.get(ke.KEY_CURRENT_DATA, {}).get(ke.KEY_CONTENT, "")  # type: ignore

    # 道之洞见（最后一条）
    dao_reports = state.get(ke.KEY_DAO_REPORTS, [])  # type: ignore
    dao_insight = dao_reports[-1].get(ke.KEY_CONTENT, "") if dao_reports else ""

    # 上帝之手裁决（最后一条）
    hand_reports = state.get(ke.KEY_HAND_REPORTS, [])  # type: ignore
    hand_insight = hand_reports[-1].get(ke.KEY_CONTENT, "") if hand_reports else ""

    # 可用情绪列表
    emotion_list_str = ", ".join(va.VAL_EMOTION_CATEGORIES)

    plugin_id = signer_cfg[ke.KEY_ID]
    type_str = signer_cfg[ke.KEY_TYPE]

    # ——— Prompt 渲染 ———
    try:
        rendered_prompt = safe_format_prompt(
            template=signer_cfg[ke.KEY_PROMPT_TEMPLATE],
            current_text=current_text,
            dao_insight=dao_insight,
            hand_insight=hand_insight,
            emotion_list_str=emotion_list_str,
        )
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_SEMANTIC_SIGNER,
            ke.KEY_CONTENT: "正在提交生成请求...",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_RUNNING}
        })
    except Exception as e:
        message = f"{va.VAL_SEMANTIC_SIGNER} | Prompt 渲染失败: {e}"
        updates[ke.KEY_MESSAGE] = message
        logger.exception(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_SEMANTIC_SIGNER,
            ke.KEY_CONTENT: "Prompt 配置有误，生成失败",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        collector.errors.append({
            ke.KEY_KEY: plugin_id,
            ke.KEY_VALUE: message,
            ke.KEY_TRACEBACK: traceback.format_exc(),
        })
        fallback_sig = f"render_error_{state[ke.KEY_ID][:8]}"  # type: ignore
        updates[ke.KEY_METACOGNITION_SIGNATURE] = fallback_sig
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
            params=signer_cfg[ke.KEY_PARAMS],
            current_text=current_text,
            validator_func=validate_metacognition_rules,
        )
        await collector.record_step_data(response, type_str, plugin_id, rendered_prompt)
    except Exception as e:
        message = f"{va.VAL_SEMANTIC_SIGNER} | LLM 调度异常: {e}"
        updates[ke.KEY_MESSAGE] = message
        logger.exception(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_SEMANTIC_SIGNER,
            ke.KEY_CONTENT: "模型服务异常，生成失败",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        collector.errors.append({
            ke.KEY_KEY: plugin_id,
            ke.KEY_VALUE: message,
            ke.KEY_TRACEBACK: traceback.format_exc(),
        })
        fallback_sig = f"system_error_{state[ke.KEY_ID][:8]}"  # type: ignore
        updates[ke.KEY_METACOGNITION_SIGNATURE] = fallback_sig
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED,
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        return _update_state(state, **updates)

    # ——— 响应处理 ———
    updates[ke.KEY_LLM_CALLS_COUNT] = current_calls + 1

    if not response.ok:
        error_detail = format_llm_error(response)
        message = f"{va.VAL_SEMANTIC_SIGNER} | API 调用失败: {error_detail}"
        updates[ke.KEY_MESSAGE] = message
        logger.warning(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_SEMANTIC_SIGNER,
            ke.KEY_CONTENT: "API 调用失败，生成未完成",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
        fallback_sig = f"api_error_{state[ke.KEY_ID][:8]}"  # type: ignore
        updates[ke.KEY_METACOGNITION_SIGNATURE] = fallback_sig
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
        message = f"{va.VAL_SEMANTIC_SIGNER} | 数据校验失败: {error_detail}"
        updates[ke.KEY_MESSAGE] = message
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_SEMANTIC_SIGNER,
            ke.KEY_CONTENT: "数据校验失败，生成未完成",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

        fallback_sig = f"validation_error_{state[ke.KEY_ID][:8]}"  # type: ignore
        updates[ke.KEY_METACOGNITION_SIGNATURE] = fallback_sig
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED,
            next_status=va.VAL_STATUS_COMPLETED,
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_COMPLETED
        return _update_state(state, **updates)

    # ——— 成功处理 ———
    parsed = response.content.get(ke.KEY_METACOGNITION_SIGNATURE, {}) if isinstance(response.content, dict) else {}
    if isinstance(parsed, dict) and ke.KEY_SIGNATURE in parsed:
        signature = str(parsed[ke.KEY_SIGNATURE]).strip()
    else:
        signature = str(parsed).strip() if parsed else ""

    if not signature:
        logger.warning(f"{va.VAL_SEMANTIC_SIGNER} | 签名内容为空", module_name=CHINESE_NAME)
        signature = f"empty_{state[ke.KEY_ID][:8]}"  # type: ignore
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        updates[ke.KEY_MESSAGE] = "签名生成内容为空"
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_SEMANTIC_SIGNER,
            ke.KEY_CONTENT: "签名内容无效，生成失败",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
    elif len(signature) > 200:
        logger.warning(f"{va.VAL_SEMANTIC_SIGNER} | 签名过长 ({len(signature)} 字符)，截断至 200", module_name=CHINESE_NAME)
        signature = signature[:200]
    else:
        updates[ke.KEY_STATUS] = va.VAL_STATUS_COMPLETED
        updates[ke.KEY_MESSAGE] = "元认知签名生成成功"

    updates[ke.KEY_METACOGNITION_SIGNATURE] = signature

    new_trace = _append_trace(
        trace=current_trace,
        node_id=node_id,
        node_status=va.VAL_STATUS_COMPLETED,
        next_status=va.VAL_STATUS_COMPLETED,
    )
    updates[ke.KEY_EXECUTION_TRACE] = new_trace

    logger.info(f"✅ {va.VAL_SEMANTIC_SIGNER} 生成成功: {signature}", module_name=CHINESE_NAME)

    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_SEMANTIC_SIGNER,
        ke.KEY_CONTENT: "签名已生成",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
    })
    return _update_state(state, **updates)
