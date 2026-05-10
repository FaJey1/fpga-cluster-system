from abc import ABC, abstractmethod
from typing import List, Optional
from fpga_worker.entities.fpga import FPGA


class FPGARepository(ABC):
    @abstractmethod
    async def save(self, fpga: FPGA) -> None: ...

    @abstractmethod
    async def get(self, fpga_id: str) -> Optional[FPGA]: ...

    @abstractmethod
    async def list(self) -> List[FPGA]: ...

    @abstractmethod
    async def update_status(self, fpga_id: str, status: str,
                            bitstream_version: Optional[str] = None) -> None: ...

    @abstractmethod
    async def delete(self, fpga_id: str) -> None: ...
