from abc import ABC, abstractmethod
from typing import Dict, Any


class MasterClient(ABC):
    @abstractmethod
    async def register_worker(self, worker_id: str, info: Dict[str, Any]) -> None: ...

    @abstractmethod
    async def report_task_result(self, task_id: str, result: Dict[str, Any]) -> None: ...

    @abstractmethod
    async def send_heartbeat(self, worker_id: str, status: Dict[str, Any]) -> None: ...

    @abstractmethod
    async def update_fpga_status(self, fpga_id: str, status: str) -> None: ...
