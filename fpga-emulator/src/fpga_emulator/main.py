"""
FPGA Emulator — simulates a physical FPGA board.

Exposes:
  POST /program   — simulate bitstream loading
  POST /test      — simulate test sequence execution
  GET  /status    — current FPGA state
  GET  /metrics   — Prometheus metrics
  GET  /health    — liveness probe
"""
import asyncio
import os
import random
import time
import logging

import uvicorn
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="FPGA Emulator", version="1.0.0")

# ── State ──────────────────────────────────────────────────────────────────
FPGA_ID = os.getenv("FPGA_ID", "fpga-emu-1")
FPGA_MODEL = os.getenv("FPGA_MODEL", "xc7a100t-1csg324c")
FPGA_VENDOR = os.getenv("FPGA_VENDOR", "Xilinx")
FAIL_RATE = float(os.getenv("FAIL_RATE", "0.05"))  # 5% random failures

# ── Timing parameters (override via env vars for demo/CI) ──────────────────
# Programming delay: PROGRAM_TIME_MIN_S .. PROGRAM_TIME_MAX_S seconds
PROGRAM_TIME_MIN_S = float(os.getenv("PROGRAM_TIME_MIN_S", "35"))
PROGRAM_TIME_MAX_S = float(os.getenv("PROGRAM_TIME_MAX_S", "160"))
# Per-vector test time in seconds: total delay = num_vectors * random(min, max)
TEST_TIME_PER_VECTOR_MIN_S = float(os.getenv("TEST_TIME_PER_VECTOR_MIN_S", "60"))
TEST_TIME_PER_VECTOR_MAX_S = float(os.getenv("TEST_TIME_PER_VECTOR_MAX_S", "180"))

_state = {
    "status": "idle",
    "current_bitstream": None,
    "last_programmed_at": None,
    "program_count": 0,
    "test_count": 0,
}

# ── Prometheus ─────────────────────────────────────────────────────────────
program_counter = Counter("emulator_program_total", "Bitstream loads", ["result"])
test_counter = Counter("emulator_test_total", "Test runs", ["result"])
program_duration = Histogram("emulator_program_duration_seconds", "Time to program")
test_duration = Histogram("emulator_test_duration_seconds", "Time to run tests")
status_gauge = Gauge("emulator_busy", "1 if busy")


# ── Request / Response models ──────────────────────────────────────────────
class ProgramRequest(BaseModel):
    bitstream_url: str
    interface: str = "usb"


class TestRequest(BaseModel):
    sequences: Optional[List[Any]] = None
    timeout: int = 300
    interface: str = "usb"
    test_count: int = 10


class TestVector(BaseModel):
    input: Any
    expected_output: Any
    label: str = ""


class TestSequenceRequest(BaseModel):
    test_vectors: List[TestVector]
    interface: str = "usb"
    timeout: int = 300


# ── Endpoints ──────────────────────────────────────────────────────────────
@app.post("/program")
async def program(req: ProgramRequest):
    logger.info("[%s] Programming from %s via %s", FPGA_ID, req.bitstream_url, req.interface)
    _state["status"] = "busy"
    status_gauge.set(1)

    delay = random.uniform(PROGRAM_TIME_MIN_S, PROGRAM_TIME_MAX_S)
    logger.info("[%s] Simulating bitstream load: %.1fs", FPGA_ID, delay)
    with program_duration.time():
        await asyncio.sleep(delay)

    failed = random.random() < FAIL_RATE
    if failed:
        _state["status"] = "idle"
        status_gauge.set(0)
        program_counter.labels(result="failure").inc()
        return {"success": False, "error": "Simulated programming failure", "fpga_id": FPGA_ID}

    _state["current_bitstream"] = req.bitstream_url
    _state["last_programmed_at"] = int(time.time())
    _state["program_count"] += 1
    _state["status"] = "idle"
    status_gauge.set(0)
    program_counter.labels(result="success").inc()

    return {
        "success": True,
        "fpga_id": FPGA_ID,
        "bitstream_url": req.bitstream_url,
        "interface": req.interface,
        "duration_seconds": round(delay, 2),
        "programmed_at": _state["last_programmed_at"],
    }


@app.post("/test")
async def run_tests(req: TestRequest):
    logger.info("[%s] Running %d tests via %s", FPGA_ID, req.test_count, req.interface)
    _state["status"] = "busy"
    status_gauge.set(1)

    per_vector_s = random.uniform(TEST_TIME_PER_VECTOR_MIN_S, TEST_TIME_PER_VECTOR_MAX_S)
    delay = req.test_count * per_vector_s
    with test_duration.time():
        await asyncio.sleep(delay)

    failed = random.random() < FAIL_RATE
    _state["test_count"] += 1
    _state["status"] = "idle"
    status_gauge.set(0)

    if failed:
        test_counter.labels(result="failure").inc()
        pass_rate = round(random.uniform(0.5, 0.85), 3)
    else:
        test_counter.labels(result="success").inc()
        pass_rate = round(random.uniform(0.95, 1.0), 3)

    passed = int(req.test_count * pass_rate)
    return {
        "success": not failed,
        "fpga_id": FPGA_ID,
        "pass_rate": pass_rate,
        "passed": passed,
        "total": req.test_count,
        "report_url": f"s3://fpga-reports/emu/{FPGA_ID}/{int(time.time())}.json",
        "duration_seconds": round(delay, 2),
    }


@app.post("/run_test_sequence")
async def run_test_sequence(req: TestSequenceRequest):
    """Run test vectors: feed each input to FPGA, compare actual vs expected output."""
    logger.info("[%s] Running test sequence (%d vectors) via %s",
                FPGA_ID, len(req.test_vectors), req.interface)
    _state["status"] = "busy"
    status_gauge.set(1)

    per_vector_s = random.uniform(TEST_TIME_PER_VECTOR_MIN_S, TEST_TIME_PER_VECTOR_MAX_S)
    delay = len(req.test_vectors) * per_vector_s
    logger.info("[%s] Simulating test sequence: %.1fs (%.1fs × %d vectors)",
                FPGA_ID, delay, per_vector_s, len(req.test_vectors))
    with test_duration.time():
        await asyncio.sleep(delay)

    _state["status"] = "idle"
    status_gauge.set(0)
    _state["test_count"] += 1

    cases = []
    passed_count = 0
    for vec in req.test_vectors:
        # Simulate FPGA output: match expected with (1 - FAIL_RATE) probability
        match = random.random() >= FAIL_RATE
        actual = vec.expected_output if match else f"ERROR_{random.randint(1000,9999)}"
        ok = actual == vec.expected_output
        if ok:
            passed_count += 1
        cases.append({
            "label": vec.label,
            "input": vec.input,
            "expected_output": vec.expected_output,
            "actual_output": actual,
            "passed": ok,
        })

    total = len(cases)
    pass_rate = round(passed_count / total, 3) if total else 0.0
    all_passed = passed_count == total

    if all_passed:
        test_counter.labels(result="success").inc()
    else:
        test_counter.labels(result="failure").inc()

    return {
        "success": all_passed,
        "fpga_id": FPGA_ID,
        "total": total,
        "passed": passed_count,
        "failed": total - passed_count,
        "pass_rate": pass_rate,
        "cases": cases,
        "duration_seconds": round(delay, 2),
        "report_url": f"s3://fpga-reports/emu/{FPGA_ID}/{int(time.time())}_seq.json",
    }


@app.get("/status")
async def status():
    return {
        "fpga_id": FPGA_ID,
        "model": FPGA_MODEL,
        "vendor": FPGA_VENDOR,
        **_state,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "fpga_id": FPGA_ID}


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    uvicorn.run("fpga_emulator.main:app", host="0.0.0.0", port=4000, reload=False)
