import asyncio
import time
from typing import Dict, Any
from app.config.config import config
from app.core.meta.executor import submit_metacognition_task
from app.core.meta.state import MetacognitiveOptimizerState
from app.common import keys as ke
from app.common import values as va
from app.core.meta.utils import _append_trace, _update_state
from app.notify.notifier_factory import get_notifiers
from app.utils.logger import LoggerManager as logger
from app.core.services.sse_manager import get_sse_manager
from app.utils.pipeline_persistence import save_metacognition_result, get_db


CHINESE_NAME = "人工介入"
# 用于存储正在等待的任务的asyncio.Event
_suspended_events: Dict[str, asyncio.Event] = {}


async def wait_human_node(state: MetacognitiveOptimizerState) -> MetacognitiveOptimizerState:
    """
    人工介入节点：
    1. 挂起任务并内部启动超时监控。
    2. 通过 SSE 推送通知给前端，同时通过传统渠道（邮件/飞书/企信）发送备份通知。
    3. 挂起前持久化当前元认知状态，供恢复时读取。
    4. 若用户恢复执行，直接返回状态进入上帝之手。
    5. 若超时，自动进入完成状态，走签名→持久化→结束。
    """
    updates: Dict[str, Any] = {}
    task_id = state.get(ke.KEY_ID, "")  # type: ignore
    current_trace = state.get(ke.KEY_EXECUTION_TRACE, [])  # type: ignore
    node_id = va.VAL_NODE_WAIT_HUMAN
    suspended_at = time.time()
    sse = get_sse_manager()

    await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
        ke.KEY_TITLE: va.VAL_HUMAN_USER,
        ke.KEY_CONTENT: "任务已挂起，等待您的介入",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_START}
    })

    # 1. 获取挂起原因
    hand_reports = state.get(ke.KEY_HAND_REPORTS, [])  # type: ignore
    justification = hand_reports[-1].get(ke.KEY_CONTENT, "需要用户介入") if hand_reports else "需要用户介入"

    # 2. 设置挂起状态
    updates[ke.KEY_STATUS] = va.VAL_STATUS_SUSPENDED
    updates[ke.KEY_SUSPENDED_AT] = suspended_at
    updates[ke.KEY_MESSAGE] = justification

    timeout = config.SUSPEND_TIMEOUT_SECONDS or 600

    # 3. 挂起前持久化当前元认知状态（供恢复执行时读取）
    try:
        archive_payload = {
            ke.KEY_ID: task_id,
            ke.KEY_TITLE: config.TEXT_REPORT_TITLE or va.VAL_TEXT_REPORT_PREFIX,
            ke.KEY_INITIAL_SNAPSHOT: state.get(ke.KEY_INITIAL_SNAPSHOT, {}),  # type: ignore
            ke.KEY_CURRENT_DATA: state.get(ke.KEY_CURRENT_DATA, {}),  # type: ignore
            ke.KEY_EXECUTION_TRACE: updates.get(ke.KEY_EXECUTION_TRACE, current_trace),  # type: ignore
            ke.KEY_EYE_REPORTS: state.get(ke.KEY_EYE_REPORTS, []),  # type: ignore
            ke.KEY_HAND_REPORTS: state.get(ke.KEY_HAND_REPORTS, []),  # type: ignore
            ke.KEY_ANALYSIS_REPORTS: state.get(ke.KEY_ANALYSIS_REPORTS, []),  # type: ignore
            ke.KEY_DAO_REPORTS: state.get(ke.KEY_DAO_REPORTS, []),  # type: ignore
            ke.KEY_STATUS: updates[ke.KEY_STATUS],
            ke.KEY_MESSAGE: updates[ke.KEY_MESSAGE],
            ke.KEY_SUSPENDED_AT: suspended_at,
            ke.KEY_USER_CLARIFICATION: state.get(ke.KEY_USER_CLARIFICATION),  # type: ignore
            ke.KEY_MAX_LLM_CALLS: state.get(ke.KEY_MAX_LLM_CALLS),  # type: ignore
            ke.KEY_LLM_CALLS_COUNT: state.get(ke.KEY_LLM_CALLS_COUNT),  # type: ignore
            ke.KEY_EXPIRES_AT: state.get(ke.KEY_EXPIRES_AT),  # type: ignore
            ke.KEY_MAX_ITERATIONS: state.get(ke.KEY_MAX_ITERATIONS),  # type: ignore
            ke.KEY_MAX_CHARS_PER_TURN: state.get(ke.KEY_MAX_CHARS_PER_TURN),  # type: ignore
            ke.KEY_MAX_DEBATE_TURNS_TO_INJECT: state.get(ke.KEY_MAX_DEBATE_TURNS_TO_INJECT),  # type: ignore
            ke.KEY_MAX_ISSUES_TO_DISPLAY: state.get(ke.KEY_MAX_ISSUES_TO_DISPLAY),  # type: ignore
            ke.KEY_VENDOR: config.LLM_DEFAULT_VENDOR,
            ke.KEY_MODEL: config.LLM_DEFAULT_MODEL,
        }
        await save_metacognition_result(
            task_id=task_id,
            data=archive_payload,
            vendor=config.LLM_DEFAULT_VENDOR,
            model=config.LLM_DEFAULT_MODEL,
            collector=None,  # 挂起阶段无 collector
        )
        logger.info(f"💾 [{task_id}] 挂起前元认知状态已持久化", module_name=CHINESE_NAME)
    except Exception as e:
        logger.error(f"💥 [{task_id}] 挂起前持久化失败: {e}", module_name=CHINESE_NAME)

    # 4. 发送 SSE 通知给前端（主要通道，用于弹窗）
    try:
        sse_manager = get_sse_manager()
        await sse_manager.send_pipeline_event(task_id, ke.KEY_HUMAN_INTERVENTION_REQUIRED, {
            ke.KEY_TITLE: va.VAL_HUMAN_USER,
            ke.KEY_CONTENT: justification,
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_HUMAN_INTERVENTION_REQUIRED, ke.KEY_STATUS: ke.KEY_RUNNING}
        })
        logger.info(f"📡 SSE 通知已发送 | 任务: {task_id}", module_name=CHINESE_NAME)
    except Exception as e:
        logger.error(f"SSE 通知发送失败: {e}", module_name=CHINESE_NAME)

    # 5. 发送传统通知（邮件/飞书/企信）作为备份通道
    try:
        notifiers = get_notifiers()
        if notifiers:
            notify_message = f"任务 ID: {task_id}\n原因: {justification}"
            for notifier in notifiers:
                await notifier.send(title=f"⏸️ 任务挂起通知 [{task_id}]", message=notify_message, file_path=None)
            logger.info(f"📧 传统通知已发送 | 任务: {task_id}", module_name=CHINESE_NAME)
    except Exception as e:
        logger.error(f"传统通知发送失败: {e}", module_name=CHINESE_NAME)

    # 6. 内部自监控挂起等待
    event = asyncio.Event()
    _suspended_events[task_id] = event

    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        # 用户恢复执行，回到上帝之手重新裁决
        logger.info(f"任务 {task_id} 被用户恢复执行，回到上帝之手", module_name=CHINESE_NAME)
        updates[ke.KEY_STATUS] = va.VAL_STATUS_GOTO_DIVINE_HAND
        updates[ke.KEY_SUSPENDED_AT] = None

        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_HUMAN_USER,
            ke.KEY_CONTENT: "已收到用户补充信息，任务恢复执行",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
        })
    except asyncio.TimeoutError:
        # 超时兜底：直接进入完成状态，走签名→持久化→结束
        logger.warning(f"任务 {task_id} 挂起超时，自动结束", module_name=CHINESE_NAME)
        updates[ke.KEY_STATUS] = va.VAL_STATUS_COMPLETED
        updates[ke.KEY_MESSAGE] = f"挂起超时，自动结束: {justification}"
        await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
            ke.KEY_TITLE: va.VAL_HUMAN_USER,
            ke.KEY_CONTENT: "挂起超时，任务已自动结束",
            ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
        })
    finally:
        _suspended_events.pop(task_id, None)

    # 7. 记录轨迹并返回
    new_trace = _append_trace(
        current_trace, node_id=node_id,
        node_status=va.VAL_STATUS_COMPLETED,
        next_status=updates[ke.KEY_STATUS],
    )
    updates[ke.KEY_EXECUTION_TRACE] = new_trace
    return _update_state(state, **updates)


async def resume_suspended_task(task_id: str, user_clarification: str = ""):
    """恢复挂起的元认知任务"""
    db = get_db()
    state_data = await db.get_metacognition_data(task_id)

    if not state_data:
        raise ValueError(f"任务 {task_id} 不存在")

    if state_data.get(ke.KEY_STATUS) != va.VAL_STATUS_SUSPENDED:
        raise ValueError(f"任务 {task_id} 未处于挂起状态")

    # 追加用户补充信息
    existing = state_data.get(ke.KEY_USER_CLARIFICATION, "")
    new_clarification = (
        f"{existing}\n\n[用户补充]\n{user_clarification}"
        if existing else user_clarification
    )
    state_data[ke.KEY_USER_CLARIFICATION] = new_clarification
    state_data[ke.KEY_STATUS] = va.VAL_STATUS_RUNNING
    state_data[ke.KEY_SUSPENDED_AT] = None

    # 写回数据库
    await db.save_metacognition_data(state_data)

    # 尝试通过内存事件唤醒
    event = _suspended_events.get(task_id)
    if event:
        event.set()
        logger.info(f"任务 {task_id} 已通过内存事件唤醒", module_name=CHINESE_NAME)
        return

    # 兜底：内存事件丢失（服务重启等），重新提交任务
    logger.warning(f"任务 {task_id} 内存事件丢失，通过重新提交恢复", module_name=CHINESE_NAME)
    await submit_metacognition_task(
        id=task_id,
        content=state_data[ke.KEY_CURRENT_DATA][ke.KEY_CONTENT],
        user_clarification=new_clarification,
    )
