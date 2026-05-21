import time
import uuid
from typing import Dict, Any
from app.config.config import config
from app.core.collector.execution_context import ExecutionCollector
from app.core.context.context_builder import ContextBuilder
from app.core.engine.executor import LLMExecutor
from app.core.meta.state import MetacognitiveOptimizerState
from app.common import keys as ke
from app.common import values as va
from app.common import paths as pa
from app.core.meta.utils import _update_state, _append_trace, fix_trace_next_node_ids, convert_int_keys_to_str
from app.core.services.sse_manager import get_sse_manager
from app.report.report_generator import ReportGenerator
from app.utils.file_util import FileUtil
from app.utils.llm_utils import sort_context_paragraphs
from app.utils.logger import LoggerManager as logger
from app.utils.pipeline_persistence import save_metacognition_result, get_db
from app.utils.watermark_utils import inject_watermark_into_result


CHINESE_NAME = "持久化存储"


async def persist_result(state: MetacognitiveOptimizerState, executor: LLMExecutor,
                          collector: ExecutionCollector) -> MetacognitiveOptimizerState:
    """
    持久化节点。
    - 通过 save_metacognition_result 完成三轨存储（SQLite + 业务快照 + 大染缸）。
    - 生成可视化 HTML 报告。
    """
    updates: Dict[str, Any] = {}
    current_trace = state.get(ke.KEY_EXECUTION_TRACE, [])  # type: ignore
    node_id = va.VAL_NODE_PERSIST_RESULT
    task_id = state.get(ke.KEY_ID) or ""  # type: ignore
    sse = get_sse_manager()

    message = f"{va.VAL_PERSISTENCE_AGENT} 节点被调用"
    logger.debug(message, module_name=CHINESE_NAME)
    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_PERSISTENCE_AGENT,
        ke.KEY_CONTENT: "开始持久化存储...",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_START}
    })

    # 修正并追加轨迹
    new_trace = _append_trace(
        trace=current_trace,
        node_id=node_id,
        node_status=va.VAL_STATUS_COMPLETED,
        next_status=va.VAL_STATUS_COMPLETED,
    )
    if new_trace:
        updates[ke.KEY_EXECUTION_TRACE] = fix_trace_next_node_ids(new_trace)

    # 获取任务ID
    if not task_id:
        fallback_id = f"fallback_{uuid.uuid4().hex[:8]}_{int(time.time())}"
        logger.critical(f"⚠️ 任务 ID 缺失，生成兜底 ID：{fallback_id}", module_name=CHINESE_NAME)
        task_id = fallback_id

    db = get_db()
    text = await db.get_text_processing_data(task_id)
    if text:
        text[ke.KEY_CONTEXT] = sort_context_paragraphs(text.get(ke.KEY_CONTEXT, {}))

    # 组装归档数据
    meta = {
        ke.KEY_ID: task_id,
        ke.KEY_INITIAL_SNAPSHOT: state.get(ke.KEY_INITIAL_SNAPSHOT, {}),  # type: ignore
        ke.KEY_CURRENT_DATA: state.get(ke.KEY_CURRENT_DATA, {}),  # type: ignore
        ke.KEY_EXECUTION_TRACE: updates.get(ke.KEY_EXECUTION_TRACE, current_trace),
        ke.KEY_EYE_REPORTS: state.get(ke.KEY_EYE_REPORTS, []),  # type: ignore
        ke.KEY_HAND_REPORTS: state.get(ke.KEY_HAND_REPORTS, []),  # type: ignore
        ke.KEY_ANALYSIS_REPORTS: state.get(ke.KEY_ANALYSIS_REPORTS, []),  # type: ignore
        ke.KEY_DAO_REPORTS: state.get(ke.KEY_DAO_REPORTS, []),  # type: ignore
        ke.KEY_STATUS: state.get(ke.KEY_STATUS, ""),  # type: ignore
        ke.KEY_MESSAGE: state.get(ke.KEY_MESSAGE, ""),  # type: ignore
        ke.KEY_METACOGNITION_SIGNATURE: state.get(ke.KEY_METACOGNITION_SIGNATURE),  # type: ignore
        ke.KEY_REVISED_TEXT: state.get(ke.KEY_REVISED_TEXT),  # type: ignore
        ke.KEY_REVISION_FIX_RECORDS: state.get(ke.KEY_REVISION_FIX_RECORDS, []),  # type: ignore
        ke.KEY_USER_CLARIFICATION: state.get(ke.KEY_USER_CLARIFICATION),  # type: ignore
        ke.KEY_RESOURCE_USAGE: {
            ke.KEY_LLM_CALLS_COUNT: state.get(ke.KEY_LLM_CALLS_COUNT),  # type: ignore
            ke.KEY_MAX_LLM_CALLS: state.get(ke.KEY_MAX_LLM_CALLS),  # type: ignore
            ke.KEY_EXPIRES_AT: state.get(ke.KEY_EXPIRES_AT),  # type: ignore
            ke.KEY_MAX_ITERATIONS: state.get(ke.KEY_MAX_ITERATIONS),  # type: ignore
            ke.KEY_MAX_DEBATE_ROUNDS: state.get(ke.KEY_MAX_DEBATE_ROUNDS),  # type: ignore
            ke.KEY_MAX_CHARS_PER_TURN: state.get(ke.KEY_MAX_CHARS_PER_TURN),  # type: ignore
            ke.KEY_MAX_DEBATE_TURNS_TO_INJECT: state.get(ke.KEY_MAX_DEBATE_TURNS_TO_INJECT),  # type: ignore
            ke.KEY_MAX_ISSUES_TO_DISPLAY: state.get(ke.KEY_MAX_ISSUES_TO_DISPLAY),  # type: ignore
            ke.KEY_TIMESTAMP_END: int(time.time()),
        },
        ke.KEY_VENDOR: config.LLM_DEFAULT_VENDOR,
        ke.KEY_MODEL: config.LLM_DEFAULT_MODEL,
    }

    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_PERSISTENCE_AGENT,
        ke.KEY_CONTENT: "正在保存元认知数据...",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_RUNNING}
    })

    # 三轨持久化（SQLite + 业务快照 + 大染缸）
    try:
        await save_metacognition_result(
            task_id=task_id,
            data=meta,
            vendor=executor.vendor,
            model=executor.model,
            collector=collector,
        )
    except Exception as e:
        logger.exception(f"💥 [{task_id}] 元认知持久化失败：{str(e)}", module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_PERSISTENCE_AGENT,
            ke.KEY_CONTENT: "元认知数据保存失败",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })

    archive_payload = {
        ke.KEY_TEXT: text,
        ke.KEY_META: meta
    }
    archive_payload = convert_int_keys_to_str(archive_payload)

    # 可视化报告
    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_PERSISTENCE_AGENT,
        ke.KEY_CONTENT: "正在生成可视化报告...",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_RUNNING}
    })
    try:
        file_util = FileUtil()
        inject_watermark_into_result(archive_payload)
        report_generator = ReportGenerator(file_util, config.PATH_FILE_REPORT_TEMPLATE_HTML_DIR)
        report_path = report_generator.render_report_to_html(
            archive_payload,
            pa.FILE_REPORT_TEMPLATE_HTML,
            va.VAL_TEXT_REPORT_PREFIX,
            config.REPORTS_DIR,
        )
        if report_path:
            normalized_path = file_util.to_posix_str(report_path)
            await db.update_file_paths(task_id, {ke.KEY_PATH_REPORT: normalized_path})
            logger.info(f"📄 [{task_id}] 可视化报告已生成：{report_path}", module_name=CHINESE_NAME)
            await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
                ke.KEY_TITLE: va.VAL_PERSISTENCE_AGENT,
                ke.KEY_CONTENT: "报告已生成，元认知分析完成",
                ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
            })
    except Exception as e:
        logger.exception(f"💥 [{task_id}] 可视化报告生成失败：{str(e)}", module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_PERSISTENCE_AGENT,
            ke.KEY_CONTENT: "报告生成失败，但数据已保存",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
        })

    updates[ke.KEY_STATUS] = va.VAL_STATUS_COMPLETED
    updates[ke.KEY_MESSAGE] = "持久化完成"
    cb = ContextBuilder()
    cb.reset()
    # 最终任务完成
    await sse.send_pipeline_event(task_id, ke.KEY_TASK_COMPLETED, {
        ke.KEY_TITLE: "任务完成",
        ke.KEY_CONTENT: "文本处理与元认知分析已全部完成",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
    })
    return _update_state(state, **updates)
