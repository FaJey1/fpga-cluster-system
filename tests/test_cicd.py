"""
Integration tests for fpga-cicd service.
Runs against a live docker-compose stack (http://localhost:3040).
"""
import hashlib
import hmac
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest

from conftest import CICD_URL, CICD_HEADERS

_CICD_TOKEN_HEADERS = {"X-API-Token": "cicd-secret"}
_GITLAB_TOKEN = "gitlab-secret"


# ── Health ────────────────────────────────────────────────────────────────────

class TestCICDHealth:
    def test_health_ok(self):
        r = httpx.get(f"{CICD_URL}/health", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_metrics_ok(self):
        r = httpx.get(f"{CICD_URL}/metrics", timeout=5)
        assert r.status_code == 200
        assert "fpga_cicd_up" in r.text

    def test_unauthorized_without_token(self):
        r = httpx.get(f"{CICD_URL}/subscriptions", timeout=5)
        assert r.status_code == 401


# ── Subscriptions ─────────────────────────────────────────────────────────────

class TestSubscriptions:
    def _subscribe(self, client: httpx.Client, pipeline_id: str, callback_url: str):
        return client.post("/subscribe", json={
            "pipeline_id": pipeline_id,
            "platform": "gitlab",
            "callback_url": callback_url,
            "secret": "test-secret-xyz",
            "pass_threshold": 0.75,
        })

    def test_subscribe_returns_201(self, cicd):
        r = self._subscribe(cicd, f"pipe-{uuid.uuid4()}", "http://example.com/cb")
        assert r.status_code == 201
        data = r.json()
        assert "sub_id" in data
        assert data["platform"] == "gitlab"
        assert data["pass_threshold"] == 0.75

    def test_list_subscriptions(self, cicd):
        pipeline_id = f"pipe-list-{uuid.uuid4()}"
        self._subscribe(cicd, pipeline_id, "http://example.com/cb")
        r = cicd.get("/subscriptions")
        assert r.status_code == 200
        ids = [s["pipeline_id"] for s in r.json()]
        assert pipeline_id in ids

    def test_delete_subscription(self, cicd):
        r = self._subscribe(cicd, f"pipe-del-{uuid.uuid4()}", "http://example.com/cb")
        sub_id = r.json()["sub_id"]

        dr = cicd.delete(f"/subscriptions/{sub_id}")
        assert dr.status_code == 204

        r2 = cicd.get("/subscriptions")
        assert not any(s["sub_id"] == sub_id for s in r2.json())

    def test_delete_nonexistent_returns_404(self, cicd):
        r = cicd.delete(f"/subscriptions/{uuid.uuid4()}")
        assert r.status_code == 404


# ── GitLab webhook ────────────────────────────────────────────────────────────

class TestWebhookGitLab:
    _PAYLOAD = {
        "pipeline_id": "gitlab-pipe-001",
        "bitstream_url": "s3://fpga-artifacts/test/v1.0.0/bitstream.bit",
        "worker_tag": "test",
        "tests_url": "s3://fpga-testvectors/test/v1.0.0/vectors.json",
        "fpga_tag": "fpga-test-001",
    }

    def test_valid_token_dispatches_task(self):
        r = httpx.post(
            f"{CICD_URL}/webhook/gitlab",
            json=self._PAYLOAD,
            headers={"X-Gitlab-Token": _GITLAB_TOKEN},
            timeout=30,
        )
        assert r.status_code == 200
        assert "task_id" in r.json()

    def test_invalid_token_returns_403(self):
        r = httpx.post(
            f"{CICD_URL}/webhook/gitlab",
            json=self._PAYLOAD,
            headers={"X-Gitlab-Token": "wrong"},
            timeout=10,
        )
        assert r.status_code == 403

    def test_missing_bitstream_returns_403(self):
        payload = {"pipeline_id": "no-bitstream", "worker_tag": "dev"}
        r = httpx.post(
            f"{CICD_URL}/webhook/gitlab",
            json=payload,
            headers={"X-Gitlab-Token": _GITLAB_TOKEN},
            timeout=10,
        )
        assert r.status_code == 403


# ── GitHub webhook ────────────────────────────────────────────────────────────

class TestWebhookGitHub:
    _SECRET = "gh-secret-xyz"
    _PIPELINE_ID = "github-pipe-001"

    def _make_signature(self, body: bytes) -> str:
        return "sha256=" + hmac.new(
            self._SECRET.encode(), body, hashlib.sha256
        ).hexdigest()

    def _ensure_subscription(self) -> None:
        httpx.post(
            f"{CICD_URL}/subscribe",
            json={
                "pipeline_id": self._PIPELINE_ID,
                "platform": "github",
                "callback_url": "http://example.com/cb",
                "secret": self._SECRET,
                "pass_threshold": 0.8,
            },
            headers=_CICD_TOKEN_HEADERS,
            timeout=10,
        )

    def test_valid_signature_dispatches_task(self):
        self._ensure_subscription()
        payload = {
            "pipeline_id": self._PIPELINE_ID,
            "bitstream_url": "s3://fpga-artifacts/github/v1.0.0/bitstream.bit",
            "worker_tag": "dev",
        }
        body = json.dumps(payload).encode()
        r = httpx.post(
            f"{CICD_URL}/webhook/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": self._make_signature(body),
            },
            timeout=30,
        )
        assert r.status_code == 200
        assert "task_id" in r.json()

    def test_invalid_signature_returns_403(self):
        self._ensure_subscription()
        payload = {"pipeline_id": self._PIPELINE_ID, "bitstream_url": "s3://x/b.bit", "worker_tag": "dev"}
        body = json.dumps(payload).encode()
        r = httpx.post(
            f"{CICD_URL}/webhook/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=baddeadbeef",
            },
            timeout=10,
        )
        assert r.status_code == 403


# ── Notify endpoint ───────────────────────────────────────────────────────────

class _CallbackHandler(BaseHTTPRequestHandler):
    received: list = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _CallbackHandler.received.append(json.loads(body))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


class TestNotify:
    def test_notify_sends_callback(self, cicd):
        _CallbackHandler.received.clear()

        server = HTTPServer(("0.0.0.0", 9876), _CallbackHandler)
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        pipeline_id = f"pipe-notify-{uuid.uuid4()}"
        cicd.post("/subscribe", json={
            "pipeline_id": pipeline_id,
            "platform": "gitlab",
            "callback_url": "http://host.docker.internal:9876/cb",
            "secret": "notify-secret",
            "pass_threshold": 0.5,
        })

        task_id = str(uuid.uuid4())
        r = httpx.post(
            f"{CICD_URL}/notify/{task_id}",
            json={"pass_rate": 0.9, "status": "completed"},
            headers=_CICD_TOKEN_HEADERS,
            timeout=15,
        )
        assert r.status_code == 200

        t.join(timeout=10)
        server.server_close()
