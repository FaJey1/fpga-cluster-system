from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum


class TaskType(str, Enum):
    DEPLOYMENT = "deployment"
    TEST = "test"
    ROLLBACK = "rollback"


class TaskMode(str, Enum):
    PROD = "PROD"
    TEST = "TEST"


class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    task_id: str
    type: TaskType
    mode: TaskMode
    bitstream_url: str
    target_fpga_id: str
    worker_tag: str
    priority: int
    pipeline_id: str
    created_at: int
    project_name: str = ""
    is_test: bool = False
    tests_url: Optional[str] = None
    test_interface: str = "usb"
    fpga_tag: Optional[str] = None
    test_config: Optional[Dict[str, Any]] = None
    assigned_worker_id: Optional[str] = None
    retry_count: int = 0
    status: TaskStatus = TaskStatus.PENDING

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "type": self.type.value,
            "mode": self.mode.value,
            "bitstream_url": self.bitstream_url,
            "target_fpga_id": self.target_fpga_id,
            "worker_tag": self.worker_tag,
            "priority": self.priority,
            "pipeline_id": self.pipeline_id,
            "created_at": self.created_at,
            "project_name": self.project_name,
            "is_test": self.is_test,
            "tests_url": self.tests_url,
            "test_interface": self.test_interface,
            "fpga_tag": self.fpga_tag,
            "test_config": self.test_config,
            "assigned_worker_id": self.assigned_worker_id,
            "retry_count": self.retry_count,
            "status": self.status.value,
        }

    @staticmethod
    def from_dict(d: dict) -> "Task":
        return Task(
            task_id=d["task_id"],
            type=TaskType(d.get("type", "deployment")),
            mode=TaskMode(d.get("mode", "PROD")),
            bitstream_url=d.get("bitstream_url", ""),
            target_fpga_id=d.get("target_fpga_id", ""),
            worker_tag=d.get("worker_tag", ""),
            priority=int(d.get("priority", 2)),
            pipeline_id=d.get("pipeline_id", ""),
            created_at=int(d.get("created_at", 0)),
            project_name=d.get("project_name", ""),
            is_test=bool(d.get("is_test", False)),
            tests_url=d.get("tests_url"),
            test_interface=d.get("test_interface", "usb"),
            fpga_tag=d.get("fpga_tag"),
            test_config=d.get("test_config"),
            assigned_worker_id=d.get("assigned_worker_id"),
            retry_count=int(d.get("retry_count", 0)),
            status=TaskStatus(d.get("status", "pending")),
        )
