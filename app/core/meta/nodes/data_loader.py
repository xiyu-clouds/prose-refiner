from app.common.enums import TextOptimizationLevel
from app.core.meta.state import MetacognitiveOptimizerState
from app.common import keys as ke
from app.common import values as va
from typing import Dict, Any, List
from app.core.meta.utils import _append_trace, _update_state, process_data_granularity
from app.core.services.sse_manager import get_sse_manager
from app.utils.logger import LoggerManager as logger


CHINESE_NAME = "数据加载"


async def data_loader_node(state: MetacognitiveOptimizerState) -> MetacognitiveOptimizerState:
    """
    根据上帝之眼的请求，从 SQLite 加载更高层级的诊断数据，
    完成增量组装后回到上帝之眼重新审视。
    """
    updates: Dict[str, Any] = {}
    current_trace: List[TraceNode] = state.get(ke.KEY_EXECUTION_TRACE, [])  # type: ignore
    node_id = va.VAL_NODE_LOAD_DATA
    task_id = state.get(ke.KEY_ID) or ""  # type: ignore
    sse = get_sse_manager()

    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_DATA_LOADER,
        ke.KEY_CONTENT: "应上帝之眼请求，开始加载所需数据",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_START}
    })

    # 1. 读取上帝之眼最新报告
    eye_reports = state.get(ke.KEY_EYE_REPORTS, [])  # type: ignore
    if not eye_reports:
        msg = "未找到上帝之眼报告，已跳过加载"
        logger.warning(msg, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_DATA_LOADER,
            ke.KEY_CONTENT: msg,
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
        # 记录节点完成
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED,
            next_status=va.VAL_STATUS_GOTO_DIVINE_EYE
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_GOTO_DIVINE_EYE
        updates[ke.KEY_MESSAGE] = "无上帝之眼报告，跳转回上帝之眼"
        return _update_state(state, **updates)

    # 防御性校验
    requested_level = TextOptimizationLevel.clamp(
        eye_reports[-1].get(ke.KEY_REQUESTED_LEVEL, 0)
    )

    # 2. 获取当前数据载荷
    current_data: DataPayload = state.get(ke.KEY_CURRENT_DATA, {}) or {}  # type: ignore
    current_level = current_data.get(ke.KEY_LEVEL, 0)
    data_store: Dict[int, str] = current_data.get(ke.KEY_DATA_STORE, {})

    # 3. 无需加载
    if requested_level <= current_level:
        msg = f"数据已满足需求 (当前 L{current_level} >= 请求 L{requested_level})"
        logger.debug(msg, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_DATA_LOADER,
            ke.KEY_CONTENT: "数据层级已满足要求，无需加载",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_COMPLETED,
            next_status=va.VAL_STATUS_GOTO_DIVINE_EYE
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_GOTO_DIVINE_EYE
        updates[ke.KEY_MESSAGE] = "数据已满足，无需加载"
        return _update_state(state, **updates)

    # 4. 获取任务 ID
    if not task_id:
        msg = "任务 ID 缺失，无法加载数据。"
        logger.error(msg, module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_DATA_LOADER,
            ke.KEY_CONTENT: "任务ID缺失，加载失败",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        updates[ke.KEY_MESSAGE] = msg
        return _update_state(state, **updates)

    logger.info(f"📥 启动数据加载：L{current_level} -> L{requested_level} | 任务: {task_id}", module_name=CHINESE_NAME)

    # 5. 执行增量加载
    try:
        new_store, new_content, final_lvl = await process_data_granularity(
            task_id=task_id,
            requested_level=requested_level,
            current_level=current_level,
            data_store=data_store,
        )
    except Exception as e:
        logger.exception(f"💥 数据加载异常: {e}", module_name=CHINESE_NAME)
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_DATA_LOADER,
            ke.KEY_CONTENT: "数据加载过程中发生异常",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
        })
        new_trace = _append_trace(
            trace=current_trace,
            node_id=node_id,
            node_status=va.VAL_STATUS_FAILED,
            next_status=va.VAL_STATUS_FAILED
        )
        updates[ke.KEY_EXECUTION_TRACE] = new_trace
        updates[ke.KEY_STATUS] = va.VAL_STATUS_FAILED
        updates[ke.KEY_MESSAGE] = f"数据加载异常: {e}"
        return _update_state(state, **updates)

    # 6. 写回状态
    updates[ke.KEY_CURRENT_DATA] = {
        ke.KEY_CONTENT: new_content,
        ke.KEY_LEVEL: final_lvl,
        ke.KEY_DATA_STORE: new_store,
    }
    new_trace = _append_trace(
        current_trace,
        node_id=node_id,
        node_status=va.VAL_STATUS_COMPLETED,
        next_status=va.VAL_STATUS_GOTO_DIVINE_EYE,
    )
    updates[ke.KEY_EXECUTION_TRACE] = new_trace
    updates[ke.KEY_STATUS] = va.VAL_STATUS_GOTO_DIVINE_EYE
    updates[ke.KEY_MESSAGE] = f"数据加载完成，当前层级 L{final_lvl}"

    msg = f"✅ 数据加载完成：L{final_lvl} | 内容长度 {len(new_content)}"
    logger.info(msg, module_name=CHINESE_NAME)
    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_DATA_LOADER,
        ke.KEY_CONTENT:f"数据加载完成，当前层级 L{final_lvl}",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
    })
    return _update_state(state, **updates)
