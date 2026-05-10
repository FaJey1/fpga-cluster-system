import logging
from typing import Dict, Any

import httpx

from fpga_worker.ports.master_client import MasterClient

logger = logging.getLogger(__name__)


class MasterHttpClient(MasterClient):
    def __init__(self, master_url: str, api_token: str = ""):
        self._master_url = master_url.rstrip("/")
        self._headers = {"X-API-Token": api_token} if api_token else {}

    async def register_worker(self, worker_id: str, info: Dict[str, Any]) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{self._master_url}/workers/register",
                json={"worker_id": worker_id, **info},
                headers=self._headers,
            )
            resp.raise_for_status()

    async def report_task_result(self, task_id: str, result: Dict[str, Any]) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{self._master_url}/tasks/{task_id}/complete",
                json=result,
                headers=self._headers,
            )
            if resp.status_code not in (200, 201, 204):
                logger.warning(
                    "Master returned %s for task %s result", resp.status_code, task_id
                )

    async def send_heartbeat(self, worker_id: str, status: Dict[str, Any]) -> None:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"{self._master_url}/workers/{worker_id}/heartbeat",
                json=status,
                headers=self._headers,
            )
            if resp.status_code not in (200, 204):
                logger.warning("Heartbeat returned %s", resp.status_code)

    async def update_fpga_status(self, fpga_id: str, status: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.put(
                    f"{self._master_url}/fpgas/{fpga_id}/status",
                    json={"status": status},
                    headers=self._headers,
                )
        except Exception as exc:
            logger.warning("update_fpga_status failed for %s: %s", fpga_id, exc)
