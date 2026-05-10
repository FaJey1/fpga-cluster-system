from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class ConnectionPort(ABC):
    """Abstract connection to an FPGA device."""

    @abstractmethod
    async def program(self, bitstream_url: str) -> Dict[str, Any]:
        """Download and flash bitstream. Returns result dict."""

    @abstractmethod
    async def run_tests(self, test_config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute legacy test sequences. Returns results dict."""

    @abstractmethod
    async def run_test_sequence(self, test_vectors: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run structured test vectors: each has input, expected_output, label.
        Returns per-case comparison results and aggregate pass_rate."""

    @abstractmethod
    async def get_status(self) -> Dict[str, Any]:
        """Return current FPGA status."""

    @abstractmethod
    def interface_type(self) -> str:
        """Return interface type string."""


class ConnectionFactory(ABC):
    """Factory that creates ConnectionPort instances per interface type."""

    @abstractmethod
    def create(self, interface: str, emulator_url: str) -> ConnectionPort:
        """Create a connection adapter for the given interface."""
