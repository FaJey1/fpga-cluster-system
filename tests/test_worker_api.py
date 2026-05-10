"""Worker API tests — FPGA registration, task dispatch, health."""
import time
import pytest
import httpx
from conftest import WORKER1_URL, WORKER2_URL, EMU1_URL


class TestWorkerHealth:
    def test_worker1_health(self, worker1):
        r = worker1.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("ok", "online")
        assert "worker_id" in data

    def test_worker2_health(self, worker2):
        r = worker2.get("/health")
        assert r.status_code == 200

    def test_worker_metrics(self, worker1):
        r = worker1.get("/metrics")
        assert r.status_code == 200


class TestFPGARegistrationOnWorker:
    def test_register_fpga_usb(self, worker1):
        r = worker1.post("/fpgas/register", json={
            "fpga_id": "fpga-w1-usb-001",
            "model": "xc7a100t-1csg324c",
            "vendor": "Xilinx",
            "serial_number": "SN-W1-001",
            "interface": "usb",
            "emulator_url": EMU1_URL,
            "specs": {
                "debugging_board": "nexus_a7",
                "fpga_crystal": "xc7a100t-1csg324c",
                "dsp_slices": 240,
                "internal_freq_mhz": 300,
                "ddr_memory_mb": 4096,
            },
        })
        assert r.status_code == 200
        data = r.json()
        assert data["fpga_id"] == "fpga-w1-usb-001"
        assert data["interface"] == "usb"
        assert data["worker_id"] == "worker-1"

    def test_register_fpga_ethernet(self, worker1):
        r = worker1.post("/fpgas/register", json={
            "fpga_id": "fpga-w1-eth-001",
            "model": "nexus_a7",
            "vendor": "Lattice",
            "serial_number": "SN-W1-ETH-001",
            "interface": "ethernet",
            "emulator_url": "http://fpga-emulator-2:4000",
            "specs": {
                "debugging_board": "nexus_a7",
                "fpga_crystal": "nexus_a7",
                "dsp_slices": 128,
                "internal_freq_mhz": 250,
                "ddr_memory_mb": 2048,
            },
        })
        assert r.status_code == 200
        assert r.json()["interface"] == "ethernet"

    def test_register_fpga_jtag(self, worker2):
        r = worker2.post("/fpgas/register", json={
            "fpga_id": "fpga-w2-jtag-001",
            "model": "xc7a100t-1csg324c",
            "vendor": "Xilinx",
            "serial_number": "SN-W2-JTAG-001",
            "interface": "jtag",
            "emulator_url": "http://fpga-emulator-3:4000",
            "specs": {
                "debugging_board": "nexus_a7",
                "fpga_crystal": "xc7a100t-1csg324c",
                "dsp_slices": 256,
                "internal_freq_mhz": 350,
                "ddr_memory_mb": 8192,
            },
        })
        assert r.status_code == 200
        assert r.json()["interface"] == "jtag"

    def test_list_fpgas_after_registration(self, worker1):
        # Register one first
        worker1.post("/fpgas/register", json={
            "fpga_id": "fpga-list-check",
            "model": "xc7a100t-1csg324c",
            "vendor": "Xilinx",
            "serial_number": "SN-LIST-CHECK",
            "interface": "usb",
            "emulator_url": EMU1_URL,
            "specs": {"debugging_board": "nexus_a7", "fpga_crystal": "xc7a100t-1csg324c",
                      "dsp_slices": 48, "internal_freq_mhz": 250, "ddr_memory_mb": 2048},
        })
        r = worker1.get("/fpgas")
        assert r.status_code == 200
        fpgas = r.json()
        assert isinstance(fpgas, list)
        assert len(fpgas) >= 1
        ids = [f["fpga_id"] for f in fpgas]
        assert "fpga-list-check" in ids

    def test_get_fpga_by_id(self, worker1):
        worker1.post("/fpgas/register", json={
            "fpga_id": "fpga-get-check",
            "model": "nexus_a7",
            "vendor": "Lattice",
            "serial_number": "SN-GET-CHECK",
            "interface": "usb",
            "emulator_url": EMU1_URL,
            "specs": {"debugging_board": "nexus_a7", "fpga_crystal": "nexus_a7",
                      "dsp_slices": 12, "internal_freq_mhz": 125, "ddr_memory_mb": 512},
        })
        r = worker1.get("/fpgas/fpga-get-check")
        assert r.status_code == 200
        assert r.json()["fpga_id"] == "fpga-get-check"

    def test_get_nonexistent_fpga(self, worker1):
        r = worker1.get("/fpgas/does-not-exist")
        assert r.status_code == 404


class TestTaskExecution:
    def test_execute_task_dispatch(self, worker1):
        """Register FPGA then dispatch a task directly to worker."""
        # Register FPGA
        worker1.post("/fpgas/register", json={
            "fpga_id": "fpga-exec-001",
            "model": "xc7a100t-1csg324c",
            "vendor": "Xilinx",
            "serial_number": "SN-EXEC-001",
            "interface": "usb",
            "emulator_url": EMU1_URL,
            "specs": {"debugging_board": "nexus_a7", "fpga_crystal": "xc7a100t-1csg324c",
                      "dsp_slices": 48, "internal_freq_mhz": 250, "ddr_memory_mb": 2048},
        })

        # Dispatch task
        r = worker1.post("/tasks/execute", json={
            "task_id": f"task-exec-{int(time.time())}",
            "type": "deployment",
            "mode": "PROD",
            "bitstream_url": "s3://fpga-artifacts/network-parser/v1.2.3/bitstream.bit",
            "target_fpga_id": "fpga-exec-001",
            "worker_tag": "test",
            "priority": 1,
            "pipeline_id": "test-pipeline",
            "created_at": int(time.time()),
        })
        assert r.status_code == 200
        result = r.json()
        assert result["status"] in ("success", "failed")

    def test_task_status_endpoint(self, worker1):
        r = worker1.get("/tasks/status")
        assert r.status_code == 200
        assert "running_tasks" in r.json()
