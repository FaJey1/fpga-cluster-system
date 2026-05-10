import asyncio
import hashlib
import hmac
import json
import logging

import httpx

from src.ports.notifier_port import NotifierPort

logger = logging.getLogger(__name__)


class HttpNotifierAdapter(NotifierPort):
    def __init__(self, timeout: float = 5.0, max_retries: int = 3):
        self._timeout = timeout
        self._max_retries = max_retries

    async def send_callback(self, url: str, payload: dict, secret: str) -> int:
        body = json.dumps(payload, ensure_ascii=False).encode()
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-FPGA-Signature": sig,
        }
        last_exc: Exception = None
        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as c:
                    r = await c.post(url, content=body, headers=headers)
                    return r.status_code
            except Exception as exc:
                last_exc = exc
                wait = 2 ** attempt
                logger.warning("Notify attempt %d/%d failed: %s, retry in %ds",
                               attempt + 1, self._max_retries, exc, wait)
                await asyncio.sleep(wait)
        raise last_exc
