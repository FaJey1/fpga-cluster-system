import logging
import os

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.adapters.etcd_webhook_adapter import EtcdWebhookAdapter
from src.adapters.http_notifier_adapter import HttpNotifierAdapter
from src.adapters.master_api_adapter import MasterAPIAdapter
from src.controllers.cicd_controller import router as cicd_router
from src.controllers.metrics_controller import router as metrics_router
from src.usecases.cicd_usecases import CICDUseCases

logging.basicConfig(level=logging.INFO)

_PUBLIC_PATHS = {"/health", "/metrics", "/docs", "/openapi.json", "/redoc"}

app = FastAPI(title="FPGA CI/CD Bridge", version="1.0.0")
app.include_router(cicd_router)
app.include_router(metrics_router)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path in _PUBLIC_PATHS or request.url.path.startswith("/webhook"):
        return await call_next(request)
    token = request.headers.get("X-API-Token", "")
    expected = os.getenv("CICD_TOKEN", "cicd-secret")
    if token != expected:
        return JSONResponse({"detail": "Требуется X-API-Token"}, status_code=401)
    return await call_next(request)


@app.on_event("startup")
async def startup():
    etcd_host = os.getenv("ETCD_HOST", "etcd")
    etcd_port = int(os.getenv("ETCD_PORT", 2379))
    master_url = os.getenv("MASTER_URL", "http://fpga-master-1:3030")
    root_token = os.getenv("ROOT_TOKEN", "secret-token")

    repo = EtcdWebhookAdapter(host=etcd_host, port=etcd_port)
    notifier = HttpNotifierAdapter()
    master = MasterAPIAdapter(master_url=master_url, token=root_token)

    app.state.usecases = CICDUseCases(repo=repo, notifier=notifier, master=master)


if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=3040, reload=False)
