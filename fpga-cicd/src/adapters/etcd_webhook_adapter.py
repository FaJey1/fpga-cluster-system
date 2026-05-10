import json
import logging
import uuid
from typing import List, Optional

from src.adapters.etcd_client import EtcdHTTPClient
from src.entities.cicd_event import CICDEvent
from src.entities.subscription import WebhookSubscription
from src.ports.webhook_repository import WebhookRepository

logger = logging.getLogger(__name__)

_SUB_PREFIX = "/cicd/subscriptions/"
_EVT_PREFIX = "/cicd/events/"


class EtcdWebhookAdapter(WebhookRepository):
    def __init__(self, host: str = "etcd", port: int = 2379):
        self._client = EtcdHTTPClient(host, port)

    async def save_subscription(self, sub: WebhookSubscription) -> None:
        await self._client.put(f"{_SUB_PREFIX}{sub.sub_id}", json.dumps(sub.to_dict()))

    async def get_subscription(self, sub_id: str) -> Optional[WebhookSubscription]:
        value, _ = await self._client.get(f"{_SUB_PREFIX}{sub_id}")
        if value is None:
            return None
        return WebhookSubscription.from_dict(json.loads(value))

    async def get_subscription_by_pipeline(self, pipeline_id: str) -> Optional[WebhookSubscription]:
        kvs = await self._client.range(_SUB_PREFIX)
        for _, v in kvs:
            try:
                d = json.loads(v)
                if d.get("pipeline_id") == pipeline_id and d.get("active", True):
                    return WebhookSubscription.from_dict(d)
            except Exception:
                pass
        return None

    async def list_subscriptions(self) -> List[WebhookSubscription]:
        kvs = await self._client.range(_SUB_PREFIX)
        result = []
        for _, v in kvs:
            try:
                result.append(WebhookSubscription.from_dict(json.loads(v)))
            except Exception:
                pass
        return result

    async def delete_subscription(self, sub_id: str) -> None:
        await self._client.delete(f"{_SUB_PREFIX}{sub_id}")

    async def save_event(self, event: CICDEvent) -> None:
        await self._client.put(
            f"{_EVT_PREFIX}{event.event_id}", json.dumps(event.to_dict())
        )
