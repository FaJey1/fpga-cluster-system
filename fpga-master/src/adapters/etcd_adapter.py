"""
etcd v3 HTTP gateway adapter — replaces aioetcd3 (incompatible with Python 3.11+).
Uses etcd's gRPC-gateway REST interface on port 2379.
"""
import asyncio
import base64
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple

import httpx

from src.ports.cluster_repository import ClusterRepository

logger = logging.getLogger(__name__)


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


class Lease:
    def __init__(self, lease_id: int):
        self.id = lease_id


class LeaseScope:
    def __init__(self, client: "EtcdHTTPClient", ttl: int):
        self._client = client
        self._ttl = ttl
        self._lease_id: Optional[int] = None
        self._task: Optional[asyncio.Task] = None

    async def __aenter__(self) -> Lease:
        self._lease_id = await self._client._grant_lease(self._ttl)
        self._task = asyncio.create_task(self._keepalive_loop())
        return Lease(self._lease_id)

    async def __aexit__(self, *_):
        if self._task:
            self._task.cancel()

    async def _keepalive_loop(self):
        while True:
            await asyncio.sleep(max(1, self._ttl // 2))
            try:
                await self._client._refresh_lease(self._lease_id)
            except Exception as exc:
                logger.warning("Lease keepalive failed: %s", exc)


class EtcdHTTPClient:
    """Thin async wrapper over the etcd v3 gRPC-gateway REST API."""

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

    async def _grant_lease(self, ttl: int) -> int:
        body = {"TTL": ttl, "ID": 0}
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{self._base}/v3/lease/grant", json=body)
            r.raise_for_status()
            return int(r.json()["ID"])

    async def _refresh_lease(self, lease_id: int) -> None:
        body = {"ID": str(lease_id)}
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(f"{self._base}/v3/lease/keepalive", json=body)

    def grant_lease_scope(self, ttl: int) -> LeaseScope:
        return LeaseScope(self, ttl)


# ── Cluster repository implementation ────────────────────────────────────────

class EtcdAdapter(ClusterRepository):
    def __init__(
        self,
        host: str = "etcd",
        port: int = 2379,
        ttl: int = 10,
        node_name: str = None,
        standalone: bool = False,
    ):
        self.host = host
        self.port = port
        self.ttl = ttl
        self.node_name = node_name
        self.standalone = standalone
        self._client = EtcdHTTPClient(host, port)

    async def register_master(self, node_id: str, info: Dict, ttl: int = None) -> int:
        ttl = ttl or self.ttl
        lease_scope = self._client.grant_lease_scope(ttl)
        async with lease_scope as lease:
            await self._client.put(f"/fpga/masters/{node_id}", json.dumps(info), lease=lease.id)
            return lease.id

    async def register_worker(self, node_id: str, info: Dict, ttl: int = None) -> None:
        # Store without lease (persistent) so workers survive heartbeat gaps
        await self._client.put(f"/fpga/workers/{node_id}", json.dumps(info))

    async def get_masters(self) -> List[Dict]:
        kvs = await self._client.range("/fpga/masters/")
        result = []
        for _, v in kvs:
            try:
                result.append(json.loads(v))
            except Exception:
                pass
        return result

    async def get_workers(self) -> List[Dict]:
        kvs = await self._client.range("/fpga/workers/")
        result = []
        for _, v in kvs:
            try:
                result.append(json.loads(v))
            except Exception:
                pass
        return result

    async def unregister(self, prefix: str, node_id: str) -> None:
        await self._client.delete(f"{prefix}/{node_id}")
