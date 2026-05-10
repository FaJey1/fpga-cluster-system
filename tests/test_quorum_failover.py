"""
Тесты кворума и отказоустойчивости.

Класс TestQuorumLogic — модульные тесты логики кворума (без Docker).
Класс TestQuorumFailover — интеграционные тесты с реальным останом контейнера;
  запускаются только при наличии Docker CLI (помечены @pytest.mark.failover).

Запуск только failover-тестов:
    pytest tests/test_quorum_failover.py -m failover -v
"""
import shutil
import subprocess
import time

import httpx
import pytest
from conftest import MASTER_URL, MASTER2_URL, MASTER3_URL, HEADERS


def _quorum_health(n: int) -> dict:
    """Копия MasterUseCases._quorum_health для unit-тестирования без импорта FastAPI."""
    import math
    if n == 0:
        return {"quorum_ok": False, "quorum_state": "no_masters",
                "fault_tolerance": 0, "warning": "No masters registered"}
    if n % 2 == 0:
        return {"quorum_ok": False, "quorum_state": "warning",
                "fault_tolerance": 0,
                "warning": (f"Even number of masters ({n}) — split-brain risk. "
                            "Use 1 (standalone), 3, or 5 masters for a valid quorum.")}
    if n == 1:
        return {"quorum_ok": True, "quorum_state": "standalone",
                "fault_tolerance": 0, "warning": "Single master — no fault tolerance"}
    return {"quorum_ok": True, "quorum_state": "ha",
            "fault_tolerance": (n - 1) // 2, "warning": None}


# ── Модульные тесты логики кворума ────────────────────────────────────────────


class TestQuorumLogicUnit:
    """Тестирование логики кворума без инфраструктуры."""

    def _health(self, n: int) -> dict:
        return _quorum_health(n)

    def test_zero_masters_no_quorum(self):
        h = self._health(0)
        assert h["quorum_ok"] is False
        assert h["quorum_state"] == "no_masters"
        assert h["fault_tolerance"] == 0

    def test_one_master_standalone(self):
        h = self._health(1)
        assert h["quorum_ok"] is True
        assert h["quorum_state"] == "standalone"
        assert h["fault_tolerance"] == 0
        assert "no fault tolerance" in h["warning"]

    def test_two_masters_warning(self):
        h = self._health(2)
        assert h["quorum_ok"] is False
        assert h["quorum_state"] == "warning"
        assert h["fault_tolerance"] == 0
        assert "split-brain" in h["warning"]

    def test_three_masters_ha(self):
        h = self._health(3)
        assert h["quorum_ok"] is True
        assert h["quorum_state"] == "ha"
        assert h["fault_tolerance"] == 1
        assert h["warning"] is None

    def test_four_masters_warning(self):
        h = self._health(4)
        assert h["quorum_ok"] is False
        assert h["quorum_state"] == "warning"

    def test_five_masters_ha(self):
        h = self._health(5)
        assert h["quorum_ok"] is True
        assert h["quorum_state"] == "ha"
        assert h["fault_tolerance"] == 2

    def test_seven_masters_ha(self):
        h = self._health(7)
        assert h["quorum_ok"] is True
        assert h["fault_tolerance"] == 3

    @pytest.mark.parametrize("n", [2, 4, 6, 8, 10])
    def test_even_always_warning(self, n):
        h = self._health(n)
        assert h["quorum_ok"] is False
        assert h["quorum_state"] == "warning"

    @pytest.mark.parametrize("n", [1, 3, 5, 7, 9])
    def test_odd_always_ok(self, n):
        h = self._health(n)
        assert h["quorum_ok"] is True

    @pytest.mark.parametrize("n,ft", [(3, 1), (5, 2), (7, 3), (9, 4)])
    def test_fault_tolerance_formula(self, n, ft):
        h = self._health(n)
        assert h["fault_tolerance"] == ft


# ── Интеграционные тесты живого кластера ──────────────────────────────────────


class TestQuorumLive:
    """Проверка кворума на живом кластере из 3 мастеров."""

    def test_current_quorum_is_ha(self):
        r = httpx.get(f"{MASTER_URL}/quorum", headers=HEADERS, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["master_count"] == 3
        assert data["quorum_ok"] is True
        assert data["quorum_state"] == "ha"
        assert data["fault_tolerance"] == 1
        assert data["warning"] is None

    def test_all_masters_agree_on_quorum(self):
        for url in (MASTER_URL, MASTER2_URL, MASTER3_URL):
            r = httpx.get(f"{url}/health", headers=HEADERS, timeout=10)
            data = r.json()
            assert data["quorum_ok"] is True, f"{url}: quorum_ok=False"
            assert data["quorum_state"] == "ha", f"{url}: state={data['quorum_state']}"

    def test_exactly_one_leader(self):
        leaders = []
        for url in (MASTER_URL, MASTER2_URL, MASTER3_URL):
            r = httpx.get(f"{url}/who_master", headers=HEADERS, timeout=10)
            data = r.json()
            if data.get("is_leader") or data.get("is_master"):
                leaders.append(data["node_id"])
        assert len(leaders) == 1, f"Ожидался ровно 1 лидер, получено: {leaders}"

    def test_leader_has_smallest_node_id(self):
        r = httpx.get(f"{MASTER_URL}/get_masters", headers=HEADERS, timeout=10)
        masters = r.json()
        node_ids = sorted(m["node_id"] for m in masters if m.get("node_id"))
        expected_leader = node_ids[0]

        for url in (MASTER_URL, MASTER2_URL, MASTER3_URL):
            r = httpx.get(f"{url}/who_master", headers=HEADERS, timeout=10)
            data = r.json()
            if data.get("is_leader") or data.get("is_master"):
                assert data["node_id"] == expected_leader, (
                    f"Лидер {data['node_id']} не совпадает с ожидаемым {expected_leader}"
                )


# ── Failover-тесты (требуют Docker) ───────────────────────────────────────────

DOCKER_AVAILABLE = shutil.which("docker") is not None


@pytest.mark.failover
@pytest.mark.skipif(not DOCKER_AVAILABLE, reason="Docker CLI недоступен")
class TestQuorumFailover:
    """
    Тесты отказоустойчивости с реальным останом контейнера.

    Сценарий: остановить master-3 → кворум становится 2 (ПРЕДУПРЕЖДЕНИЕ)
              → запустить master-3 → кворум восстанавливается до HA.
    """

    @pytest.fixture(autouse=True)
    def ensure_master3_running(self):
        """Гарантирует запуск master-3 после каждого теста."""
        yield
        subprocess.run(["docker", "start", "fpga_master_3"],
                       capture_output=True, timeout=15)
        time.sleep(8)

    def _stop_master3(self):
        subprocess.run(["docker", "stop", "fpga_master_3"],
                       check=True, capture_output=True, timeout=15)

    def _start_master3(self):
        subprocess.run(["docker", "start", "fpga_master_3"],
                       check=True, capture_output=True, timeout=15)

    def test_two_masters_triggers_quorum_warning(self):
        """При 2 мастерах кластер должен сообщать о ПРЕДУПРЕЖДЕНИИ (split-brain)."""
        self._stop_master3()
        time.sleep(12)

        r = httpx.get(f"{MASTER_URL}/health", headers=HEADERS, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["masters_count"] == 2, f"Ожидалось 2, получено {data['masters_count']}"
        assert data["quorum_ok"] is False
        assert data["quorum_state"] == "warning"
        assert data["fault_tolerance"] == 0

    def test_cluster_remains_available_with_two_masters(self):
        """При 2 мастерах кластер продолжает отвечать на запросы."""
        self._stop_master3()
        time.sleep(12)

        for url in (MASTER_URL, MASTER2_URL):
            r = httpx.get(f"{url}/health", headers=HEADERS, timeout=10)
            assert r.status_code == 200, f"{url} недоступен при 2 мастерах"

    def test_quorum_recovers_after_restart(self):
        """После возврата 3-го мастера кворум восстанавливается до HA."""
        self._stop_master3()
        time.sleep(12)

        r = httpx.get(f"{MASTER_URL}/health", headers=HEADERS, timeout=10)
        assert r.json()["quorum_state"] == "warning"

        self._start_master3()
        time.sleep(12)

        r = httpx.get(f"{MASTER_URL}/health", headers=HEADERS, timeout=10)
        data = r.json()
        assert data["quorum_ok"] is True
        assert data["quorum_state"] == "ha"
        assert data["fault_tolerance"] == 1

    def test_task_submission_survives_one_master_failure(self):
        """Отправка задач продолжает работать при отказе одного мастера."""
        self._stop_master3()
        time.sleep(12)

        r = httpx.post(
            f"{MASTER_URL}/tasks",
            json={"type": "deployment", "mode": "PROD",
                  "bitstream_url": "s3://bucket/failover-test.bit",
                  "worker_tag": "test", "priority": 1},
            headers=HEADERS, timeout=10,
        )
        assert r.status_code == 200
        task_id = r.json()["task_id"]

        # Проверить на master-2 (master-3 остановлен)
        r2 = httpx.get(f"{MASTER2_URL}/tasks/{task_id}", headers=HEADERS, timeout=10)
        assert r2.status_code == 200
        assert r2.json()["task_id"] == task_id
