"""
元认知执行器（Metacognition Executor）
负责异步、并发地执行元认知推理任务（如反思、修正、决策等）。
采用生产者 - 消费者模型：
  - 生产者：定时任务、API 调用等通过 `submit_metacognition_task` 提交任务
  - 消费者：后台工作者（worker）从队列中取出任务并执行
支持优雅启动与关闭，避免任务丢失或资源泄漏。
"""
from app.config.config import config
from app.core.meta.state import MetacognitiveOptimizerState
from app.db.memory_db import MemoryPhaseDB
import asyncio
import time
import uuid
from asyncio import Queue
from typing import Optional, Callable, Set
from app.notify.notifier_factory import get_notifiers
from app.utils.logger import LoggerManager as logger
from app.common import keys as ke
from app.common import values as va


CHINESE_NAME = "元认知执行器"

# 全局资源（延迟初始化，避免模块导入时副作用）
_META_COG_QUEUE: Optional[Queue] = None
_META_COG_SEMAPHORE: Optional[asyncio.Semaphore] = None
_DB_INSTANCE: Optional[MemoryPhaseDB] = None
_shutdown_event: Optional[asyncio.Event] = None
# 进程级去重集合
_submitted_ids: Set[str] = set()
_submitted_lock: Optional[asyncio.Lock] = None


# ==============================================================================
# 内部工具函数
# ==============================================================================
def _init_executor():
    """
    初始化元认知执行器所需的全局资源。
    幂等操作：多次调用不会重复初始化。
    """
    global _META_COG_QUEUE, _META_COG_SEMAPHORE, _DB_INSTANCE, _submitted_lock
    if _META_COG_QUEUE is None:
        _META_COG_QUEUE = Queue(maxsize=config.METACOGNITION_QUEUE_MAXSIZE)
        _META_COG_SEMAPHORE = asyncio.Semaphore(config.METACOGNITION_MAX_WORKER)
        _DB_INSTANCE = MemoryPhaseDB.get_instance(config.DB_PATH)
        _submitted_lock = asyncio.Lock()


async def _check_and_mark_submitted(phase_id: str) -> bool:
    """
    进程级去重：检查并标记 phase_id 是否已提交过元认知任务
    Returns:
        True = 已提交过（本次跳过），False = 未提交（本次可提交）
    """
    async with _submitted_lock:
        if phase_id in _submitted_ids:
            return True
        _submitted_ids.add(phase_id)
        return False


def get_metacognitive_queue() -> Queue:
    """获取元认知任务队列实例"""
    if _META_COG_QUEUE is None:
        raise RuntimeError(
            "元认知执行器未启动。请确保在应用 startup 中调用了 start_metacog_workers()"
        )
    return _META_COG_QUEUE


async def monitor_metacognition_queue():
    """
    后台监控任务：定期检查队列堆积情况，超过阈值时记录警告日志并发送通知。
    """
    # 统一提取配置，就地兜底
    max_size = config.METACOGNITION_QUEUE_MAXSIZE or 30
    high_watermark = config.METACOGNITION_QUEUE_HIGH_WATERMARK or 0.8
    mid_watermark = config.METACOGNITION_QUEUE_MID_WATERMARK or 0.5
    alert_cooldown = config.METACOGNITION_MONITOR_ALERT_COOLDOWN or 600
    check_interval = config.METACOGNITION_QUEUE_CHECK_INTERVAL or 30

    last_alert_time = 0

    while True:
        try:
            queue = get_metacognitive_queue()
            queue_size = queue.qsize()

            usage_ratio = queue_size / max_size if max_size > 0 else 0
            usage_percent = usage_ratio * 100

            # 高水位告警
            if queue_size > max_size * high_watermark:
                logger.warning(
                    f"⚠️ 元认知队列严重堆积：{queue_size}/{max_size} ({usage_percent:.1f}%)",
                    module_name=CHINESE_NAME,
                    extra={
                        ke.KEY_QUEUE_SIZE: queue_size,
                        ke.KEY_MAX_SIZE: max_size,
                        ke.KEY_USAGE_PERCENT: usage_percent,
                    },
                )
                current_time = asyncio.get_event_loop().time()
                if current_time - last_alert_time > alert_cooldown:
                    notifiers = get_notifiers()
                    if notifiers:
                        notify_title = "🔴 紧急：元认知队列堆积告警"
                        notify_message = (
                            f"当前积压任务数：**{queue_size}**\n"
                            f"队列最大容量：{max_size}\n"
                            f"使用率：**{usage_percent:.1f}%**\n\n"
                            f"建议检查：\n"
                            f"1. 消费者服务是否存活\n"
                            f"2. 下游 LLM 接口是否响应过慢"
                        )
                        for notifier in notifiers:
                            try:
                                await notifier.send(
                                    title=notify_title,
                                    message=notify_message,
                                    file_path=None,
                                )
                            except Exception as notify_err:
                                logger.error(f"⚠️ 单个通知渠道发送失败: {notify_err}", module_name=CHINESE_NAME)
                    last_alert_time = current_time
                    logger.info("📧 告警通知已发送", module_name=CHINESE_NAME)

            # 中水位提示
            elif queue_size > max_size * mid_watermark:
                logger.info(
                    f"📊 元认知队列使用率偏高：{queue_size}/{max_size} ({usage_percent:.1f}%)",
                    module_name=CHINESE_NAME,
                )

            await asyncio.sleep(check_interval)

        except Exception as e:
            logger.error(f"队列监控循环异常：{e}", module_name=CHINESE_NAME)
            await asyncio.sleep(60)


# ==============================================================================
# 核心任务执行逻辑
# ==============================================================================
async def run_metacognitive_loop(
        id: str,
        content: str,
        user_clarification: Optional[str] = None,
        callback: Optional[Callable] = None,
        **extra_overrides,
):
    """
    执行单个元认知任务的完整生命周期。
    """
    try:
        trace_id = str(uuid.uuid4())
        logger.set_trace_id(trace_id)

        db = _DB_INSTANCE

        # 数据库级去重
        already_exists = await db.has_metacognition_record(id)
        if already_exists:
            logger.info(f"⏭️ 元认知记录已存在，跳过执行 | {ke.KEY_ID}={id}", module_name=CHINESE_NAME)
            return

        # 合并配置默认值
        llm_calls = config.METACOGNITION_MAX_LLM_CALLS or 30
        exp_at = config.METACOGNITION_EXPIRES_AT or 300
        debate = config.METACOGNITION_MAX_DEBATE_ROUNDS or 2
        chars = config.METACOGNITION_MAX_CHARS_PER_TURN or 800
        turns = config.METACOGNITION_MAX_DEBATE_TURNS_TO_INJECT or 2
        issues = config.METACOGNITION_MAX_ISSUES_TO_DISPLAY or 7
        lvl = config.METACOGNITION_DATA_LOADER_DEFAULT_LEVEL or 0

        # 构建初始快照
        snapshot_data = {
            ke.KEY_ID: id,
            ke.KEY_CONTENT: content,
            ke.KEY_LEVEL: lvl,
            ke.KEY_USER_CLARIFICATION: user_clarification,
            ke.KEY_MAX_LLM_CALLS: llm_calls,
            ke.KEY_EXPIRES_AT: exp_at,
            ke.KEY_MAX_DEBATE_ROUNDS: debate,
            ke.KEY_MAX_CHARS_PER_TURN: chars,
            ke.KEY_MAX_DEBATE_TURNS_TO_INJECT: turns,
            ke.KEY_MAX_ISSUES_TO_DISPLAY: issues,
            ke.KEY_CALLBACK: callback,
            **extra_overrides,
        }

        # 构建初始状态
        state: MetacognitiveOptimizerState = {
            ke.KEY_ID: id,
            ke.KEY_INITIAL_SNAPSHOT: snapshot_data,
            ke.KEY_CURRENT_DATA: {
                ke.KEY_CONTENT: content,
                ke.KEY_LEVEL: lvl,
                ke.KEY_DATA_STORE: {},
            },
            ke.KEY_EXECUTION_TRACE: [],
            ke.KEY_EYE_REPORTS: [],
            ke.KEY_HAND_REPORTS: [],
            ke.KEY_ANALYSIS_REPORTS: [],
            ke.KEY_DAO_REPORTS: [],
            ke.KEY_MAX_LLM_CALLS: llm_calls,
            ke.KEY_LLM_CALLS_COUNT: 0,
            ke.KEY_EXPIRES_AT: time.time() + exp_at,
            ke.KEY_MAX_DEBATE_ROUNDS: debate,
            ke.KEY_MAX_CHARS_PER_TURN: chars,
            ke.KEY_MAX_DEBATE_TURNS_TO_INJECT: turns,
            ke.KEY_MAX_ISSUES_TO_DISPLAY: issues,
            ke.KEY_USER_CLARIFICATION: user_clarification,
            ke.KEY_STATUS: va.VAL_STATUS_RUNNING,
            ke.KEY_MESSAGE: "",
            ke.KEY_METACOGNITION_SIGNATURE: None,
            ke.KEY_REVISED_TEXT: None,
            ke.KEY_REVISION_FIX_RECORDS: [],
        }

        logger.info(
            f"▶️ 启动元认知任务 | {ke.KEY_ID}={id} | 层级={lvl} | 字符限制={chars}",
            module_name=CHINESE_NAME,
        )

        from app.registry.global_singleton_registry import GlobalSingletonRegistry
        registry = await GlobalSingletonRegistry.get_instance()
        graph = await registry.get_metacognition_graph()
        final_state = await asyncio.wait_for(graph.ainvoke(state), timeout=exp_at)

        # 回调通知
        if callback:
            await callback(id, final_state)

        logger.info(
            f"✅ 元认知任务完成 | ID={id} | LLM调用={final_state[ke.KEY_LLM_CALLS_COUNT]}",
            module_name=CHINESE_NAME,
        )

    except Exception as e:
        logger.exception(f"❌ 元认知任务失败 | ID={id} | {str(e)}", module_name=CHINESE_NAME)
        raise


# ==============================================================================
# 后台工作者（消费者）
# ==============================================================================
async def metacognitive_worker():
    """
    元认知任务工作者协程。
    持续监听任务队列和关闭信号：
      - 若有新任务，取出并执行
      - 若收到关闭信号，立即退出（已取出的任务仍会完成）
    每成功调用 `queue.get()`，必须匹配一次 `queue.task_done()`，
    以确保 `queue.join()` 能正确等待所有任务完成。
    """
    queue = get_metacognitive_queue()
    while True:
        try:
            # 同时等待“新任务”或“关闭信号”，谁先到就响应谁
            done, pending = await asyncio.wait(
                [queue.get(), _shutdown_event.wait()],
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            break

        # 取消未完成的等待任务，释放资源
        for p in pending:
            p.cancel()

        # 检查是否收到关闭信号
        if _shutdown_event.is_set():
            break

        # 处理获取到的任务
        try:
            task_data = done.pop().result()
        except Exception as e:
            logger.error(f"获取任务失败: {e}", module_name=CHINESE_NAME)
            continue  # get() 失败，不调用 task_done()

        # 执行任务
        try:
            async with _META_COG_SEMAPHORE:
                await run_metacognitive_loop(**task_data)
        except Exception as e:
            logger.error(f"任务执行失败: {e}", module_name=CHINESE_NAME)
        finally:
            # ⚠️ 关键：只要 queue.get() 成功，就必须调用 task_done()
            queue.task_done()


# ==============================================================================
# 生命周期管理（启动 / 关闭）
# ==============================================================================
def start_metacognition_workers():
    """
    启动元认知执行器的后台工作者。
    必须在应用启动阶段（如 FastAPI @app.on_event("startup")）调用。
    会初始化资源并创建指定数量的并发工作者。
    """
    global _shutdown_event
    if not config.METACOGNITION_ENABLED:
        logger.info("ℹ️ 元认知总开关已关闭，跳过启动", module_name=CHINESE_NAME)
        return
    _init_executor()
    _shutdown_event = asyncio.Event()  # 在事件循环存在后创建
    loop = asyncio.get_running_loop()
    # 启动 worker
    for _ in range(config.METACOGNITION_MAX_WORKER):
        loop.create_task(metacognitive_worker())

    # 启动监控任务
    loop.create_task(monitor_metacognition_queue())
    logger.info("🚀 元认知执行器已启动", module_name=CHINESE_NAME)


async def shutdown_metacognition_workers(graceful: bool = True):
    """
    停止元认知执行器。
    Args:
        graceful: 是否等待队列中已有任务全部完成后再退出。
                  若为 False，则立即标记停止，已取出的任务仍会完成，
                  但队列中剩余任务将被丢弃。
    """
    if _shutdown_event:
        _shutdown_event.set()
        if graceful:
            logger.info("⏳ 等待元认知队列中任务完成...", module_name=CHINESE_NAME)
            await get_metacognitive_queue().join()  # 阻塞直到所有 task_done() 被调用
    logger.info("🛑 元认知工作者已停止", module_name=CHINESE_NAME)


# ==============================================================================
# 任务提交接口（生产者）
# ==============================================================================
async def submit_metacognition_task(
        id: str,
        content: str,
        user_clarification: Optional[str] = None,
        callback: Optional[Callable] = None,
        **extra_overrides,
) -> bool:
    """提交一个元认知任务到执行队列。"""
    # 总开关检查
    if not config.METACOGNITION_ENABLED:
        logger.info(f"元认知总开关已关闭，拒绝新任务: {id}", module_name=CHINESE_NAME)
        return False

    if not id or not content or not isinstance(content, str) or len(content.strip()) == 0:
        logger.warning(f"提交失败：缺少必要字段或内容为空 | {ke.KEY_ID}={id}", module_name=CHINESE_NAME)
        return False

    if _shutdown_event and _shutdown_event.is_set():
        logger.warning(f"系统正在关闭，拒绝新任务: {id}", module_name=CHINESE_NAME)
        return False

    queue = get_metacognitive_queue()
    if queue.full():
        logger.warning(f"队列已满，丢弃任务：{id}", module_name=CHINESE_NAME)
        return False

    already_submitted = await _check_and_mark_submitted(id)
    if already_submitted:
        logger.debug(f"⏭️ 元认知任务已提交过，跳过 | {ke.KEY_ID}={id}", module_name=CHINESE_NAME)
        return True

    task = {
        ke.KEY_ID: id,
        ke.KEY_CONTENT: content,
        ke.KEY_USER_CLARIFICATION: user_clarification,
        ke.KEY_CALLBACK: callback,
        **extra_overrides,
    }

    await queue.put(task)
    logger.info(f"🚀 任务入队：{id} (内容长度={len(content)})", module_name=CHINESE_NAME)
    return True
