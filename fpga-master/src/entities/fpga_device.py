from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class FPGADevice:
    fpga_id: str
    worker_id: str
    model: str
    vendor: str
    serial_number: str
    interface: str
    status: str = "idle"
    board_name: str = ""
    current_bitstream_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fpga_id": self.fpga_id,
            "worker_id": self.worker_id,
            "model": self.model,
            "vendor": self.vendor,
            "serial_number": self.serial_number,
            "interface": self.interface,
            "status": self.status,
            "board_name": self.board_name,
            "current_bitstream_version": self.current_bitstream_version,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "FPGADevice":
        return FPGADevice(
            fpga_id=d["fpga_id"],
            worker_id=d.get("worker_id", ""),
            model=d.get("model", ""),
            vendor=d.get("vendor", ""),
            serial_number=d.get("serial_number", ""),
            interface=d.get("interface", "usb"),
            status=d.get("status", "idle"),
            board_name=d.get("board_name", ""),
            current_bitstream_version=d.get("current_bitstream_version"),
        )
