"""
Shared fixtures for integration tests.
All tests run against a live docker-compose stack.

Set MASTER_URL / WORKER1_URL / WORKER2_URL / EMU1_URL / CICD_URL env-vars to override.
"""
import os
import time

import httpx
import pytest

MASTER_URL = os.getenv("MASTER_URL", "http://localhost:3030")
CICD_URL = os.getenv("CICD_URL", "http://localhost:3040")
MASTER2_URL = os.getenv("MASTER2_URL", "http://localhost:3031")
MASTER3_URL = os.getenv("MASTER3_URL", "http://localhost:3032")
WORKER1_URL = os.getenv("WORKER1_URL", "http://localhost:4031")
WORKER2_URL = os.getenv("WORKER2_URL", "http://localhost:4032")
EMU1_URL = os.getenv("EMU1_URL", "http://localhost:4001")
EMU2_URL = os.getenv("EMU2_URL", "http://localhost:4002")
EMU3_URL = os.getenv("EMU3_URL", "http://localhost:4003")

HEADERS = {"X-API-Token": "secret-token"}


def wait_for(url: str, timeout: int = 60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{url}/health", timeout=3)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError(f"Service at {url} did not become healthy in {timeout}s")


CICD_HEADERS = {"X-API-Token": "cicd-secret"}


@pytest.fixture(scope="session", autouse=True)
def wait_for_services():
    """Block until all services are healthy."""
    for url in (MASTER_URL, MASTER2_URL, MASTER3_URL, WORKER1_URL, WORKER2_URL, EMU1_URL, CICD_URL):
        wait_for(url)


# Timeout covers PROGRAM_TIME_MAX_S(160) + test sequence + overhead
_CLIENT_TIMEOUT = httpx.Timeout(connect=10, read=300, write=10, pool=5)


@pytest.fixture
def master():
    return httpx.Client(base_url=MASTER_URL, headers=HEADERS, timeout=_CLIENT_TIMEOUT)


@pytest.fixture
def master2():
    return httpx.Client(base_url=MASTER2_URL, headers=HEADERS, timeout=_CLIENT_TIMEOUT)


@pytest.fixture
def master3():
    return httpx.Client(base_url=MASTER3_URL, headers=HEADERS, timeout=_CLIENT_TIMEOUT)


@pytest.fixture
def worker1():
    return httpx.Client(base_url=WORKER1_URL, timeout=_CLIENT_TIMEOUT)


@pytest.fixture
def worker2():
    return httpx.Client(base_url=WORKER2_URL, timeout=_CLIENT_TIMEOUT)


@pytest.fixture
def emu1():
    return httpx.Client(base_url=EMU1_URL, timeout=_CLIENT_TIMEOUT)


@pytest.fixture
def cicd():
    return httpx.Client(base_url=CICD_URL, headers=CICD_HEADERS, timeout=_CLIENT_TIMEOUT)
