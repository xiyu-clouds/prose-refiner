import asyncio
import json
import time
from typing import List, Optional

from app.common import keys as ke
from app.utils.logger import LoggerManager as logger


class SSEManager:
    """
    SSE 全局广播管理器
    事件格式：
    {
        "id": int,            # 全局唯一消息ID（用于前端去重）
        "task_id": str,       # 任务 ID（可选）
        "timestamp": float,   # 时间戳
        "title": str,         # 标题（精炼）
        "content": str,       # 核心信息（精准）
        "meta": dict          # 扩展字段（进度百分比等）
    }
    """
    CHINESE_NAME = "SSE管理"
    _instance = None
    MAX_HISTORY = 1000

    def __init__(self):
        self._connections: List[asyncio.Queue] = []
        self._event_history: List[dict] = []
        self._message_counter = 0
        logger.info("SSE 全局广播管理器已创建", module_name=self.CHINESE_NAME)

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_event_history(self) -> List[dict]:
        """获取最近的事件历史记录，用于跨页面恢复"""
        return list(self._event_history)

    def clear_event_history(self):
        """清空事件历史记录，服务终止时调用"""
        self._event_history = []
        logger.info("SSE 事件历史已清空", module_name=self.CHINESE_NAME)

    def _add_to_history(self, event: str, data: dict):
        """将事件添加到历史记录，超出限制时移除最早的"""
        self._event_history.append({
            "event": event,
            "data": data,
            "timestamp": time.strftime("%m-%d %H:%M:%S", time.localtime())
        })
        while len(self._event_history) > self.MAX_HISTORY:
            self._event_history.pop(0)

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
        self._message_counter += 1
        data['id'] = self._message_counter
        self._add_to_history(event, data)
        message = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        for queue in self._connections:
            await queue.put(message)

    async def send_pipeline_event(self, task_id: str, event: str, data: dict):
        """推送任务状态事件（保留原接口，内部改用 broadcast）"""
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