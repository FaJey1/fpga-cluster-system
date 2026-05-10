import json
import logging
import secrets
import time
import uuid
from typing import List, Optional

from src.entities.token import ClusterToken, ROLES

logger = logging.getLogger(__name__)

TOKEN_PREFIX = "/cluster/tokens/"


class TokenUseCases:
    """Manage authentication tokens with optional TTL and role-based access."""

    def __init__(self, etcd_client):
        self._etcd = etcd_client

    async def init_root_token(self, root_token_value: str) -> None:
        """Register root admin token on startup (idempotent)."""
        existing, _ = await self._etcd.get(f"{TOKEN_PREFIX}{root_token_value}")
        if existing is None:
            meta = ClusterToken(
                token_id="root",
                token=root_token_value,
                role="admin",
                description="Root administrator token",
                created_at=int(time.time()),
                expires_at=None,
                is_root=True,
            )
            await self._etcd.put(f"{TOKEN_PREFIX}{root_token_value}", json.dumps(meta.to_dict()))
            logger.info("Root token registered")
        else:
            logger.info("Root token already registered")

    async def issue_token(
        self,
        role: str,
        description: str,
        ttl_seconds: Optional[int] = None,
    ) -> ClusterToken:
        if role not in ROLES:
            raise ValueError(f"Unknown role '{role}'. Valid: {ROLES}")

        token_value = secrets.token_urlsafe(32)
        token_id = str(uuid.uuid4())
        now = int(time.time())
        meta = ClusterToken(
            token_id=token_id,
            token=token_value,
            role=role,
            description=description,
            created_at=now,
            expires_at=now + ttl_seconds if ttl_seconds else None,
            is_root=False,
        )
        key = f"{TOKEN_PREFIX}{token_value}"
        if ttl_seconds:
            lease_id = await self._etcd._grant_lease(ttl_seconds)
            await self._etcd.put(key, json.dumps(meta.to_dict()), lease=lease_id)
        else:
            await self._etcd.put(key, json.dumps(meta.to_dict()))
        logger.info("Token %s issued, role=%s ttl=%s", token_id, role, ttl_seconds)
        return meta

    async def validate_token(self, token_value: str) -> Optional[dict]:
        val, _ = await self._etcd.get(f"{TOKEN_PREFIX}{token_value}")
        if val is None:
            return None
        meta = json.loads(val)
        if meta.get("expires_at") and int(time.time()) > meta["expires_at"]:
            await self._etcd.delete(f"{TOKEN_PREFIX}{token_value}")
            return None
        return meta

    async def list_tokens(self) -> List[dict]:
        kvs = await self._etcd.range(TOKEN_PREFIX)
        result = []
        for _, v in kvs:
            try:
                meta = json.loads(v)
                meta.pop("token", None)
                result.append(meta)
            except Exception:
                pass
        return result

    async def revoke_token(self, token_id: str) -> bool:
        kvs = await self._etcd.range(TOKEN_PREFIX)
        for key, v in kvs:
            try:
                meta = json.loads(v)
                if meta.get("token_id") == token_id and not meta.get("is_root"):
                    await self._etcd.delete(key)
                    logger.info("Token %s revoked", token_id)
                    return True
            except Exception:
                pass
        return False
