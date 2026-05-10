from abc import ABC, abstractmethod
from typing import Optional


class MasterPort(ABC):
    @abstractmethod
    async def submit_task(
        self,
        bitstream_url: str,
        worker_tag: str,
        pipeline_id: str,
        is_test: bool = False,
        tests_url: Optional[str] = None,
        fpga_tag: Optional[str] = None,
        test_interface: Optional[str] = None,
    ) -> str:
        """Submit task to fpga-master. Returns task_id."""
        ...
