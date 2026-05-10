"""
Thin async wrapper over etcd v3 gRPC-gateway REST API.
Copied from fpga-master/src/adapters/etcd_adapter.py (EtcdHTTPClient only).
"""
import asyncio
import base64
from typing import Any, Dict, List, Optional, Tuple

import httpx


def _b64e(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def _b64d(s: str) -> str:
    return base64.b64decode(s).decode()


def _prefix_range_end(prefix: str) -> str:
    b = bytearray(prefix.encode())
    for i in range(len(b) - 1, -1, -1):
        if b[i] < 0xFF:
            b[i] += 1
            return base64.b64encode(bytes(b[: i + 1])).decode()
    return base64.b64encode(b"\x00").decode()


class EtcdHTTPClient:
    def __init__(self, host: str, port: int):
        self._base = f"http://{host}:{port}"

    async def put(self, key: str, value: str, lease: Optional[int] = None) -> None:
        body: Dict[str, Any] = {"key": _b64e(key), "value": _b64e(value)}
        if lease:
            body["lease"] = str(lease)
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{self._base}/v3/kv/put", json=body)
            r.raise_for_status()

    async def get(self, key: str) -> Tuple[Optional[str], None]:
        body = {"key": _b64e(key)}
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{self._base}/v3/kv/range", json=body)
            r.raise_for_status()
            kvs = r.json().get("kvs", [])
        if not kvs:
            return None, None
        return _b64d(kvs[0]["value"]), None

    async def range(self, prefix: str) -> List[Tuple[str, str]]:
        body = {"key": _b64e(prefix), "range_end": _prefix_range_end(prefix)}
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{self._base}/v3/kv/range", json=body)
            r.raise_for_status()
            kvs = r.json().get("kvs", [])
        return [(_b64d(kv["key"]), _b64d(kv["value"])) for kv in kvs]

    async def delete(self, key: str) -> None:
        body = {"key": _b64e(key)}
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{self._base}/v3/kv/deleterange", json=body)
            r.raise_for_status()

    async def delete_prefix(self, prefix: str) -> None:
        body = {"key": _b64e(prefix), "range_end": _prefix_range_end(prefix)}
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{self._base}/v3/kv/deleterange", json=body)
            r.raise_for_status()
