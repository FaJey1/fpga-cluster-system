import logging
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from src.usecases.cicd_usecases import CICDUseCases

logger = logging.getLogger(__name__)
router = APIRouter()

_GITLAB_TOKEN = os.getenv("GITLAB_WEBHOOK_TOKEN", "gitlab-secret")


def get_uc(request: Request) -> CICDUseCases:
    return request.app.state.usecases


class SubscribeRequest(BaseModel):
    pipeline_id: str
    platform: str
    callback_url: str
    secret: str
    pass_threshold: float = 0.8
    ttl: Optional[int] = None


@router.post("/subscribe", status_code=201)
async def subscribe(body: SubscribeRequest, uc: CICDUseCases = Depends(get_uc)):
    sub = await uc.subscribe(
        pipeline_id=body.pipeline_id,
        platform=body.platform,
        callback_url=body.callback_url,
        secret=body.secret,
        pass_threshold=body.pass_threshold,
        ttl=body.ttl,
    )
    return sub.to_dict()


@router.get("/subscriptions")
async def list_subscriptions(uc: CICDUseCases = Depends(get_uc)):
    subs = await uc.list_subscriptions()
    return [s.to_dict() for s in subs]


@router.delete("/subscriptions/{sub_id}", status_code=204)
async def unsubscribe(sub_id: str, uc: CICDUseCases = Depends(get_uc)):
    ok = await uc.unsubscribe(sub_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Subscription not found")


@router.post("/webhook/gitlab")
async def webhook_gitlab(
    request: Request,
    x_gitlab_token: str = Header(default=""),
    uc: CICDUseCases = Depends(get_uc),
):
    payload = await request.json()
    task_id = await uc.handle_gitlab_event(x_gitlab_token, payload, _GITLAB_TOKEN)
    if task_id is None:
        raise HTTPException(status_code=403, detail="Invalid token or no bitstream_url")
    return {"task_id": task_id}


@router.post("/webhook/github")
async def webhook_github(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
    uc: CICDUseCases = Depends(get_uc),
):
    body = await request.body()
    payload = await request.json()
    task_id = await uc.handle_github_event(x_hub_signature_256, body, payload)
    if task_id is None:
        raise HTTPException(status_code=403, detail="Invalid signature or no subscription")
    return {"task_id": task_id}


@router.post("/notify/{task_id}")
async def notify(
    task_id: str,
    request: Request,
    uc: CICDUseCases = Depends(get_uc),
):
    import asyncio
    body = await request.json()
    pass_rate = float(body.get("pass_rate", 0.0))
    status = body.get("status", "completed")
    asyncio.create_task(uc.notify_pipeline(task_id, pass_rate, status))
    return {"ok": True}
