import asyncio
import logging
import os

import uvicorn
from fastapi import FastAPI

from fpga_worker.adapters.connection_factory import FPGAConnectionFactory
from fpga_worker.adapters.fpga_etcd_adapter import InMemoryFPGARepository
from fpga_worker.adapters.master_http_client import MasterHttpClient
from fpga_worker.adapters.redis_task_adapter import RedisTaskQueue
from fpga_worker.controllers import router, get_usecases
from fpga_worker.usecases.worker_usecases import WorkerUseCases

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="FPGA Worker Node", version="1.0.0")

_usecases: WorkerUseCases = None


async def build_usecases() -> WorkerUseCases:
    global _usecases
    if _usecases is not None:
        return _usecases

    worker_id = os.getenv("WORKER_ID", "worker-1")
    tags = os.getenv("WORKER_TAGS", "test").split(",")
    master_url = os.getenv("MASTER_URL", "http://fpga-master:3030")
    redis_url = f"redis://{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', '6379')}"
    api_token = os.getenv("API_TOKEN", "secret-token")

    fpga_repo = InMemoryFPGARepository()
    task_queue = RedisTaskQueue(redis_url)
    master_client = MasterHttpClient(master_url, api_token)
    conn_factory = FPGAConnectionFactory()

    _usecases = WorkerUseCases(
        worker_id=worker_id,
        tags=tags,
        fpga_repo=fpga_repo,
        task_queue=task_queue,
        master_client=master_client,
        connection_factory=conn_factory,
    )
    return _usecases


app.dependency_overrides[get_usecases] = build_usecases
app.include_router(router)


@app.on_event("startup")
async def startup():
    usecases = await build_usecases()
    # Register with master
    try:
        status = await usecases.get_worker_status()
        await usecases.master_client.register_worker(usecases.worker_id, status)
        logger.info("Registered worker %s with master", usecases.worker_id)
    except Exception as exc:
        logger.warning("Could not register with master on startup: %s", exc)

    # Background: poll queue + heartbeat
    asyncio.create_task(_polling_loop(usecases))
    asyncio.create_task(_heartbeat_loop(usecases))


async def _polling_loop(usecases: WorkerUseCases):
    while True:
        try:
            await usecases.poll_and_execute()
        except Exception as exc:
            logger.error("Polling error: %s", exc)
        await asyncio.sleep(2)


async def _heartbeat_loop(usecases: WorkerUseCases):
    while True:
        await asyncio.sleep(10)
        await usecases.send_heartbeat()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=3031, reload=False)
