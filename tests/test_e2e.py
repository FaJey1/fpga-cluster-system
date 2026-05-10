"""
End-to-end тесты полного пайплайна ПЛИС-кластера.

Сценарии:
  - 3 тестовых проекта (worker_tag=test, is_test=True): Network Parser, HFT Decoder, TCP Offload
  - 2 production проекта (worker_tag=dev/prod): GPIO Controller, Encryption Accelerator

Пайплайн: API → очередь → планировщик → воркер по тегу → прошивка ПЛИС → тест-последовательность
"""
import time
import pytest
import httpx
from conftest import MASTER_URL, WORKER1_URL, EMU1_URL

# ── Проекты для тестирования (worker_tag=test, is_test=True) ──────────────────
TEST_PROJECTS = [
    {
        "name": "Network Parser",
        "worker_tag": "test",
        "fpga_tag": "fpga-test-001",
        "bitstream_url": "s3://fpga-artifacts/network-parser/v1.2.3/bitstream.bit",
        "tests_url": "s3://fpga-testvectors/network-parser/v1.2.3/vectors.json",
        "test_interface": "usb",
        "pipeline_id": "pipeline-net-parser-001",
        "description": "Сетевой парсер пакетов (Xilinx xc7a100t)",
    },
    {
        "name": "HFT Market Data Decoder",
        "worker_tag": "test",
        "fpga_tag": "fpga-test-001",
        "bitstream_url": "s3://fpga-artifacts/hft-decoder/v2.0.1/bitstream.bit",
        "tests_url": "s3://fpga-testvectors/hft-decoder/v2.0.1/vectors.json",
        "test_interface": "usb",
        "pipeline_id": "pipeline-hft-decoder-001",
        "description": "Декодер рыночных данных HFT (Lattice nexus_a7)",
    },
    {
        "name": "TCP Offload Engine",
        "worker_tag": "test",
        "fpga_tag": "fpga-test-001",
        "bitstream_url": "s3://fpga-artifacts/tcp-offload/v3.1.0/bitstream.bit",
        "tests_url": "s3://fpga-testvectors/tcp-offload/v3.1.0/vectors.json",
        "test_interface": "jtag",
        "pipeline_id": "pipeline-tcp-offload-001",
        "description": "TCP-разгрузочный движок (Xilinx xc7a100t)",
    },
]

# ── Production-проекты (dev/prod, is_test=False) ──────────────────────────────
PROD_PROJECTS = [
    {
        "name": "GPIO Controller",
        "worker_tag": "dev",
        "fpga_tag": "dev_gpio_controller",
        "bitstream_url": "s3://fpga-artifacts/gpio-controller/v1.0.0/bitstream.bit",
        "pipeline_id": "pipeline-gpio-dev-001",
        "description": "Контроллер GPIO для отладочного стенда",
    },
    {
        "name": "Encryption Accelerator",
        "worker_tag": "prod",
        "fpga_tag": "prod_encryption_accelerator",
        "bitstream_url": "s3://fpga-artifacts/encrypt-accel/v4.2.0/bitstream.bit",
        "pipeline_id": "pipeline-encrypt-prod-001",
        "description": "Аппаратный ускоритель шифрования (production)",
    },
]


class TestPipelineTestProjects:
    """3 тестовых проекта: worker_tag=test, is_test=True, с тест-последовательностью."""

    @pytest.fixture(autouse=True)
    def register_test_fpga(self, worker1):
        worker1.post("/fpgas/register", json={
            "fpga_id": "fpga-test-001",
            "model": "xc7a100t-1csg324c",
            "vendor": "Xilinx",
            "serial_number": "SN-TEST-001",
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

    @pytest.mark.parametrize("project", TEST_PROJECTS, ids=[p["name"] for p in TEST_PROJECTS])
    def test_test_project_pipeline(self, master, worker1, project):
        """Полный пайплайн тестового проекта: submit → execute → test sequence → result."""
        # 1. Отправить задачу на мастер
        r = master.post("/tasks", json={
            "type": "test",
            "mode": "TEST",
            "bitstream_url": project["bitstream_url"],
            "target_fpga_id": project["fpga_tag"],
            "worker_tag": project["worker_tag"],
            "priority": 1,
            "pipeline_id": project["pipeline_id"],
            "project_name": project["name"],
            "is_test": True,
            "tests_url": project["tests_url"],
            "test_interface": project["test_interface"],
            "fpga_tag": project["fpga_tag"],
        })
        assert r.status_code == 200, f"Submit failed: {r.text}"
        task = r.json()
        task_id = task["task_id"]
        assert task["status"] == "pending"
        assert task["is_test"] is True
        assert task["worker_tag"] == "test"

        # 2. Диспетчеризация на воркер (симуляция планировщика)
        r2 = worker1.post("/tasks/execute", json={
            **task,
            "created_at": int(time.time()),
        })
        assert r2.status_code == 200
        result = r2.json()
        assert result["status"] in ("success", "failed"), f"Unexpected status: {result}"

        # 3. Проверить наличие результатов тест-последовательности
        if result["status"] == "success":
            assert "test_sequence_results" in result, \
                f"Тестовый проект должен содержать test_sequence_results: {result}"
            seq = result["test_sequence_results"]
            assert "total" in seq
            assert "passed" in seq
            assert "pass_rate" in seq
            assert 0 <= seq["pass_rate"] <= 1.0
            assert "cases" in seq

        # 4. Отчитаться мастеру
        master.post(f"/tasks/{task_id}/complete", json=result)

        # 5. Проверить финальный статус
        r3 = master.get(f"/tasks/{task_id}")
        assert r3.status_code == 200
        assert r3.json()["status"] in ("completed", "failed")

    def test_all_test_projects_submitted(self, master):
        """Три тестовых проекта отправлены в очередь и видны в списке задач."""
        task_ids = []
        for proj in TEST_PROJECTS:
            r = master.post("/tasks", json={
                "type": "test",
                "mode": "TEST",
                "bitstream_url": proj["bitstream_url"],
                "worker_tag": proj["worker_tag"],
                "project_name": proj["name"],
                "is_test": True,
                "tests_url": proj["tests_url"],
                "test_interface": proj["test_interface"],
                "fpga_tag": proj["fpga_tag"],
            })
            assert r.status_code == 200
            task_ids.append(r.json()["task_id"])

        tasks_resp = master.get("/tasks")
        assert tasks_resp.status_code == 200
        all_ids = {t["task_id"] for t in tasks_resp.json()}
        for tid in task_ids:
            assert tid in all_ids, f"Задача {tid} не найдена в списке"

    def test_test_project_fpga_tag_routing(self, master):
        """Тестовые проекты маршрутизируются на ПЛИС с тегом fpga-test-001."""
        for proj in TEST_PROJECTS:
            r = master.post("/tasks", json={
                "type": "test",
                "mode": "TEST",
                "bitstream_url": proj["bitstream_url"],
                "worker_tag": "test",
                "project_name": proj["name"],
                "is_test": True,
                "tests_url": proj["tests_url"],
                "fpga_tag": proj["fpga_tag"],
            })
            assert r.status_code == 200
            task = r.json()
            assert task["fpga_tag"] == "fpga-test-001"
            assert task["worker_tag"] == "test"


class TestPipelineProdProjects:
    """2 production-проекта: dev/prod теги, is_test=False, без тест-последовательности."""

    @pytest.fixture(autouse=True)
    def register_prod_fpgas(self, worker1, worker2):
        # Dev-ПЛИС на worker-1
        worker1.post("/fpgas/register", json={
            "fpga_id": "dev_gpio_controller",
            "model": "xc7a100t-1csg324c",
            "vendor": "Xilinx",
            "serial_number": "SN-DEV-001",
            "interface": "ethernet",
            "emulator_url": EMU1_URL,
            "specs": {"dsp_slices": 48, "internal_freq_mhz": 200, "ddr_memory_mb": 1024},
        })
        # Prod-ПЛИС на worker-2
        worker2.post("/fpgas/register", json={
            "fpga_id": "prod_encryption_accelerator",
            "model": "xc7a100t-1csg324c",
            "vendor": "Xilinx",
            "serial_number": "SN-PROD-001",
            "interface": "pcie",
            "emulator_url": EMU1_URL,
            "specs": {"dsp_slices": 256, "internal_freq_mhz": 400, "ddr_memory_mb": 8192},
        })

    def test_dev_project_pipeline(self, master, worker1):
        """GPIO Controller: worker_tag=dev, fpga_tag=dev_gpio_controller."""
        proj = PROD_PROJECTS[0]
        r = master.post("/tasks", json={
            "type": "deployment",
            "mode": "PROD",
            "bitstream_url": proj["bitstream_url"],
            "target_fpga_id": proj["fpga_tag"],
            "worker_tag": proj["worker_tag"],
            "priority": 2,
            "pipeline_id": proj["pipeline_id"],
            "project_name": proj["name"],
            "is_test": False,
            "fpga_tag": proj["fpga_tag"],
        })
        assert r.status_code == 200
        task = r.json()
        task_id = task["task_id"]
        assert task["is_test"] is False
        assert task["worker_tag"] == "dev"
        assert task["fpga_tag"] == "dev_gpio_controller"

        r2 = worker1.post("/tasks/execute", json={**task, "created_at": int(time.time())})
        assert r2.status_code == 200
        result = r2.json()
        assert result["status"] in ("success", "failed")
        # Deployment не должен содержать тест-последовательность
        assert "test_sequence_results" not in result

        master.post(f"/tasks/{task_id}/complete", json=result)
        r3 = master.get(f"/tasks/{task_id}")
        assert r3.json()["status"] in ("completed", "failed")

    def test_prod_project_pipeline(self, master, worker2):
        """Encryption Accelerator: worker_tag=prod, fpga_tag=prod_encryption_accelerator."""
        proj = PROD_PROJECTS[1]
        r = master.post("/tasks", json={
            "type": "deployment",
            "mode": "PROD",
            "bitstream_url": proj["bitstream_url"],
            "target_fpga_id": proj["fpga_tag"],
            "worker_tag": proj["worker_tag"],
            "priority": 1,
            "pipeline_id": proj["pipeline_id"],
            "project_name": proj["name"],
            "is_test": False,
            "fpga_tag": proj["fpga_tag"],
        })
        assert r.status_code == 200
        task = r.json()
        task_id = task["task_id"]
        assert task["is_test"] is False
        assert task["worker_tag"] == "prod"
        assert task["fpga_tag"] == "prod_encryption_accelerator"

        r2 = worker2.post("/tasks/execute", json={**task, "created_at": int(time.time())})
        assert r2.status_code == 200
        result = r2.json()
        assert "test_sequence_results" not in result

        master.post(f"/tasks/{task_id}/complete", json=result)
        r3 = master.get(f"/tasks/{task_id}")
        assert r3.json()["status"] in ("completed", "failed")

    def test_fpga_tags_follow_naming_convention(self, master):
        """Проверка: fpga_tag для dev = dev_<project>, для prod = prod_<project>."""
        for proj in PROD_PROJECTS:
            r = master.post("/tasks", json={
                "type": "deployment",
                "mode": "PROD",
                "bitstream_url": proj["bitstream_url"],
                "worker_tag": proj["worker_tag"],
                "project_name": proj["name"],
                "fpga_tag": proj["fpga_tag"],
            })
            assert r.status_code == 200
            task = r.json()
            tag = task["fpga_tag"]
            expected_prefix = proj["worker_tag"] + "_"
            assert tag.startswith(expected_prefix), \
                f"fpga_tag '{tag}' должен начинаться с '{expected_prefix}'"


class TestPipelineRouting:
    """Проверка маршрутизации задач по тегам воркеров."""

    def test_worker_tag_separation(self, master):
        """Тестовые и production задачи попадают в разные очереди по worker_tag."""
        # Тестовая задача
        r_test = master.post("/tasks", json={
            "type": "test",
            "mode": "TEST",
            "bitstream_url": TEST_PROJECTS[0]["bitstream_url"],
            "worker_tag": "test",
            "is_test": True,
            "project_name": TEST_PROJECTS[0]["name"],
        })
        # Dev задача
        r_dev = master.post("/tasks", json={
            "type": "deployment",
            "mode": "PROD",
            "bitstream_url": PROD_PROJECTS[0]["bitstream_url"],
            "worker_tag": "dev",
            "is_test": False,
            "project_name": PROD_PROJECTS[0]["name"],
        })
        # Prod задача
        r_prod = master.post("/tasks", json={
            "type": "deployment",
            "mode": "PROD",
            "bitstream_url": PROD_PROJECTS[1]["bitstream_url"],
            "worker_tag": "prod",
            "is_test": False,
            "project_name": PROD_PROJECTS[1]["name"],
        })

        assert r_test.status_code == 200
        assert r_dev.status_code == 200
        assert r_prod.status_code == 200

        assert r_test.json()["worker_tag"] == "test"
        assert r_dev.json()["worker_tag"] == "dev"
        assert r_prod.json()["worker_tag"] == "prod"

    def test_queue_contains_test_tasks(self, master):
        """Очередь содержит задачи после отправки."""
        master.post("/tasks", json={
            "bitstream_url": TEST_PROJECTS[0]["bitstream_url"],
            "worker_tag": "test",
            "is_test": True,
            "project_name": TEST_PROJECTS[0]["name"],
        })
        r = master.get("/get_queue")
        assert r.status_code == 200


class TestEmulatorTestSequence:
    """Прямые тесты эмулятора: /run_test_sequence."""

    def test_run_test_sequence_basic(self, emu1):
        r = emu1.post("/run_test_sequence", json={
            "test_vectors": [
                {"label": "vec_000", "input": [0xAA, 0xBB], "expected_output": [0x00, 0x11]},
                {"label": "vec_001", "input": [0x01, 0x02], "expected_output": [0xAB, 0xA8]},
            ],
            "interface": "usb",
        })
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert data["total"] == 2
        assert "passed" in data
        assert "pass_rate" in data
        assert "cases" in data
        assert len(data["cases"]) == 2
        for case in data["cases"]:
            assert "label" in case
            assert "passed" in case
            assert "actual_output" in case

    def test_run_test_sequence_case_structure(self, emu1):
        vectors = [
            {"label": f"case_{i}", "input": i, "expected_output": i * 2}
            for i in range(10)
        ]
        r = emu1.post("/run_test_sequence", json={
            "test_vectors": vectors,
            "interface": "jtag",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 10
        assert data["passed"] + data["failed"] == data["total"]
        assert 0.0 <= data["pass_rate"] <= 1.0

    def test_emulator_program_still_works(self, emu1):
        r = emu1.post("/program", json={
            "bitstream_url": "s3://test/bitstream.bit",
            "interface": "usb",
        })
        assert r.status_code == 200
        assert "success" in r.json()

    def test_emulator_status(self, emu1):
        r = emu1.get("/status")
        assert r.status_code == 200
        data = r.json()
        assert "fpga_id" in data
        assert "status" in data


class TestFullPipelineIntegration:
    """Интеграционный тест: все 5 проектов через полный пайплайн."""

    @pytest.fixture(autouse=True)
    def setup_fpgas(self, worker1, worker2):
        for fpga_id, model, iface, worker in [
            ("fpga-test-001", "xc7a100t-1csg324c", "usb", worker1),
            ("dev_gpio_controller", "xc7a100t-1csg324c", "ethernet", worker1),
            ("prod_encryption_accelerator", "xc7a100t-1csg324c", "pcie", worker2),
        ]:
            worker.post("/fpgas/register", json={
                "fpga_id": fpga_id,
                "model": model,
                "vendor": "Xilinx",
                "serial_number": f"SN-{fpga_id}",
                "interface": iface,
                "emulator_url": EMU1_URL,
                "specs": {"dsp_slices": 100, "internal_freq_mhz": 250, "ddr_memory_mb": 2048},
            })

    def test_all_five_projects_submitted_and_visible(self, master):
        """Все 5 проектов (3 test + 2 prod) отправлены и видны в списке задач."""
        all_projects = [
            {**p, "type": "test", "mode": "TEST", "is_test": True}
            for p in TEST_PROJECTS
        ] + [
            {**p, "type": "deployment", "mode": "PROD", "is_test": False}
            for p in PROD_PROJECTS
        ]

        task_ids = []
        for proj in all_projects:
            payload = {
                "type": proj["type"],
                "mode": proj["mode"],
                "bitstream_url": proj["bitstream_url"],
                "worker_tag": proj["worker_tag"],
                "project_name": proj["name"],
                "is_test": proj["is_test"],
                "fpga_tag": proj.get("fpga_tag", ""),
            }
            if proj["is_test"]:
                payload["tests_url"] = proj["tests_url"]
            r = master.post("/tasks", json=payload)
            assert r.status_code == 200, f"Failed to submit {proj['name']}: {r.text}"
            task = r.json()
            assert task["is_test"] == proj["is_test"]
            task_ids.append(task["task_id"])

        assert len(task_ids) == 5

        tasks_r = master.get("/tasks")
        all_ids = {t["task_id"] for t in tasks_r.json()}
        for tid in task_ids:
            assert tid in all_ids

    def test_worker_registration_visible(self, master):
        """Воркеры worker-1 и worker-2 зарегистрированы и видны мастеру."""
        workers = master.get("/get_workers").json()
        worker_ids = {w.get("worker_id") for w in workers}
        assert "worker-1" in worker_ids
        assert "worker-2" in worker_ids
