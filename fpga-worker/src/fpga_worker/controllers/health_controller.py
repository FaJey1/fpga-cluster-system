from fastapi import Depends
from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

from fpga_worker.controllers.main import router, get_usecases
from fpga_worker.usecases.worker_usecases import WorkerUseCases

# Prometheus metrics
tasks_executed = Counter("worker_tasks_executed_total", "Total tasks executed", ["status"])
fpgas_registered = Gauge("worker_fpgas_registered", "Number of registered FPGAs")
fpgas_busy = Gauge("worker_fpgas_busy", "Number of busy FPGAs")


@router.get("/health", tags=["ops"])
async def health(usecases: WorkerUseCases = Depends(get_usecases)):
    status = await usecases.get_worker_status()
    fpgas_registered.set(status["fpga_count"])
    fpgas_busy.set(status["busy_fpga_count"])
    return {"status": "ok", **status}


@router.get("/metrics", tags=["ops"], response_class=PlainTextResponse)
async def metrics():
    return PlainTextResponse(
        generate_latest(), media_type=CONTENT_TYPE_LATEST
    )
