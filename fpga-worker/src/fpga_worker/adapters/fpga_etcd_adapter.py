"""In-memory FPGA repository (etcd-backed in prod; memory for tests)."""
import json
import logging
from typing import Dict, List, Optional

from fpga_worker.entities.fpga import FPGA, FPGAStatus
from fpga_worker.ports.fpga_repository import FPGARepository

logger = logging.getLogger(__name__)


class InMemoryFPGARepository(FPGARepository):
    """Stores FPGA state in-process memory. Suitable for single-worker node."""

    def __init__(self):
        self._store: Dict[str, FPGA] = {}

    async def save(self, fpga: FPGA) -> None:
        self._store[fpga.fpga_id] = fpga

    async def get(self, fpga_id: str) -> Optional[FPGA]:
        return self._store.get(fpga_id)

    async def list(self) -> List[FPGA]:
        return list(self._store.values())

    async def update_status(
        self,
        fpga_id: str,
        status: str,
        bitstream_version: Optional[str] = None,
    ) -> None:
        fpga = self._store.get(fpga_id)
        if fpga:
            fpga.status = FPGAStatus(status)
            if bitstream_version is not None:
                fpga.current_bitstream_version = bitstream_version

    async def delete(self, fpga_id: str) -> None:
        self._store.pop(fpga_id, None)
