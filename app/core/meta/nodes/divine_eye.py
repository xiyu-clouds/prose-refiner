import time
import traceback
from typing import Dict, Any, cast
from app.common.enums import TextOptimizationLevel, StrategyCode, get_status_from_node
from app.core.collector.execution_context import ExecutionCollector
from app.core.engine.executor import LLMExecutor
from app.core.meta.state import MetacognitiveOptimizerState, DivineEyeInsight
from app.core.meta.utils import _update_state, check_llm_budget, _create_empty_eye, _append_trace
from app.common import keys as ke
from app.common import enums as en
from app.common import values as va
from app.core.prompt.prompt_builder import PromptBuilder
from app.core.services.sse_manager import get_sse_manager
from app.core.validators.validator_adapter import validate_metacognition_rules
from app.utils.llm_utils import format_llm_error
from app.utils.logger import LoggerManager as logger
from app.utils.prompt_util import safe_format_prompt

CHINESE_NAME = "上帝之眼"


async def divine_eye_node(state: MetacognitiveOptimizerState, executor: LLMExecutor, collector: ExecutionCollector,
                          caller_last_report: str, next_dest: str) -> MetacognitiveOptimizerState:
    updates: Dict[str, Any] = {}
    current_trace: List[TraceNode] = state.get(ke.KEY_EXECUTION_TRACE, [])  # type: ignore
    current_eye_reports = state.get(ke.KEY_EYE_REPORTS, [])  # type: ignore
    node_id = va.VAL_NODE_DIVINE_EYE
    task_id = state.get(ke.KEY_ID) or ""  # type: ignore
    sse = get_sse_manager()

    message = f"{va.VAL_EYE_OF_GOD} 节点被调用。"
    logger.debug(message, module_name=CHINESE_NAME)
    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_EYE_OF_GOD,
        ke.KEY_CONTENT: "开始全局审视当前文本状态",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_START}
    })

    # --- 预算校验 ---
    if not check_llm_budget(state, va.VAL_EYE_OF_GOD):
        message = f"{va.VAL_EYE_OF_GOD} | LLM 调用预算耗尽"
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_EYE_OF_GOD,
            ke.KEY_CONTENT: "调用次数已达上限，无法继续分析",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
        empty_eye = _create_empty_eye(message)
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED,
            next_status=va.VAL_STATUS_COMPLETED_BY_BUDGET
        )

        updates[ke.KEY_MESSAGE] = message
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_EYE_REPORTS] = current_eye_reports + [empty_eye]
        updates[ke.KEY_STATUS] = va.VAL_STATUS_COMPLETED_BY_BUDGET
        return _update_state(state, **updates)

    builder = PromptBuilder()
    eye_cfg = builder.get_full_config(va.VAL_INTERNAL_DIVINE_EYE_INTUITION, is_prompt=False)
    if not eye_cfg:
        message = f"{va.VAL_EYE_OF_GOD} | 配置缺失 ({va.VAL_INTERNAL_DIVINE_EYE_INTUITION})"
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_EYE_OF_GOD,
            ke.KEY_CONTENT: "缺少必要插件配置，分析无法启动",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
        empty_eye = _create_empty_eye(message)
        new_trace = _append_trace(
            current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED,
        )

        updates[ke.KEY_MESSAGE] = message
        updates[ke.KEY_EYE_REPORTS] = current_eye_reports + [empty_eye]
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        return _update_state(state, **updates)

    # ——— 数据准备 ———
    current_calls = state.get(ke.KEY_LLM_CALLS_COUNT, 0)  # type: ignore
    current_data = state.get(ke.KEY_CURRENT_DATA, {})  # type: ignore
    current_text = current_data.get(ke.KEY_CONTENT, "") if isinstance(current_data, dict) else ""
    current_level = current_data.get(ke.KEY_LEVEL, 0) if isinstance(current_data, dict) else 0

    dao_reports = state.get(ke.KEY_DAO_REPORTS, [])  # type: ignore
    dao_insight = f"{dao_reports[-1][ke.KEY_CONTENT]}" if dao_reports else ""

    plugin_id = eye_cfg[ke.KEY_ID]
    type_str = eye_cfg[ke.KEY_TYPE]

    # ——— Prompt 渲染 ———
    try:
        rendered_prompt = safe_format_prompt(
            template=eye_cfg[ke.KEY_PROMPT_TEMPLATE],
            current_level=current_level,
            level_desc=TextOptimizationLevel.get_description(current_level),
            current_text=current_text,
            dao_insight=dao_insight,
            auxiliary_context=caller_last_report,
            level_options=TextOptimizationLevel.get_options_string()
        )
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_EYE_OF_GOD,
            ke.KEY_CONTENT: "正在提交分析请求...",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_RUNNING}
        })
    except Exception as e:
        message = f"{va.VAL_EYE_OF_GOD} | Prompt 渲染失败: {e}"
        logger.exception(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_EYE_OF_GOD,
            ke.KEY_CONTENT: "Prompt 模板配置有误，渲染失败",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
        collector.errors.append({
            ke.KEY_KEY: plugin_id,
            ke.KEY_VALUE: message,
            ke.KEY_TRACEBACK: traceback.format_exc()
        })
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED
        )
        empty_eye = _create_empty_eye(message)

        updates[ke.KEY_MESSAGE] = message
        updates[ke.KEY_EYE_REPORTS] = current_eye_reports + [empty_eye]
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        return _update_state(state, **updates)

    # ——— LLM 调用 ———
    try:
        response = await executor.json(
            prompt=rendered_prompt,
            prompt_id=plugin_id,
            type_str=type_str,
            params=eye_cfg[ke.KEY_PARAMS],
            current_text=current_text,
            validator_func=validate_metacognition_rules
        )

        await collector.record_step_data(response, type_str, plugin_id, rendered_prompt)
    except Exception as e:
        message = f"{va.VAL_EYE_OF_GOD} | LLM 调度异常: {e}"
        logger.exception(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_EYE_OF_GOD,
            ke.KEY_CONTENT: "模型服务调用异常，请稍后重试",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
        collector.errors.append({
            ke.KEY_KEY: plugin_id,
            ke.KEY_VALUE: message,
            ke.KEY_TRACEBACK: traceback.format_exc()
        })
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED,
            next_status=va.VAL_STATUS_GOTO_DIVINE_HAND
        )
        empty_eye = _create_empty_eye(message)

        updates[ke.KEY_MESSAGE] = message
        updates[ke.KEY_EYE_REPORTS] = current_eye_reports + [empty_eye]
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_GOTO_DIVINE_HAND
        return _update_state(state, **updates)

    # ——— 响应处理 ———
    updates[ke.KEY_LLM_CALLS_COUNT] = current_calls + 1

    if not response.ok:
        error_detail = format_llm_error(response)
        message = f"{va.VAL_EYE_OF_GOD} | API 调用失败: {error_detail}"
        logger.warning(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_EYE_OF_GOD,
            ke.KEY_CONTENT: "API 调用失败，分析未能完成",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
        empty_eye = _create_empty_eye(message)
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED
        )

        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_EYE_REPORTS] = current_eye_reports + [empty_eye]
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        updates[ke.KEY_MESSAGE] = message
        return _update_state(state, **updates)

    if not response.valid:
        error_detail = format_llm_error(response)
        message = f"{va.VAL_EYE_OF_GOD} | 数据校验失败: {error_detail}"
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_EYE_OF_GOD,
            ke.KEY_CONTENT: "数据校验失败，分析未能完成",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
        empty_eye = _create_empty_eye(message)
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED,
            next_status=va.VAL_STATUS_GOTO_DIVINE_HAND
        )

        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_EYE_REPORTS] = current_eye_reports + [empty_eye]
        updates[ke.KEY_STATUS] = va.VAL_STATUS_GOTO_DIVINE_HAND
        updates[ke.KEY_MESSAGE] = message
        return _update_state(state, **updates)

    # ——— 解析有效响应 ———
    parsed = response.content.get(ke.KEY_DIVINE_EYE, {}) if isinstance(response.content, dict) else {}
    if not isinstance(parsed, dict) or ke.KEY_STRATEGY not in parsed:
        message = f"{va.VAL_EYE_OF_GOD} | 返回结构缺失必要字段"
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_EYE_OF_GOD,
            ke.KEY_CONTENT: "返回结构缺失必要字段，分析未能完成",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
        empty_eye = _create_empty_eye(message)
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_EYE_REPORTS] = current_eye_reports + [empty_eye]
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        updates[ke.KEY_MESSAGE] = message
        return _update_state(state, **updates)

    # 提取并校验战略代码
    raw_strategy = parsed.get(ke.KEY_STRATEGY)
    strategy_code = raw_strategy.strip() if isinstance(raw_strategy, str) else ""

    if strategy_code not in en.VAL_VALID_STRATEGY:
        message = f"{va.VAL_EYE_OF_GOD} | 无效战略代码: {strategy_code}"
        logger.error(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_EYE_OF_GOD,
            ke.KEY_CONTENT: "返回无效战略代码，分析未能完成",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
        empty_eye = _create_empty_eye(message)
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED
        )

        updates[ke.KEY_MESSAGE] = message
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_EYE_REPORTS] = current_eye_reports + [empty_eye]  # type: ignore
        updates[ke.KEY_STATUS] = va.VAL_STATUS_GOTO_DIVINE_HAND
        return _update_state(state, **updates)

    # ——— 构建报告 ———
    new_report = cast(DivineEyeInsight, {
        ke.KEY_TIMESTAMP: time.time(),
        ke.KEY_STRATEGY: strategy_code,
        ke.KEY_CONTENT: str(parsed.get(ke.KEY_CONTENT, "")),
        ke.KEY_CONFIDENCE: float(parsed.get(ke.KEY_CONFIDENCE, 0.0)),
        ke.KEY_REQUESTED_LEVEL: int(parsed.get(ke.KEY_REQUESTED_LEVEL, 0)),
        ke.KEY_ABORT_RECOMMENDATION: bool(parsed.get(ke.KEY_ABORT_RECOMMENDATION, False)),
        ke.KEY_ABORT_REASON: str(parsed.get(ke.KEY_ABORT_REASON, "")) or None
    })

    eye_reports = current_eye_reports + [new_report]
    updates[ke.KEY_EYE_REPORTS] = eye_reports

    # ——— 核心决策逻辑 ———
    requested_level = new_report.get(ke.KEY_REQUESTED_LEVEL, 0)
    is_abort = new_report.get(ke.KEY_ABORT_RECOMMENDATION, False)
    abort_reason = new_report.get(ke.KEY_ABORT_REASON, "")

    message = f"👁️ {va.VAL_EYE_OF_GOD}分析完成 | 终止={is_abort} | 请求层级={requested_level} | 当前层级={current_level} | 战略={strategy_code}"
    logger.info(message, module_name=CHINESE_NAME)
    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_EYE_OF_GOD,
        ke.KEY_CONTENT: "全局扫描完成，已生成路由决策",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_RUNNING}
    })

    # 场景 A: 【冲突】想停但请求数据 -> 强制去上帝之手
    if is_abort and requested_level > current_level:
        message = f"{va.VAL_EYE_OF_GOD} | 决策冲突：建议终止但请求更高层级 (L{requested_level}) → 交付{va.VAL_HAND_OF_GOD}。"
        logger.warning(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_EYE_OF_GOD,
            ke.KEY_CONTENT: "决策冲突，已移交上帝之手裁决",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
        })
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED,
            next_status=va.VAL_STATUS_GOTO_DIVINE_HAND
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_GOTO_DIVINE_HAND
        updates[ke.KEY_MESSAGE] = message
        return _update_state(state, **updates)

    # 场景 B: 【终止】文本已高度自洽
    if is_abort:
        message = f"{va.VAL_EYE_OF_GOD} | 判定无优化空间: {abort_reason}。"
        logger.info(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_EYE_OF_GOD,
            ke.KEY_CONTENT: "文本已高度自洽，无需优化",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
        })
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED,
            next_status=va.VAL_STATUS_COMPLETED_TRIVIAL
        )

        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_COMPLETED_TRIVIAL
        updates[ke.KEY_MESSAGE] = message
        return _update_state(state, **updates)

    # 场景 C: 【缺数据】加载更高层级
    if requested_level > current_level:
        message = f"{va.VAL_EYE_OF_GOD} | 数据不足：需加载至 L{requested_level}"
        logger.info(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_EYE_OF_GOD,
            ke.KEY_CONTENT: "信息不足，正在加载更高级别数据",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
        })
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED,
            next_status=va.VAL_STATUS_GOTO_LOAD_DATA
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_GOTO_LOAD_DATA
        updates[ke.KEY_MESSAGE] = message
        return _update_state(state, **updates)

    # 场景 D: 【数据充足】执行战略
    cfg = en.VAL_STRATEGY_CONFIGS.get(cast(StrategyCode, strategy_code))
    next_node = cfg.get(ke.KEY_NEXT_STEP)  # type: ignore
    if not cfg:
        message = f"{va.VAL_EYE_OF_GOD} | 缺少上帝之眼路由配置，强制转交上帝之手"
        logger.warning(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_EYE_OF_GOD,
            ke.KEY_CONTENT: message,
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
        })
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED,
            next_status=va.VAL_STATUS_GOTO_DIVINE_HAND
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_GOTO_DIVINE_HAND
        updates[ke.KEY_MESSAGE] = message
        return _update_state(state, **updates)

    if next_node and next_node in en.VAL_VALID_NODE_IDS:
        target_status = get_status_from_node(cast(str, next_node))
        message = f"{va.VAL_EYE_OF_GOD} | 执行战略: {strategy_code} → {next_node}"
        logger.info(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_EYE_OF_GOD,
            ke.KEY_CONTENT: "已确定分析路径，正在移交执行",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
        })
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED,
            next_status=target_status
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = target_status
        updates[ke.KEY_MESSAGE] = message
        return _update_state(state, **updates)

    # 场景 E: 【兜底】无有效路由 → 交付上帝之手
    message = f"{va.VAL_EYE_OF_GOD} | 无有效路由，兜底转上帝之手"
    logger.error(message, module_name=CHINESE_NAME)
    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_EYE_OF_GOD,
        ke.KEY_CONTENT: "无有效路由，已移交上帝之手兜底处理",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
    })
    new_trace = _append_trace(
        trace=current_trace,
        node_id=node_id,
        node_status=va.VAL_STATUS_COMPLETED,
        next_status=next_dest
    )

    updates[ke.KEY_EXECUTION_TRACE] = new_trace
    updates[ke.KEY_STATUS] = next_dest
    updates[ke.KEY_MESSAGE] = message
    return _update_state(state, **updates)
