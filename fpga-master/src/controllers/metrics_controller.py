from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

from .main import router, get_usecases, MasterUseCases, Depends

tasks_submitted = Counter("master_tasks_submitted_total", "Tasks submitted")
tasks_completed = Counter("master_tasks_completed_total", "Tasks completed", ["status"])
workers_online = Gauge("master_workers_online", "Online workers")
fpgas_total = Gauge("master_fpgas_total", "Total registered FPGAs")
queue_depth = Gauge("master_queue_depth", "Current queue depth")
api_requests = Counter("master_api_requests_total", "API requests", ["method", "path"])


@router.get("/health", tags=["ops"])
async def health(usecases: MasterUseCases = Depends(get_usecases)):
    workers = await usecases.get_workers()
    quorum = await usecases.quorum_status()
    return {
        "status": "ok",
        "node_id": usecases.node_id,
        "masters_count": quorum["master_count"],
        "workers_count": len(workers),
        "quorum_state": quorum["quorum_state"],
        "quorum_ok": quorum["quorum_ok"],
        "fault_tolerance": quorum["fault_tolerance"],
        "quorum_warning": quorum.get("warning"),
    }


@router.get("/metrics", tags=["ops"], response_class=PlainTextResponse)
async def metrics(usecases: MasterUseCases = Depends(get_usecases)):
    try:
        w = await usecases.get_workers()
        workers_online.set(len(w))
        fpgas = await usecases.get_fpgas()
        fpgas_total.set(len(fpgas))
        q = await usecases.list_queue()
        queue_depth.set(len(q))
    except Exception:
        pass
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
