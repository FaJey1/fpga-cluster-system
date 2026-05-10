from typing import Dict, Any, Optional
from fastapi import HTTPException, Depends
from pydantic import BaseModel

from fpga_worker.controllers.main import router, get_usecases
from fpga_worker.usecases.worker_usecases import WorkerUseCases
from fpga_worker.entities.task import Task


class DispatchTaskRequest(BaseModel):
    task_id: str
    type: str = "deployment"
    mode: str = "PROD"
    bitstream_url: str
    target_fpga_id: str = ""
    worker_tag: str = ""
    priority: int = 2
    pipeline_id: str = ""
    created_at: int = 0
    project_name: str = ""
    is_test: bool = False
    tests_url: Optional[str] = None
    test_interface: str = "usb"
    fpga_tag: Optional[str] = None
    test_config: Optional[Dict[str, Any]] = None


@router.post("/tasks/execute", tags=["tasks"])
async def execute_task(
    payload: DispatchTaskRequest,
    usecases: WorkerUseCases = Depends(get_usecases),
):
    """Master dispatches a task directly to this worker."""
    task = Task.from_dict(payload.model_dump())
    result = await usecases.execute_task(task)
    return result


@router.get("/tasks/status", tags=["tasks"])
async def task_status(usecases: WorkerUseCases = Depends(get_usecases)):
    status = await usecases.get_worker_status()
    return {"running_tasks": status["running_tasks"]}
