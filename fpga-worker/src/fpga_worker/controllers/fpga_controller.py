from typing import Dict, Any, Optional
from fastapi import HTTPException
from pydantic import BaseModel

from fpga_worker.controllers.main import router, get_usecases
from fpga_worker.usecases.worker_usecases import WorkerUseCases
from fastapi import Depends


class FPGASpecs(BaseModel):
    debugging_board: str = ""
    fpga_crystal: str = ""
    dsp_slices: int = 0
    internal_freq_mhz: int = 0
    ddr_memory_mb: int = 0


class RegisterFPGARequest(BaseModel):
    fpga_id: str
    model: str
    vendor: str
    serial_number: str
    interface: str = "usb"
    emulator_url: str = ""
    board_name: str = ""
    specs: FPGASpecs = FPGASpecs()


@router.post("/fpgas/register", tags=["fpgas"])
async def register_fpga(
    payload: RegisterFPGARequest,
    usecases: WorkerUseCases = Depends(get_usecases),
):
    try:
        fpga = await usecases.register_fpga(payload.model_dump())
        return fpga.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/fpgas", tags=["fpgas"])
async def list_fpgas(usecases: WorkerUseCases = Depends(get_usecases)):
    try:
        fpgas = await usecases.list_fpgas()
        return [f.to_dict() for f in fpgas]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/fpgas/{fpga_id}", tags=["fpgas"])
async def get_fpga(fpga_id: str, usecases: WorkerUseCases = Depends(get_usecases)):
    fpga = await usecases.get_fpga(fpga_id)
    if fpga is None:
        raise HTTPException(status_code=404, detail="FPGA not found")
    return fpga.to_dict()
