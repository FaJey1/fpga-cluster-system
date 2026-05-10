"""
Нагрузочные тесты — два уровня параллелизма (c=1 и c=10),
диапазон запросов: 100 / 500 / 1000 / 5000 / 10000.

Результаты сохраняются в results/*.csv; plot_results.py строит
сравнительные графики c=1 vs c=10 для каждого эндпоинта.
"""
import csv
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from conftest import MASTER_URL, HEADERS

RESULTS_DIR = Path(__file__).parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

CONCURRENCY_LEVELS = [1, 10]
TOTAL_REQUESTS = [100, 500, 1000, 5000, 10000]


def _request(args):
    url, method, path, payload, headers = args
    start = time.perf_counter()
    try:
        with httpx.Client(base_url=url, headers=headers, timeout=60) as client:
            r = client.get(path) if method == "GET" else client.post(path, json=payload)
        return time.perf_counter() - start, r.status_code, None
    except Exception as exc:
        return time.perf_counter() - start, 0, str(exc)


def run_load_test(
    url: str,
    method: str,
    path: str,
    payload: dict,
    total: int,
    concurrency: int,
    test_name: str,
) -> dict:
    args = [(url, method, path, payload, HEADERS)] * total
    latencies = []
    errors = 0

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for elapsed, status, err in pool.map(_request, args):
            latencies.append(elapsed)
            if status != 200 or err:
                errors += 1
    wall = time.perf_counter() - t0

    latencies.sort()
    n = len(latencies)
    return {
        "test": test_name,
        "total_requests": total,
        "concurrency": concurrency,
        "errors": errors,
        "rps": round(total / wall, 2),
        "p50_ms": round(statistics.median(latencies) * 1000, 1),
        "p95_ms": round(latencies[int(0.95 * n)] * 1000, 1),
        "p99_ms": round(latencies[int(0.99 * n)] * 1000, 1),
        "mean_ms": round(statistics.mean(latencies) * 1000, 1),
    }


def save_csv(rows: list, filename: str):
    path = RESULTS_DIR / filename
    if not rows:
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"CSV сохранён: {path}")


class TestLoadMaster:
    @pytest.mark.parametrize("concurrency", CONCURRENCY_LEVELS)
    @pytest.mark.parametrize("total", TOTAL_REQUESTS)
    def test_get_queue_load(self, total, concurrency):
        result = run_load_test(
            MASTER_URL, "GET", "/get_queue", {}, total, concurrency, "get_queue"
        )
        print(f"\n[нагрузка] get_queue total={total} c={concurrency}: {result}")
        assert result["errors"] / total < 0.05, "Более 5% ошибок"
        assert result["p95_ms"] < 5000, f"p95 > 5000ms при total={total} c={concurrency}"

    @pytest.mark.parametrize("concurrency", CONCURRENCY_LEVELS)
    @pytest.mark.parametrize("total", TOTAL_REQUESTS)
    def test_get_workers_load(self, total, concurrency):
        result = run_load_test(
            MASTER_URL, "GET", "/get_workers", {}, total, concurrency, "get_workers"
        )
        print(f"\n[нагрузка] get_workers total={total} c={concurrency}: {result}")
        assert result["errors"] / total < 0.05

    @pytest.mark.parametrize("concurrency", CONCURRENCY_LEVELS)
    @pytest.mark.parametrize("total", TOTAL_REQUESTS)
    def test_who_master_load(self, total, concurrency):
        result = run_load_test(
            MASTER_URL, "GET", "/who_master", {}, total, concurrency, "who_master"
        )
        print(f"\n[нагрузка] who_master total={total} c={concurrency}: {result}")
        assert result["errors"] / total < 0.05

    def test_generate_summary_csvs(self):
        """Генерация итоговых CSV c=1 и c=10 для каждого эндпоинта."""
        endpoints = [
            ("GET", "/get_queue", {}, "get_queue"),
            ("GET", "/get_workers", {}, "get_workers"),
            ("GET", "/who_master", {}, "who_master"),
        ]
        for method, path, payload, name in endpoints:
            rows = []
            for concurrency in CONCURRENCY_LEVELS:
                for total in TOTAL_REQUESTS:
                    r = run_load_test(MASTER_URL, method, path, payload, total, concurrency, name)
                    rows.append(r)
                    print(f"  {name} total={total} c={concurrency}: "
                          f"rps={r['rps']} p95={r['p95_ms']}ms")
            save_csv(rows, f"load_{name}.csv")

    def test_submit_tasks_load(self):
        """Отправка задач при нагрузке — 100/500 запросов, c=1 и c=10."""
        rows = []
        for concurrency in CONCURRENCY_LEVELS:
            for total in [100, 500]:
                result = run_load_test(
                    MASTER_URL, "POST", "/tasks",
                    {"type": "deployment", "mode": "PROD",
                     "bitstream_url": "s3://bucket/load-test.bit",
                     "worker_tag": "test", "priority": 3},
                    total, concurrency, "submit_task",
                )
                rows.append(result)
                print(f"\n[нагрузка] submit_task total={total} c={concurrency}: {result}")
        save_csv(rows, "load_submit_task.csv")
