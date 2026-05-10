from abc import ABC, abstractmethod
from typing import List, Optional

from src.entities.subscription import WebhookSubscription
from src.entities.cicd_event import CICDEvent


class WebhookRepository(ABC):
    @abstractmethod
    async def save_subscription(self, sub: WebhookSubscription) -> None: ...

    @abstractmethod
    async def get_subscription(self, sub_id: str) -> Optional[WebhookSubscription]: ...

    @abstractmethod
    async def get_subscription_by_pipeline(self, pipeline_id: str) -> Optional[WebhookSubscription]: ...

    @abstractmethod
    async def list_subscriptions(self) -> List[WebhookSubscription]: ...

    @abstractmethod
    async def delete_subscription(self, sub_id: str) -> None: ...

    @abstractmethod
    async def save_event(self, event: CICDEvent) -> None: ...
