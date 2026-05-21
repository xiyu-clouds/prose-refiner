import asyncio
import json
import threading
import time
from typing import List, Optional
import httpcore
import httpx
from app.common import keys as ke
from app.config.config import config
from app.utils.logger import LoggerManager as logger


class SSEManager:
    """
    所有 SSE 事件都遵循同一个格式：
    {
        "task_id": str,       # 任务 ID
        "timestamp": float,   # 由 send_pipeline_event 自动注入
        "title": str,         # 标题
        "content": str,       # 核心信息
        "meta": dict          # 扩展字段
    }
    """
    CHINESE_NAME = "SSE管理"
    _instance = None

    def __init__(self):
        self._connections: List[asyncio.Queue] = []
        self._latest_event: Optional[str] = None
        self._proxy_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()  # 优雅停止信号
        self._proxy_backend_url: str = config.PROXY_BACKEND_SSE_URL or "http://127.0.0.1:8000/api/sse"
        logger.info("SSE 全局广播管理器已创建", module_name=self.CHINESE_NAME)

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ========== 代理启停 ==========
    def start_proxy(self, backend_url: str = None):
        """启动代理线程，由 FastAPI 生命周期调用"""
        if backend_url:
            self._proxy_backend_url = backend_url
        if self._proxy_thread and self._proxy_thread.is_alive():
            return
        self._stop_event.clear()
        self._proxy_thread = threading.Thread(target=self._fetch_backend_events, daemon=True)
        self._proxy_thread.start()
        logger.info(f"SSE 代理线程已启动，后端地址：{backend_url}", module_name=self.CHINESE_NAME)

    def stop_proxy(self):
        """优雅停止代理线程，由 FastAPI 生命周期调用"""
        self._stop_event.set()
        if self._proxy_thread and self._proxy_thread.is_alive():
            self._proxy_thread.join(timeout=5)
        logger.info("SSE 代理线程已停止", module_name=self.CHINESE_NAME)

    # ========== 后台线程逻辑 ==========
    def _fetch_backend_events(self):
        # 等待 Uvicorn 完全就绪，避免秒级启动失败
        time.sleep(3)

        # 从默认重试配置读取参数
        retry_cfg = config.DEFAULT_RETRY_CONFIG
        max_retries = retry_cfg.get(ke.KEY_MAX_RETRIES, 3)
        enable_exp_backoff = retry_cfg.get(ke.KEY_ENABLE_EXP_BACKOFF, True)
        exp_multiplier = retry_cfg.get(ke.KEY_EXP_MULTIPLIER, 1)
        exp_max_wait = retry_cfg.get(ke.KEY_EXP_MAX_WAIT, 10)
        min_wait = retry_cfg.get(ke.KEY_MIN_WAIT, 0.1)

        attempt = 0
        while not self._stop_event.is_set():
            try:
                with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=None, write=None, pool=None)) as client:
                    with client.stream("GET", self._proxy_backend_url) as r:
                        if r.status_code != 200:
                            logger.error(f"SSE 代理连接失败：状态码 {r.status_code}", module_name=self.CHINESE_NAME)
                            raise httpx.HTTPStatusError(
                                f"Unexpected status {r.status_code}",
                                request=r.request,
                                response=r
                            )

                        logger.info("SSE 代理已成功连接后端 SSE 流", module_name=self.CHINESE_NAME)
                        event_name = None
                        data_str = ""
                        for line in r.iter_lines():
                            if self._stop_event.is_set():
                                break
                            line = line.strip()
                            if line.startswith("event: "):
                                event_name = line[7:]
                            elif line.startswith("data: "):
                                data_str = line[6:]
                            elif line == "" and event_name is not None and data_str:
                                full_message = f"event: {event_name}\ndata: {data_str}\n\n"
                                self._latest_event = full_message
                                for queue in self._connections:
                                    try:
                                        loop = asyncio.get_event_loop()
                                        loop.call_soon_threadsafe(queue.put_nowait, full_message)
                                    except Exception:
                                        pass
                                event_name = None
                                data_str = ""
                        # 正常结束（流关闭或无数据），退出重试循环，不再重连
                        break

            except (httpx.ConnectError, httpx.HTTPStatusError, httpx.ReadError,
                    httpx.RemoteProtocolError, httpcore.ConnectError, httpcore.ReadError,
                    httpcore.RemoteProtocolError, httpx.NetworkError) as e:
                attempt += 1
                if attempt > max_retries:
                    logger.error("SSE 代理重试耗尽，无法连接后端，请检查服务是否正常启动", module_name=self.CHINESE_NAME)
                    break

                # 计算等待时间
                if enable_exp_backoff:
                    wait = min(min_wait * (exp_multiplier ** (attempt - 1)), exp_max_wait)
                else:
                    wait = min_wait

                logger.warning(
                    f"SSE 代理连接失败，第 {attempt}/{max_retries} 次重试，等待 {wait:.1f}s | 错误: {e}", module_name=self.CHINESE_NAME
                )
                time.sleep(wait)
            except Exception as e:
                logger.error(f"SSE 代理流读取异常：{e}，将退出代理", module_name=self.CHINESE_NAME)
                break

    # ========== 补发缓存 ==========
    def get_latest_event(self) -> Optional[str]:
        return self._latest_event

    def register(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        self._connections.append(queue)
        logger.info(f"SSE 客户端已注册，当前连接数: {len(self._connections)}", module_name=self.CHINESE_NAME)
        return queue

    def unregister(self, queue: asyncio.Queue):
        self._connections = [q for q in self._connections if q is not queue]
        logger.info(f"SSE 客户端已注销，当前连接数: {len(self._connections)}", module_name=self.CHINESE_NAME)

    async def broadcast(self, event: str, data: dict):
        """全局广播事件到所有已注册的 SSE 连接"""
        message = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        for queue in self._connections:
            await queue.put(message)

    async def send_pipeline_event(self, task_id: str, event: str, data: dict):
        """推送流水线状态事件（保留原接口，内部改用 broadcast）"""
        await self.broadcast(
            event=event,
            data={
                ke.KEY_TASK_ID: task_id,
                ke.KEY_TIMESTAMP: time.time(),
                **data
            }
        )


def get_sse_manager() -> SSEManager:
    return SSEManager.get_instance()
