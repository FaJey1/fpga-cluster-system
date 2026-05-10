from .main import *
from src.entities.task import Task, TaskType, TaskMode
from typing import Optional


class SubmitTaskIn(BaseModel):
    type: str = "deployment"
    mode: str = "PROD"
    bitstream_url: str
    target_fpga_id: str = ""
    worker_tag: str = "test"
    priority: int = 2
    pipeline_id: str = ""
    project_name: str = ""
    project_board: str = ""
    is_test: bool = False
    tests_url: Optional[str] = None
    test_interface: str = "usb"
    fpga_tag: Optional[str] = None
    test_config: Optional[Dict] = None


class CompleteTaskIn(BaseModel):
    status: str
    fpga_id: str = ""
    bitstream_url: str = ""
    programmed_at: Optional[int] = None
    report_url: str = ""
    test_results: Optional[Dict] = None
    error: str = ""


@router.post("/tasks", tags=["tasks"])
async def submit_task(
    payload: SubmitTaskIn,
    _: str = require_operator,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        task = Task.new(
            task_type=payload.type,
            mode=payload.mode,
            bitstream_url=payload.bitstream_url,
            target_fpga_id=payload.target_fpga_id,
            worker_tag=payload.worker_tag,
            priority=payload.priority,
            pipeline_id=payload.pipeline_id,
            project_name=payload.project_name,
            project_board=payload.project_board,
            is_test=payload.is_test,
            tests_url=payload.tests_url,
            test_interface=payload.test_interface,
            fpga_tag=payload.fpga_tag,
            test_config=payload.test_config,
        )
        return await usecases.submit_task(task)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tasks", tags=["tasks"])
async def clear_tasks(
    _: str = require_admin,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        return await usecases.clear_tasks()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks", tags=["tasks"])
async def list_tasks(
    _: str = require_viewer,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        return await usecases.list_tasks()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}", tags=["tasks"])
async def get_task(
    task_id: str,
    _: str = require_viewer,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        task = await usecases.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return task
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/{task_id}/complete", tags=["tasks"])
async def complete_task(
    task_id: str,
    payload: CompleteTaskIn,
    _: str = require_operator,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        return await usecases.complete_task(task_id, payload.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
