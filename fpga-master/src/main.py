import asyncio
import logging
import os

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.adapters.redis_adapter import RedisQueueAdapter
from src.adapters.etcd_adapter import EtcdAdapter
from src.controllers import router, get_usecases as get_usecases_placeholder
from src.usecases.master_usecases import MasterUseCases
from src.usecases.token_usecases import TokenUseCases
from src.entities.token import ROLE_RANK

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_PUBLIC_PATHS = {
    "/health", "/metrics", "/docs", "/openapi.json", "/redoc",
    "/favicon.ico",
}

app = FastAPI(
    title="FPGA Master Node",
    version="1.0.0",
    description="FPGA Cluster Management — Master API",
)

_usecases: MasterUseCases = None
_token_uc: TokenUseCases = None


async def build_usecases() -> MasterUseCases:
    global _usecases, _token_uc
    if _usecases is not None:
        return _usecases

    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    etcd_host = os.getenv("ETCD_HOST", "localhost")
    etcd_port = int(os.getenv("ETCD_PORT", 2379))
    node_name = os.getenv("NODE_NAME", "master-1")
    standalone = os.getenv("STANDALONE", "true").lower() == "true"

    queue_repo = RedisQueueAdapter(
        f"redis://{redis_host}:{redis_port}", queue_name="fpga:queue"
    )
    cluster_repo = EtcdAdapter(
        host=etcd_host, port=etcd_port, ttl=10,
        node_name=node_name, standalone=standalone,
    )

    _token_uc = TokenUseCases(cluster_repo._client)

    _usecases = MasterUseCases(
        node_id=node_name,
        cluster_repo=cluster_repo,
        queue_repo=queue_repo,
        token_uc=_token_uc,
    )
    return _usecases


app.dependency_overrides[get_usecases_placeholder] = build_usecases
app.include_router(router)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path in _PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
        return await call_next(request)

    if _token_uc is None:
        return await call_next(request)

    token_value = request.headers.get("X-API-Token")
    if not token_value:
        return JSONResponse({"detail": "Требуется заголовок X-API-Token"}, status_code=401)

    token_data = await _token_uc.validate_token(token_value)
    if token_data is None:
        return JSONResponse({"detail": "Недействительный или просроченный токен"}, status_code=401)

    request.state.token = token_data
    request.state.role = token_data.get("role", "viewer")
    return await call_next(request)


@app.on_event("startup")
async def startup():
    usecases = await build_usecases()

    root_token = os.getenv("ROOT_TOKEN", "secret-token")
    await _token_uc.init_root_token(root_token)

    await usecases.join_cluster(
        {"node_id": os.getenv("NODE_NAME", "master-1"), "standalone": True}
    )
    logger.info("Master %s joined cluster", usecases.node_id)
    asyncio.create_task(_scheduler_loop(usecases))


async def _scheduler_loop(usecases: MasterUseCases):
    while True:
        try:
            await usecases.schedule_pending_tasks()
        except Exception as exc:
            logger.error("Scheduler error: %s", exc)
        await asyncio.sleep(5)


if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=3030, reload=False)
