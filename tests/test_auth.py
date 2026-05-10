"""
Тесты аутентификации и RBAC.

Проверяются: выпуск токенов, TTL, ролевой доступ, отзыв,
проверка /auth/whoami, защита роутов от неавторизованных запросов.
"""
import time
import pytest
import httpx
from conftest import MASTER_URL, HEADERS


ROOT_HEADERS = HEADERS  # {"X-API-Token": "secret-token"} — это root/admin


def _h(token: str) -> dict:
    return {"X-API-Token": token}


class TestTokenIssuance:
    def test_issue_operator_token(self):
        r = httpx.post(
            f"{MASTER_URL}/auth/tokens",
            json={"role": "operator", "description": "CI/CD token"},
            headers=ROOT_HEADERS, timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["role"] == "operator"
        assert "token" in data
        assert data["token_id"] != ""
        assert data["expires_at"] is None

    def test_issue_viewer_token(self):
        r = httpx.post(
            f"{MASTER_URL}/auth/tokens",
            json={"role": "viewer", "description": "Monitoring dashboard"},
            headers=ROOT_HEADERS, timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["role"] == "viewer"

    def test_issue_token_with_ttl(self):
        r = httpx.post(
            f"{MASTER_URL}/auth/tokens",
            json={"role": "operator", "description": "Short-lived", "ttl_seconds": 3600},
            headers=ROOT_HEADERS, timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["expires_at"] is not None
        assert data["expires_at"] > int(time.time())

    def test_issue_invalid_role_rejected(self):
        r = httpx.post(
            f"{MASTER_URL}/auth/tokens",
            json={"role": "superuser"},
            headers=ROOT_HEADERS, timeout=10,
        )
        assert r.status_code == 400

    def test_non_admin_cannot_issue_token(self):
        # First issue an operator token
        r1 = httpx.post(
            f"{MASTER_URL}/auth/tokens",
            json={"role": "operator", "description": "for rbac test"},
            headers=ROOT_HEADERS, timeout=10,
        )
        op_token = r1.json()["token"]

        # Operator tries to issue another token — must be forbidden
        r2 = httpx.post(
            f"{MASTER_URL}/auth/tokens",
            json={"role": "viewer"},
            headers=_h(op_token), timeout=10,
        )
        assert r2.status_code == 403

    def test_viewer_cannot_issue_token(self):
        r1 = httpx.post(
            f"{MASTER_URL}/auth/tokens",
            json={"role": "viewer", "description": "viewer for rbac"},
            headers=ROOT_HEADERS, timeout=10,
        )
        v_token = r1.json()["token"]

        r2 = httpx.post(
            f"{MASTER_URL}/auth/tokens",
            json={"role": "viewer"},
            headers=_h(v_token), timeout=10,
        )
        assert r2.status_code == 403


class TestTokenList:
    def test_list_tokens_as_admin(self):
        r = httpx.get(f"{MASTER_URL}/auth/tokens", headers=ROOT_HEADERS, timeout=10)
        assert r.status_code == 200
        tokens = r.json()
        assert isinstance(tokens, list)
        # Root token must be present
        roles = [t["role"] for t in tokens]
        assert "admin" in roles

    def test_list_tokens_hides_plaintext(self):
        r = httpx.get(f"{MASTER_URL}/auth/tokens", headers=ROOT_HEADERS, timeout=10)
        for tok in r.json():
            assert "token" not in tok, "Plaintext token должен быть скрыт в листинге"

    def test_non_admin_cannot_list_tokens(self):
        r1 = httpx.post(
            f"{MASTER_URL}/auth/tokens",
            json={"role": "operator", "description": "list-test"},
            headers=ROOT_HEADERS, timeout=10,
        )
        op_token = r1.json()["token"]
        r2 = httpx.get(f"{MASTER_URL}/auth/tokens", headers=_h(op_token), timeout=10)
        assert r2.status_code == 403


class TestTokenRevoke:
    def test_revoke_token(self):
        # Issue a token to revoke
        r1 = httpx.post(
            f"{MASTER_URL}/auth/tokens",
            json={"role": "viewer", "description": "to-be-revoked"},
            headers=ROOT_HEADERS, timeout=10,
        )
        tok_data = r1.json()
        token_id = tok_data["token_id"]
        token_val = tok_data["token"]

        # Verify it works
        r_before = httpx.get(f"{MASTER_URL}/auth/whoami", headers=_h(token_val), timeout=10)
        assert r_before.status_code == 200

        # Revoke
        r2 = httpx.delete(
            f"{MASTER_URL}/auth/tokens/{token_id}",
            headers=ROOT_HEADERS, timeout=10,
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "revoked"

        # After revoke — token must be invalid
        r_after = httpx.get(f"{MASTER_URL}/auth/whoami", headers=_h(token_val), timeout=10)
        assert r_after.status_code == 401

    def test_cannot_revoke_root_token(self):
        r = httpx.delete(
            f"{MASTER_URL}/auth/tokens/root",
            headers=ROOT_HEADERS, timeout=10,
        )
        assert r.status_code == 404

    def test_revoke_nonexistent_returns_404(self):
        r = httpx.delete(
            f"{MASTER_URL}/auth/tokens/does-not-exist",
            headers=ROOT_HEADERS, timeout=10,
        )
        assert r.status_code == 404


class TestWhoami:
    def test_whoami_returns_role(self):
        r = httpx.get(f"{MASTER_URL}/auth/whoami", headers=ROOT_HEADERS, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["role"] == "admin"
        assert data["token_id"] == "root"

    def test_whoami_for_issued_token(self):
        r1 = httpx.post(
            f"{MASTER_URL}/auth/tokens",
            json={"role": "operator", "description": "whoami-test"},
            headers=ROOT_HEADERS, timeout=10,
        )
        op_token = r1.json()["token"]

        r2 = httpx.get(f"{MASTER_URL}/auth/whoami", headers=_h(op_token), timeout=10)
        assert r2.status_code == 200
        assert r2.json()["role"] == "operator"

    def test_whoami_without_token_returns_401(self):
        r = httpx.get(f"{MASTER_URL}/auth/whoami", timeout=10)
        assert r.status_code == 401

    def test_whoami_with_invalid_token_returns_401(self):
        r = httpx.get(f"{MASTER_URL}/auth/whoami",
                      headers={"X-API-Token": "invalid-token-xyz"}, timeout=10)
        assert r.status_code == 401


class TestRBAC:
    """Проверка ролевого доступа к защищённым эндпоинтам."""

    def _issue(self, role: str) -> str:
        r = httpx.post(
            f"{MASTER_URL}/auth/tokens",
            json={"role": role, "description": f"rbac-{role}"},
            headers=ROOT_HEADERS, timeout=10,
        )
        return r.json()["token"]

    def test_viewer_can_read_tasks(self):
        t = self._issue("viewer")
        r = httpx.get(f"{MASTER_URL}/tasks", headers=_h(t), timeout=10)
        assert r.status_code == 200

    def test_viewer_cannot_submit_task(self):
        t = self._issue("viewer")
        r = httpx.post(
            f"{MASTER_URL}/tasks",
            json={"type": "deployment", "mode": "PROD",
                  "bitstream_url": "s3://x/y.bit", "worker_tag": "test"},
            headers=_h(t), timeout=10,
        )
        assert r.status_code == 403

    def test_operator_can_submit_task(self):
        t = self._issue("operator")
        r = httpx.post(
            f"{MASTER_URL}/tasks",
            json={"type": "deployment", "mode": "PROD",
                  "bitstream_url": "s3://x/y.bit", "worker_tag": "test", "priority": 1},
            headers=_h(t), timeout=10,
        )
        assert r.status_code == 200

    def test_viewer_can_read_workers(self):
        t = self._issue("viewer")
        r = httpx.get(f"{MASTER_URL}/get_workers", headers=_h(t), timeout=10)
        assert r.status_code == 200

    def test_viewer_cannot_register_worker(self):
        t = self._issue("viewer")
        r = httpx.post(
            f"{MASTER_URL}/workers/register",
            json={"worker_id": "rbac-w", "tags": ["test"],
                  "node_ip": "1.2.3.4", "status": "online", "max_capacity": 2},
            headers=_h(t), timeout=10,
        )
        assert r.status_code == 403

    def test_operator_can_register_worker(self):
        t = self._issue("operator")
        r = httpx.post(
            f"{MASTER_URL}/workers/register",
            json={"worker_id": f"rbac-w-op-{int(time.time())}",
                  "tags": ["test"], "node_ip": "1.2.3.4",
                  "status": "online", "max_capacity": 2},
            headers=_h(t), timeout=10,
        )
        assert r.status_code == 200

    def test_no_token_returns_401(self):
        r = httpx.get(f"{MASTER_URL}/tasks", timeout=10)
        assert r.status_code == 401

    def test_health_is_public(self):
        """health и metrics доступны без токена."""
        r = httpx.get(f"{MASTER_URL}/health", timeout=10)
        assert r.status_code == 200

    def test_metrics_is_public(self):
        r = httpx.get(f"{MASTER_URL}/metrics", timeout=10)
        assert r.status_code == 200
