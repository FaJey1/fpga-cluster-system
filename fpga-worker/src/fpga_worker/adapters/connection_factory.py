"""
Factory pattern for creating FPGA connection adapters.
Each adapter wraps the FPGA emulator HTTP API to simulate
USB / Ethernet / JTAG / PCIe communication.
"""
import asyncio
import logging
from typing import Dict, Any

import httpx

from fpga_worker.ports.connection_port import ConnectionPort, ConnectionFactory

logger = logging.getLogger(__name__)

# ---------- Concrete Adapters ----------

class _EmulatorConnection(ConnectionPort):
    """Base adapter: calls the FPGA emulator REST API."""

    def __init__(self, emulator_url: str, iface: str):
        self._url = emulator_url.rstrip("/")
        self._iface = iface

    async def program(self, bitstream_url: str) -> Dict[str, Any]:
        # Demo-режим: прошивка до 160 с → таймаут 300 с
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{self._url}/program",
                json={"bitstream_url": bitstream_url, "interface": self._iface},
            )
            resp.raise_for_status()
            return resp.json()

    async def run_tests(self, test_config: Dict[str, Any]) -> Dict[str, Any]:
        # Demo-режим: до 20 векторов × 180 с = 3600 с → таймаут 600 с для CI
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(
                f"{self._url}/test",
                json={**test_config, "interface": self._iface},
            )
            resp.raise_for_status()
            return resp.json()

    async def run_test_sequence(self, test_vectors: list) -> Dict[str, Any]:
        # Demo-режим: до 20 векторов × 180 с = 3600 с → таймаут 600 с для CI
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(
                f"{self._url}/run_test_sequence",
                json={"test_vectors": test_vectors, "interface": self._iface},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_status(self) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{self._url}/status")
            resp.raise_for_status()
            return resp.json()

    def interface_type(self) -> str:
        return self._iface


class USBConnection(_EmulatorConnection):
    def __init__(self, emulator_url: str):
        super().__init__(emulator_url, "usb")


class EthernetConnection(_EmulatorConnection):
    def __init__(self, emulator_url: str):
        super().__init__(emulator_url, "ethernet")


class JTAGConnection(_EmulatorConnection):
    def __init__(self, emulator_url: str):
        super().__init__(emulator_url, "jtag")


class PCIeConnection(_EmulatorConnection):
    def __init__(self, emulator_url: str):
        super().__init__(emulator_url, "pcie")


# ---------- Factory ----------

class FPGAConnectionFactory(ConnectionFactory):
    _registry: Dict[str, type] = {
        "usb": USBConnection,
        "ethernet": EthernetConnection,
        "jtag": JTAGConnection,
        "pcie": PCIeConnection,
    }

    def create(self, interface: str, emulator_url: str) -> ConnectionPort:
        cls = self._registry.get(interface.lower())
        if cls is None:
            raise ValueError(f"Unknown interface type: {interface}")
        return cls(emulator_url)
