import hashlib
import hmac
import logging
import uuid
from typing import List, Optional

from src.entities.cicd_event import CICDEvent, CICDTask
from src.entities.subscription import WebhookSubscription
from src.ports.master_port import MasterPort
from src.ports.notifier_port import NotifierPort
from src.ports.webhook_repository import WebhookRepository

logger = logging.getLogger(__name__)


class CICDUseCases:
    def __init__(
        self,
        repo: WebhookRepository,
        notifier: NotifierPort,
        master: MasterPort,
    ):
        self._repo = repo
        self._notifier = notifier
        self._master = master

    async def subscribe(
        self,
        pipeline_id: str,
        platform: str,
        callback_url: str,
        secret: str,
        pass_threshold: float = 0.8,
        ttl: Optional[int] = None,
    ) -> WebhookSubscription:
        sub = WebhookSubscription(
            sub_id=str(uuid.uuid4()),
            pipeline_id=pipeline_id,
            platform=platform,
            callback_url=callback_url,
            secret=secret,
            pass_threshold=pass_threshold,
            ttl=ttl,
        )
        await self._repo.save_subscription(sub)
        return sub

    async def unsubscribe(self, sub_id: str) -> bool:
        sub = await self._repo.get_subscription(sub_id)
        if sub is None:
            return False
        await self._repo.delete_subscription(sub_id)
        return True

    async def list_subscriptions(self) -> List[WebhookSubscription]:
        return await self._repo.list_subscriptions()

    async def handle_gitlab_event(
        self, token: str, payload: dict, expected_token: str
    ) -> Optional[str]:
        if not hmac.compare_digest(token, expected_token):
            return None
        return await self._dispatch_event(payload, "gitlab")

    async def handle_github_event(
        self, signature: str, body: bytes, payload: dict
    ) -> Optional[str]:
        pipeline_id = (
            payload.get("pipeline_id")
            or payload.get("id")
            or payload.get("check_run", {}).get("external_id")
        )
        if not pipeline_id:
            return None
        sub = await self._repo.get_subscription_by_pipeline(str(pipeline_id))
        if sub is None:
            return None
        expected = "sha256=" + hmac.new(
            sub.secret.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        return await self._dispatch_event(payload, "github")

    async def notify_pipeline(self, task_id: str, pass_rate: float, status: str) -> None:
        events = await self._repo.list_subscriptions()
        for sub in events:
            event = await self._submit_notify(sub, task_id, pass_rate, status)
            if event:
                await self._repo.save_event(event)

    async def _dispatch_event(self, payload: dict, platform: str) -> Optional[str]:
        pipeline_id = str(
            payload.get("pipeline_id")
            or payload.get("object_attributes", {}).get("id")
            or payload.get("id")
            or ""
        )
        bitstream_url = (
            payload.get("bitstream_url")
            or payload.get("variables", {}).get("BITSTREAM_URL")
            or payload.get("environment", {}).get("BITSTREAM_URL")
            or ""
        )
        worker_tag = payload.get("worker_tag") or payload.get("variables", {}).get("WORKER_TAG", "dev")
        tests_url = payload.get("tests_url") or payload.get("variables", {}).get("TESTS_URL")
        is_test = bool(tests_url)
        fpga_tag = payload.get("fpga_tag") or payload.get("variables", {}).get("FPGA_TAG")
        test_interface = payload.get("test_interface") or payload.get("variables", {}).get("TEST_INTERFACE")

        if not bitstream_url:
            logger.warning("No bitstream_url in %s webhook payload", platform)
            return None

        task_id = await self._master.submit_task(
            bitstream_url=bitstream_url,
            worker_tag=worker_tag,
            pipeline_id=pipeline_id,
            is_test=is_test,
            tests_url=tests_url,
            fpga_tag=fpga_tag,
            test_interface=test_interface,
        )

        event = CICDEvent(
            event_id=str(uuid.uuid4()),
            task_id=task_id,
            pipeline_id=pipeline_id,
            platform=platform,
            status="submitted",
        )
        await self._repo.save_event(event)
        return task_id

    async def _submit_notify(
        self, sub: WebhookSubscription, task_id: str, pass_rate: float, status: str
    ) -> Optional[CICDEvent]:
        passed = pass_rate >= sub.pass_threshold
        payload = {
            "task_id": task_id,
            "pipeline_id": sub.pipeline_id,
            "status": "success" if passed else "failed",
            "pass_rate": pass_rate,
        }
        try:
            http_status = await self._notifier.send_callback(
                sub.callback_url, payload, sub.secret
            )
            notify_status = "notify_ok" if 200 <= http_status < 300 else "notify_err"
        except Exception as exc:
            logger.error("Notify failed for sub %s: %s", sub.sub_id, exc)
            http_status = None
            notify_status = "notify_err"

        return CICDEvent(
            event_id=str(uuid.uuid4()),
            task_id=task_id,
            pipeline_id=sub.pipeline_id,
            platform=sub.platform,
            status=notify_status,
            pass_rate=pass_rate,
            http_status=http_status,
        )
