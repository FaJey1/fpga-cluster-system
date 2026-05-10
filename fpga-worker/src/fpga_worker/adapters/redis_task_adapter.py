import json
import logging
from typing import Optional

import redis.asyncio as aioredis

from fpga_worker.entities.task import Task
from fpga_worker.ports.task_queue import TaskQueue

logger = logging.getLogger(__name__)


class RedisTaskQueue(TaskQueue):
    """Polls per-tag Redis lists (LPUSH on master side, LPOP on worker side)."""

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    def _queue_key(self, tag: str) -> str:
        return f"fpga:tasks:{tag}"

    async def pop(self, worker_tag: str) -> Optional[Task]:
        r = await self._get_redis()
        raw = await r.lpop(self._queue_key(worker_tag))
        if raw is None:
            return None
        try:
            return Task.from_dict(json.loads(raw))
        except Exception as exc:
            logger.error("Failed to deserialize task: %s — %s", raw, exc)
            return None

    async def ack(self, task_id: str) -> None:
        pass  # Redis LPOP is already destructive; nothing extra needed
