from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class FPGAStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"


class InterfaceType(str, Enum):
    USB = "usb"
    ETHERNET = "ethernet"
    JTAG = "jtag"
    PCIE = "pcie"


@dataclass
class FPGASpecs:
    debugging_board: str
    fpga_crystal: str
    dsp_slices: int
    internal_freq_mhz: int
    ddr_memory_mb: int

    def to_dict(self):
        return {
            "debugging_board": self.debugging_board,
            "fpga_crystal": self.fpga_crystal,
            "dsp_slices": self.dsp_slices,
            "internal_freq_mhz": self.internal_freq_mhz,
            "ddr_memory_mb": self.ddr_memory_mb,
        }

    @staticmethod
    def from_dict(d: dict) -> "FPGASpecs":
        return FPGASpecs(
            debugging_board=d.get("debugging_board", ""),
            fpga_crystal=d.get("fpga_crystal", ""),
            dsp_slices=int(d.get("dsp_slices", 0)),
            internal_freq_mhz=int(d.get("internal_freq_mhz", 0)),
            ddr_memory_mb=int(d.get("ddr_memory_mb", 0)),
        )


@dataclass
class FPGA:
    fpga_id: str
    worker_id: str
    model: str
    vendor: str
    serial_number: str
    interface: InterfaceType
    emulator_url: str
    specs: FPGASpecs
    status: FPGAStatus = FPGAStatus.IDLE
    board_name: str = ""
    current_bitstream_version: Optional[str] = None

    def to_dict(self):
        return {
            "fpga_id": self.fpga_id,
            "worker_id": self.worker_id,
            "model": self.model,
            "vendor": self.vendor,
            "serial_number": self.serial_number,
            "interface": self.interface.value,
            "emulator_url": self.emulator_url,
            "specs": self.specs.to_dict(),
            "status": self.status.value,
            "board_name": self.board_name,
            "current_bitstream_version": self.current_bitstream_version,
        }

    @staticmethod
    def from_dict(d: dict) -> "FPGA":
        return FPGA(
            fpga_id=d["fpga_id"],
            worker_id=d["worker_id"],
            model=d["model"],
            vendor=d["vendor"],
            serial_number=d["serial_number"],
            interface=InterfaceType(d.get("interface", "usb")),
            emulator_url=d.get("emulator_url", ""),
            specs=FPGASpecs.from_dict(d.get("specs", {})),
            status=FPGAStatus(d.get("status", "idle")),
            board_name=d.get("board_name", ""),
            current_bitstream_version=d.get("current_bitstream_version"),
        )
