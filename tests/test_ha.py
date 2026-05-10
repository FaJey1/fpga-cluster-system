"""
High-availability tests — 3-master quorum (valid odd HA configuration).
Verifies shared etcd state, leader election, and quorum health reporting.
"""
import time
import pytest
import httpx
from conftest import MASTER_URL, MASTER2_URL, MASTER3_URL, HEADERS

ALL_MASTERS = [MASTER_URL, MASTER2_URL, MASTER3_URL]


class TestMultipleMasters:
    def test_all_three_masters_healthy(self):
        for url in ALL_MASTERS:
            r = httpx.get(f"{url}/health", headers=HEADERS, timeout=10)
            assert r.status_code == 200, f"{url} not healthy"

    def test_quorum_state_is_ha_with_three_masters(self):
        """With 3 masters, quorum_state must be 'ha' and fault_tolerance = 1."""
        r = httpx.get(f"{MASTER_URL}/health", headers=HEADERS, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["quorum_ok"] is True
        assert data["quorum_state"] == "ha"
        assert data["fault_tolerance"] == 1
        assert data["quorum_warning"] is None

    def test_all_masters_report_same_quorum_state(self):
        for url in ALL_MASTERS:
            r = httpx.get(f"{url}/health", headers=HEADERS, timeout=10)
            assert r.status_code == 200
            data = r.json()
            assert data["quorum_state"] == "ha", f"{url} quorum_state mismatch"
            assert data["quorum_ok"] is True

    def test_masters_count_is_three(self):
        r = httpx.get(f"{MASTER_URL}/get_masters", headers=HEADERS, timeout=10)
        assert r.status_code == 200
        masters = r.json()
        assert len(masters) == 3, f"Expected 3 masters, got {len(masters)}: {masters}"

    def test_masters_share_state(self):
        """Register a worker via master-1, verify it appears on master-2 and master-3."""
        worker_id = f"ha-worker-{int(time.time())}"
        r1 = httpx.post(
            f"{MASTER_URL}/workers/register",
            json={"worker_id": worker_id, "tags": ["ha-test"], "node_ip": "172.20.0.99",
                  "status": "online", "max_capacity": 2},
            headers=HEADERS, timeout=10,
        )
        assert r1.status_code == 200

        time.sleep(1)
        for url in (MASTER2_URL, MASTER3_URL):
            r = httpx.get(f"{url}/get_workers", headers=HEADERS, timeout=10)
            assert r.status_code == 200
            worker_ids = [w.get("worker_id") for w in r.json()]
            assert worker_id in worker_ids, f"Worker not visible on {url}"

    def test_queue_shared_between_masters(self):
        """Push project via master-1, read it via master-2 and master-3."""
        pid = f"ha-proj-{int(time.time())}"
        httpx.post(
            f"{MASTER_URL}/put_project",
            json={"project_id": pid, "project_name": "ha-test",
                  "sources_url": "s3://bucket/ha.bit", "pipiline_id": "ha-001"},
            headers=HEADERS, timeout=10,
        )
        time.sleep(0.5)
        for url in (MASTER2_URL, MASTER3_URL):
            r = httpx.get(f"{url}/get_queue", headers=HEADERS, timeout=10)
            queue = r.json().get("queue", [])
            ids = [p["project_id"] for p in queue]
            assert pid in ids, f"Project not visible on {url}"

        httpx.post(f"{MASTER_URL}/remove_project",
                   json={"project_id": pid}, headers=HEADERS, timeout=5)

    def test_who_master_returns_valid_response_on_all(self):
        leaders = []
        for url in ALL_MASTERS:
            r = httpx.get(f"{url}/who_master", headers=HEADERS, timeout=10)
            assert r.status_code == 200
            data = r.json()
            assert "is_master" in data
            assert "node_id" in data
            assert data["quorum_state"] == "ha"
            assert data["fault_tolerance"] == 1
            if data["is_master"]:
                leaders.append(data["node_id"])
        assert len(leaders) == 1, f"Expected exactly 1 leader, got: {leaders}"

    def test_task_submitted_to_master1_visible_on_all(self):
        r1 = httpx.post(
            f"{MASTER_URL}/tasks",
            json={"type": "deployment", "mode": "PROD",
                  "bitstream_url": "s3://bucket/ha-task.bit", "worker_tag": "ha-test",
                  "priority": 2, "pipeline_id": "ha-pipeline"},
            headers=HEADERS, timeout=10,
        )
        assert r1.status_code == 200
        task_id = r1.json()["task_id"]

        time.sleep(1)
        for url in (MASTER2_URL, MASTER3_URL):
            r = httpx.get(f"{url}/tasks/{task_id}", headers=HEADERS, timeout=10)
            assert r.status_code == 200
            assert r.json()["task_id"] == task_id


class TestQuorumHealth:
    def test_quorum_endpoint(self):
        r = httpx.get(f"{MASTER_URL}/quorum", headers=HEADERS, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["master_count"] == 3
        assert data["quorum_ok"] is True
        assert data["quorum_state"] == "ha"
        assert data["fault_tolerance"] == 1
        assert data["warning"] is None
