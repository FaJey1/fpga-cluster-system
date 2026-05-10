"""Master API tests — queue, cluster state, tasks, FPGA registration."""
import time
import pytest
import httpx
from conftest import MASTER_URL, HEADERS


class TestHealth:
    def test_health_ok(self, master):
        r = master.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "node_id" in data

    def test_metrics_endpoint(self, master):
        r = master.get("/metrics")
        assert r.status_code == 200
        assert b"python_" in r.content or b"master_" in r.content or len(r.content) > 0

    def test_openapi_docs(self, master):
        r = master.get("/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        assert "paths" in schema


class TestQueueOperations:
    def test_queue_initially_empty_or_readable(self, master):
        r = master.get("/get_queue")
        assert r.status_code == 200
        assert "queue" in r.json()

    def test_put_and_list_project(self, master):
        project = {
            "project_id": f"test-{int(time.time())}",
            "project_name": "Network Parser",
            "sources_url": "s3://fpga-artifacts/network-parser/v1.2.3/bitstream.bit",
            "pipiline_id": "pipeline-001",
        }
        r = master.post("/put_project", json=project)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

        r = master.get("/get_queue")
        queue = r.json()["queue"]
        ids = [p["project_id"] for p in queue]
        assert project["project_id"] in ids

        # cleanup
        master.post("/remove_project", json={"project_id": project["project_id"]})

    def test_remove_nonexistent_project(self, master):
        r = master.post("/remove_project", json={"project_id": "nonexistent-999"})
        assert r.status_code == 200
        assert r.json()["removed"] is False

    def test_pop_project(self, master):
        pid = f"pop-{int(time.time())}"
        master.post("/put_project", json={
            "project_id": pid, "project_name": "pop-test",
            "sources_url": "s3://bucket/test.bit", "pipiline_id": "p1",
        })
        r = master.post("/pop_project")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("ok", "empty")


class TestClusterState:
    def test_get_masters(self, master):
        r = master.get("/get_masters")
        assert r.status_code == 200
        masters = r.json()
        assert isinstance(masters, list)
        assert len(masters) >= 1
        assert any(m.get("node_id") == "master-1" for m in masters)

    def test_who_master(self, master):
        r = master.get("/who_master")
        assert r.status_code == 200
        data = r.json()
        assert "is_master" in data
        assert "node_id" in data

    def test_get_workers_returns_list(self, master):
        r = master.get("/get_workers")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestWorkerRegistration:
    def test_register_worker(self, master):
        r = master.post("/workers/register", json={
            "worker_id": "test-worker-api",
            "tags": ["test", "dev"],
            "node_ip": "172.20.0.99",
            "status": "online",
            "max_capacity": 4,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["worker_id"] == "test-worker-api"

    def test_worker_heartbeat(self, master):
        master.post("/workers/register", json={
            "worker_id": "hb-worker",
            "tags": ["test"],
            "node_ip": "",
            "status": "online",
            "max_capacity": 2,
        })
        r = master.post("/workers/hb-worker/heartbeat", json={
            "status": "online",
            "fpga_count": 2,
            "busy_fpga_count": 0,
            "running_tasks": [],
        })
        assert r.status_code == 200


class TestFPGARegistration:
    def test_register_fpga(self, master):
        r = master.post("/fpgas/register", json={
            "fpga_id": "fpga-test-001",
            "worker_id": "worker-1",
            "model": "xc7a100t-1csg324c",
            "vendor": "Xilinx",
            "serial_number": "SN-TEST-001",
            "interface": "usb",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["fpga_id"] == "fpga-test-001"
        assert data["model"] == "xc7a100t-1csg324c"

    def test_list_fpgas(self, master):
        master.post("/fpgas/register", json={
            "fpga_id": "fpga-list-001",
            "worker_id": "worker-1",
            "model": "nexus_a7",
            "vendor": "Lattice",
            "serial_number": "SN-LIST-001",
            "interface": "jtag",
        })
        r = master.get("/fpgas")
        assert r.status_code == 200
        fpgas = r.json()
        assert isinstance(fpgas, list)
        ids = [f["fpga_id"] for f in fpgas]
        assert "fpga-list-001" in ids

    def test_get_fpga_by_id(self, master):
        master.post("/fpgas/register", json={
            "fpga_id": "fpga-get-001",
            "worker_id": "worker-1",
            "model": "xc7a100t-1csg324c",
            "vendor": "Xilinx",
            "serial_number": "SN-GET-001",
            "interface": "ethernet",
        })
        r = master.get("/fpgas/fpga-get-001")
        assert r.status_code == 200
        assert r.json()["fpga_id"] == "fpga-get-001"

    def test_get_nonexistent_fpga(self, master):
        r = master.get("/fpgas/nonexistent-fpga-xyz")
        assert r.status_code == 404


class TestTaskManagement:
    def test_submit_task(self, master):
        r = master.post("/tasks", json={
            "type": "deployment",
            "mode": "PROD",
            "bitstream_url": "s3://fpga-artifacts/network-parser/v1.2.3/bitstream.bit",
            "target_fpga_id": "",
            "worker_tag": "test",
            "priority": 1,
            "pipeline_id": "test-pipeline-001",
        })
        assert r.status_code == 200
        task = r.json()
        assert "task_id" in task
        assert task["status"] == "pending"
        assert task["type"] == "deployment"
        return task["task_id"]

    def test_get_task(self, master):
        r = master.post("/tasks", json={
            "type": "test",
            "mode": "TEST",
            "bitstream_url": "s3://fpga-artifacts/fsm/v2.0.1/bitstream.bit",
            "worker_tag": "test",
            "priority": 2,
            "pipeline_id": "test-pipeline-002",
            "test_config": {"sequences": [1, 2, 3], "timeout": 60, "test_count": 3},
        })
        task_id = r.json()["task_id"]

        r2 = master.get(f"/tasks/{task_id}")
        assert r2.status_code == 200
        assert r2.json()["task_id"] == task_id

    def test_list_tasks(self, master):
        r = master.get("/tasks")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_complete_task(self, master):
        r = master.post("/tasks", json={
            "type": "deployment",
            "mode": "PROD",
            "bitstream_url": "s3://bucket/test.bit",
            "worker_tag": "test",
        })
        task_id = r.json()["task_id"]

        r2 = master.post(f"/tasks/{task_id}/complete", json={
            "status": "success",
            "fpga_id": "fpga-001",
            "bitstream_url": "s3://bucket/test.bit",
            "report_url": "s3://reports/test.json",
        })
        assert r2.status_code == 200

        r3 = master.get(f"/tasks/{task_id}")
        assert r3.json()["status"] == "completed"
