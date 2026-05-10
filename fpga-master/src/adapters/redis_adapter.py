import json
from typing import List, Dict, Tuple
import redis.asyncio as aioredis

from src.ports.queue_repository import QueueRepository
from src.entities.project import Project
from src.entities.task import Task


class RedisQueueAdapter(QueueRepository):
    def __init__(self, redis_url: str, queue_name: str = "fpga:queue"):
        self.redis_url = redis_url
        self.queue_name = queue_name
        self._redis: aioredis.Redis = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    # ── Legacy project queue ────────────────────────────────────────────────

    async def push_project(self, project: Project) -> None:
        r = await self._get_redis()
        await r.rpush(self.queue_name, json.dumps(project.to_dict()))

    async def pop_project(self) -> Project:
        r = await self._get_redis()
        raw = await r.lpop(self.queue_name)
        if raw is None:
            return None
        return Project.from_dict(json.loads(raw))

    async def list_queue(self) -> List[Dict]:
        r = await self._get_redis()
        vals = await r.lrange(self.queue_name, 0, -1)
        return [json.loads(v) for v in vals]

    async def remove_project(self, project_id: str) -> Tuple[bool, Project]:
        r = await self._get_redis()
        for v in await r.lrange(self.queue_name, 0, -1):
            d = json.loads(v)
            if str(d.get("project_id")) == str(project_id):
                await r.lrem(self.queue_name, 0, v)
                return True, Project.from_dict(d)
        return False, None

    # ── Full Task queue (per-tag keys) ──────────────────────────────────────

    async def push_task(self, task: Task) -> None:
        r = await self._get_redis()
        key = f"fpga:tasks:{task.worker_tag}"
        await r.rpush(key, json.dumps(task.to_dict()))

    async def list_tasks_by_tag(self, tag: str) -> List[Dict]:
        r = await self._get_redis()
        vals = await r.lrange(f"fpga:tasks:{tag}", 0, -1)
        return [json.loads(v) for v in vals]

    async def clear_tasks(self) -> None:
        r = await self._get_redis()
        keys = await r.keys("fpga:tasks:*")
        if keys:
            await r.delete(*keys)
