from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional


@dataclass
class WebhookSubscription:
    sub_id: str
    pipeline_id: str
    platform: Literal["gitlab", "github"]
    callback_url: str
    secret: str
    pass_threshold: float = 0.8
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    active: bool = True
    ttl: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "sub_id": self.sub_id,
            "pipeline_id": self.pipeline_id,
            "platform": self.platform,
            "callback_url": self.callback_url,
            "secret": self.secret,
            "pass_threshold": self.pass_threshold,
            "created_at": self.created_at.isoformat(),
            "active": self.active,
            "ttl": self.ttl,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WebhookSubscription":
        d = dict(d)
        if isinstance(d.get("created_at"), str):
            d["created_at"] = datetime.fromisoformat(d["created_at"])
        return cls(**d)
