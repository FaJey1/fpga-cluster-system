from .main import *
import time


class WorkerRegisterIn(BaseModel):
    worker_id: str
    tags: List[str] = []
    node_ip: str = ""
    status: str = "online"
    max_capacity: int = 4
    current_load: int = 0
    fpga_devices: List[Dict] = []


class HeartbeatIn(BaseModel):
    status: str = "online"
    fpga_count: int = 0
    busy_fpga_count: int = 0
    running_tasks: List[str] = []
    last_heartbeat: int = 0
    current_load: int = 0
    tags: List[str] = []


@router.post("/workers/register", tags=["workers"])
async def register_worker(
    payload: WorkerRegisterIn,
    _: str = require_operator,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        info = payload.model_dump()
        info["last_heartbeat"] = int(time.time())
        return await usecases.register_worker(payload.worker_id, info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/workers/{worker_id}", tags=["workers"])
async def delete_worker(
    worker_id: str,
    _: str = require_admin,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        return await usecases.delete_worker(worker_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workers/{worker_id}/heartbeat", tags=["workers"])
async def worker_heartbeat(
    worker_id: str,
    payload: HeartbeatIn,
    _: str = require_operator,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        return await usecases.update_worker_heartbeat(worker_id, payload.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
