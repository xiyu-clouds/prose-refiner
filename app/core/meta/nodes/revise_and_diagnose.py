from typing import Dict, Any
from app.common import keys as ke
from app.common import values as va
from app.core.collector.execution_context import ExecutionCollector
from app.core.engine.executor import LLMExecutor
from app.core.meta.state import MetacognitiveOptimizerState
from app.core.meta.utils import _update_state, _append_trace
from app.core.prompt.prompt_builder import PromptBuilder
from app.core.services.sse_manager import get_sse_manager
from app.core.validators.validator_adapter import validate_step_rules
from app.utils.llm_utils import format_llm_error
from app.utils.logger import LoggerManager as logger
from app.utils.prompt_util import safe_format_prompt


CHINESE_NAME = "修复验证"


async def revise_and_diagnose_node(
        state: MetacognitiveOptimizerState,
        executor: LLMExecutor,
        collector: ExecutionCollector,
) -> MetacognitiveOptimizerState:
    """
    修复与验证节点。
    复用文本处理流水线的三个通用步骤：定向修复 → 候选生成 → 智能选择。
    """
    updates: Dict[str, Any] = {}
    current_trace = state.get(ke.KEY_EXECUTION_TRACE, [])  # type: ignore
    node_id = va.VAL_NODE_REVISE_AND_DIAGNOSE
    builder = PromptBuilder()
    task_id = state.get(ke.KEY_ID) or ""  # type: ignore
    sse = get_sse_manager()
    current_calls = state.get(ke.KEY_LLM_CALLS_COUNT, 0)  # type: ignore
    llm_calls_delta = 0

    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_REVISE_DIAGNOSTICIAN,
        ke.KEY_CONTENT: "开始执行文本修复",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_START}
    })

    # 获取原始全文
    current_data = state.get(ke.KEY_CURRENT_DATA, {})  # type: ignore
    current_text = current_data.get(ke.KEY_CONTENT, "") if isinstance(current_data, dict) else ""

    # 获取上帝之手的问题清单
    hand_reports = state.get(ke.KEY_HAND_REPORTS, [])  # type: ignore
    if not hand_reports:
        message = f"{va.VAL_REVISE_DIAGNOSTICIAN} | 缺少上帝之手裁决报告，跳过修复"
        logger.warning(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_REVISE_DIAGNOSTICIAN,
            ke.KEY_CONTENT: "无裁决报告，跳过修复",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
        })

        updates[ke.KEY_REVISED_TEXT] = current_text
        updates[ke.KEY_REVISION_FIX_RECORDS] = []
        updates[ke.KEY_MESSAGE] = message
        updates[ke.KEY_EXECUTION_TRACE] = _append_trace(
            current_trace, node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED, next_status=va.VAL_STATUS_COMPLETED,
        )
        updates[ke.KEY_STATUS] = va.VAL_STATUS_COMPLETED
        return _update_state(state, **updates)

    priority_issues = hand_reports[-1].get(ke.KEY_PRIORITY_ISSUES, [])
    if not priority_issues:
        message = f"{va.VAL_REVISE_DIAGNOSTICIAN} | 问题清单为空，无需修复"
        logger.info(message, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_REVISE_DIAGNOSTICIAN,
            ke.KEY_CONTENT: "无优先级问题，跳过修复",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
        })

        updates[ke.KEY_REVISED_TEXT] = current_text
        updates[ke.KEY_REVISION_FIX_RECORDS] = []
        updates[ke.KEY_MESSAGE] = message
        updates[ke.KEY_EXECUTION_TRACE] = _append_trace(
            current_trace, node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED, next_status=va.VAL_STATUS_COMPLETED,
        )
        updates[ke.KEY_STATUS] = va.VAL_STATUS_COMPLETED
        return _update_state(state, **updates)

    # 格式化问题清单为诊断报告文本
    diagnosis_report = _format_priority_issues(priority_issues)

    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_REVISE_DIAGNOSTICIAN,
        ke.KEY_CONTENT: "正在执行创意增强...",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_START}
    })
    creative_result, delta = await _run_existing_step(
        step_id=va.VAL_RULE_CREATIVE_ENHANCE,
        template_vars={
            ke.KEY_CURRENT_TEXT: current_text,
            ke.KEY_AUXILIARY_DIAGNOSIS_REPORT: diagnosis_report,
        },
        fallback_text={ke.KEY_CREATIVE_ENHANCE: {ke.KEY_CLEANED_TEXT: current_text}},
        current_text=current_text,
        builder=builder, executor=executor, collector=collector
    )
    enhanced_text = creative_result.get(ke.KEY_CREATIVE_ENHANCE, {}).get(ke.KEY_CLEANED_TEXT, current_text)
    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_REVISE_DIAGNOSTICIAN,
        ke.KEY_CONTENT: "创意增强完成",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
    })
    llm_calls_delta += delta

    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_REVISE_DIAGNOSTICIAN,
        ke.KEY_CONTENT: "正在生成候选版本...",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_START}
    })
    candidates_result, delta = await _run_existing_step(
        step_id=va.VAL_RULE_CANDIDATE_GENERATION,
        template_vars={ke.KEY_CURRENT_TEXT: enhanced_text},
        fallback_text={ke.KEY_CANDIDATES_OUTPUT: {ke.KEY_CANDIDATES: []}},
        current_text=current_text,
        builder=builder, executor=executor, collector=collector
    )
    candidates = candidates_result.get(ke.KEY_CANDIDATES_OUTPUT, {}).get(ke.KEY_CANDIDATES, [])
    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_REVISE_DIAGNOSTICIAN,
        ke.KEY_CONTENT: "候选版本生成完成",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
    })
    llm_calls_delta += delta
    candidate_count = len(candidates)

    # ========== 步骤3：智能选择 ==========
    injection_params = state.get(ke.KEY_INITIAL_SNAPSHOT, {}).get(ke.KEY_INJECTION_PARAMS, {})  # type: ignore
    candidate_0 = candidates[0] if candidate_count > 0 else "[缺失] 通用版未生成，请跳过此版本"
    candidate_1 = candidates[1] if candidate_count > 1 else "[缺失] 惊艳版未生成，请跳过此版本"
    candidate_2 = candidates[2] if candidate_count > 2 else "[缺失] 本然版未生成，请跳过此版本"

    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_REVISE_DIAGNOSTICIAN,
        ke.KEY_CONTENT: "正在进行智能选择...",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_START}
    })
    selection_result, delta = await _run_existing_step(
        step_id=va.VAL_RULE_INTELLIGENT_SELECTION,
        template_vars={
            ke.KEY_ORIGINAL_TEXT: current_text,
            ke.KEY_CURRENT_TEXT: enhanced_text,
            ke.KEY_CANDIDATE_0: candidate_0,
            ke.KEY_CANDIDATE_1: candidate_1,
            ke.KEY_CANDIDATE_2: candidate_2,
            ke.KEY_CHARACTER_PROFILES: injection_params.get(ke.KEY_CHARACTER_PROFILES, ""),
            ke.KEY_RELATIONSHIP_MAP: injection_params.get(ke.KEY_RELATIONSHIP_MAP, ""),
            ke.KEY_WORLDVIEW_RULES: injection_params.get(ke.KEY_WORLDVIEW_RULES, ""),
            ke.KEY_STYLE_PREFERENCE: injection_params.get(ke.KEY_STYLE_PREFERENCE, "")
        },
        fallback_text={ke.KEY_SELECTION_RESULT: {ke.KEY_SELECTED_INDEX: 1, ke.KEY_REASON: "默认选择"}},
        current_text=current_text,
        builder=builder, executor=executor, collector=collector
    )
    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_REVISE_DIAGNOSTICIAN,
        ke.KEY_CONTENT: "智能选择完成",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
    })
    llm_calls_delta += delta
    selection_data = selection_result.get(ke.KEY_SELECTION_RESULT, {})
    selected_index = selection_data.get(ke.KEY_SELECTED_INDEX, 1)
    selection_reason = selection_data.get(ke.KEY_REASON, "默认选择")
    all_versions = [current_text, enhanced_text] + candidates
    selected_text = all_versions[selected_index] if 0 <= selected_index < len(all_versions) else enhanced_text

    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_REVISE_DIAGNOSTICIAN,
        ke.KEY_CONTENT: "正在进行保真修复...",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_START}
    })
    repair_result, delta = await _run_existing_step(
        step_id=va.VAL_RULE_FIDELITY_REPAIR,
        template_vars={
            ke.KEY_INIT_TEXT: current_text,
            ke.KEY_CURRENT_TEXT: selected_text,
        },
        fallback_text={ke.KEY_FIDELITY_REPAIR: {ke.KEY_CLEANED_TEXT: selected_text}},
        current_text=current_text,
        builder=builder, executor=executor, collector=collector
    )
    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_REVISE_DIAGNOSTICIAN,
        ke.KEY_CONTENT: "保真修复完成",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
    })
    llm_calls_delta += delta
    repair_data = repair_result.get(ke.KEY_FIDELITY_REPAIR, {})
    final_text = repair_data.get(ke.KEY_CLEANED_TEXT, selected_text)
    fidelity_issues = repair_data.get(ke.KEY_ISSUES_FIXED, [])

    updates[ke.KEY_LLM_CALLS_COUNT] = current_calls + llm_calls_delta

    revision_records = [
        {
            ke.KEY_ISSUES_COUNT: len(priority_issues),
            ke.KEY_CANDIDATES_COUNT: candidate_count,
            ke.KEY_SELECTED_INDEX: selected_index,
            ke.KEY_SELECTED_REASON: selection_reason,
            ke.KEY_ISSUES_FIXED: fidelity_issues
        }
    ]

    message = (
        f"{va.VAL_REVISE_DIAGNOSTICIAN} | 修复完成 | "
        f"问题: {len(priority_issues)} 项 | 候选: {candidate_count} 个 | 选中: 版本{selected_index}"
    )
    logger.info(message, module_name=CHINESE_NAME)

    updates[ke.KEY_REVISED_TEXT] = final_text
    updates[ke.KEY_REVISION_FIX_RECORDS] = revision_records
    updates[ke.KEY_MESSAGE] = message
    updates[ke.KEY_EXECUTION_TRACE] = _append_trace(
        current_trace, node_id=node_id,
        node_status=va.VAL_STATUS_COMPLETED, next_status=va.VAL_STATUS_COMPLETED,
    )
    updates[ke.KEY_STATUS] = va.VAL_STATUS_COMPLETED

    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_REVISE_DIAGNOSTICIAN,
        ke.KEY_CONTENT: "修复与验证完成，最终文本已生成",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
    })
    return _update_state(state, **updates)


def _format_priority_issues(priority_issues: list) -> str:
    """将问题清单格式化为 Prompt 可用的诊断报告文本"""
    if not priority_issues:
        return "无诊断问题"

    lines = ["### 诊断问题清单"]
    for issue in priority_issues:
        lines.append(
            f"- [{issue.get(ke.KEY_PRIORITY, '?')}] {issue.get(ke.KEY_CATEGORY, '')}: {issue.get(ke.KEY_ISSUE, '')}"
        )
        if issue.get(ke.KEY_SUGGESTED_FIX):
            lines.append(f"  修复方向: {issue[ke.KEY_SUGGESTED_FIX]}")
    return "\n".join(lines)


async def _run_existing_step(
        step_id: str,
        template_vars: dict,
        fallback_text: Any,
        current_text: str,
        builder: PromptBuilder,
        executor: LLMExecutor,
        collector: ExecutionCollector
) -> tuple[Any, int]:
    """通用步骤执行器，返回 (结果, 本次调用次数增量: 0 或 1)"""
    cfg = builder.get_full_config(step_id, is_prompt=True)
    if not cfg:
        logger.error(f"{CHINESE_NAME} | 缺少步骤配置: {step_id}", module_name=CHINESE_NAME)
        return fallback_text, 0

    try:
        rendered_prompt = safe_format_prompt(
            template=cfg[ke.KEY_PROMPT_TEMPLATE],
            **template_vars,
        )
    except Exception as e:
        logger.error(f"{CHINESE_NAME} | {step_id} Prompt 渲染失败: {e}", module_name=CHINESE_NAME)
        return fallback_text, 0

    try:
        response = await executor.json(
            prompt=rendered_prompt,
            type_str=ke.KEY_INTERNAL,
            prompt_id=step_id,
            params=cfg[ke.KEY_PARAMS],
            current_text=current_text,
            validator_func=validate_step_rules,
        )
        await collector.record_step_data(response, ke.KEY_INTERNAL, step_id, rendered_prompt)

        if not response.ok or not response.valid:
            logger.error(f"{CHINESE_NAME} | {step_id} 失败: {format_llm_error(response)}")
            return fallback_text, 1

        content = response.content
        if not content:
            logger.warning(f"{CHINESE_NAME} | {step_id} 返回空内容，使用 fallback")
            return fallback_text, 1

        # 直接返回完整的 content 字典
        return content, 1

    except Exception as e:
        logger.error(f"{CHINESE_NAME} | {step_id} 异常: {e}", module_name=CHINESE_NAME)
        return fallback_text, 0
