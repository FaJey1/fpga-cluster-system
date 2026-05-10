from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional


@dataclass
class CICDEvent:
    event_id: str
    task_id: Optional[str]
    pipeline_id: str
    platform: Literal["gitlab", "github"]
    status: Literal["submitted", "success", "failed", "notify_ok", "notify_err"]
    pass_rate: Optional[float] = None
    http_status: Optional[int] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "task_id": self.task_id,
            "pipeline_id": self.pipeline_id,
            "platform": self.platform,
            "status": self.status,
            "pass_rate": self.pass_rate,
            "http_status": self.http_status,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class CICDTask:
    bitstream_url: str
    worker_tag: str
    is_test: bool
    pipeline_id: str
    tests_url: Optional[str] = None
    fpga_tag: Optional[str] = None
    test_interface: Optional[str] = None
