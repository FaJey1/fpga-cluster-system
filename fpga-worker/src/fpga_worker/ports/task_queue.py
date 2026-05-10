from abc import ABC, abstractmethod
from typing import Optional
from fpga_worker.entities.task import Task


class TaskQueue(ABC):
    @abstractmethod
    async def pop(self, worker_tag: str) -> Optional[Task]:
        """Non-blocking pop of next task for given tag. Returns None if empty."""

    @abstractmethod
    async def ack(self, task_id: str) -> None:
        """Acknowledge task completion."""
