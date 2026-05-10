import logging
from typing import Optional

import httpx

from src.ports.master_port import MasterPort

logger = logging.getLogger(__name__)


class MasterAPIAdapter(MasterPort):
    def __init__(self, master_url: str, token: str):
        self._master_url = master_url.rstrip("/")
        self._token = token

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
        payload = {
            "bitstream_url": bitstream_url,
            "worker_tag": worker_tag,
            "pipeline_id": pipeline_id,
            "is_test": is_test,
        }
        if tests_url:
            payload["tests_url"] = tests_url
        if fpga_tag:
            payload["fpga_tag"] = fpga_tag
        if test_interface:
            payload["test_interface"] = test_interface

        headers = {"X-API-Token": self._token}
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{self._master_url}/tasks",
                json=payload,
                headers=headers,
            )
            r.raise_for_status()
            return r.json()["task_id"]
