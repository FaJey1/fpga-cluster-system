from .main import *
from src.entities.fpga_device import FPGADevice


class RegisterFPGAIn(BaseModel):
    fpga_id: str
    worker_id: str
    model: str
    vendor: str
    serial_number: str
    interface: str = "usb"
    status: str = "idle"
    board_name: str = ""
    specs: Optional[Dict] = None


@router.post("/fpgas/register", tags=["fpgas"])
async def register_fpga(
    payload: RegisterFPGAIn,
    _: str = require_operator,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        fpga = FPGADevice(
            fpga_id=payload.fpga_id,
            worker_id=payload.worker_id,
            model=payload.model,
            vendor=payload.vendor,
            serial_number=payload.serial_number,
            interface=payload.interface,
            board_name=payload.board_name,
        )
        return await usecases.register_fpga(fpga)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fpgas", tags=["fpgas"])
async def list_fpgas(
    _: str = require_viewer,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        return await usecases.get_fpgas()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class UpdateFPGAStatusIn(BaseModel):
    status: str


@router.put("/fpgas/{fpga_id}/status", tags=["fpgas"])
async def update_fpga_status(
    fpga_id: str,
    payload: UpdateFPGAStatusIn,
    _: str = require_operator,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        return await usecases.update_fpga_status(fpga_id, payload.status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/fpgas/{fpga_id}", tags=["fpgas"])
async def delete_fpga(
    fpga_id: str,
    _: str = require_operator,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        return await usecases.delete_fpga(fpga_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fpgas/{fpga_id}", tags=["fpgas"])
async def get_fpga(
    fpga_id: str,
    _: str = require_viewer,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        fpga = await usecases.get_fpga(fpga_id)
        if fpga is None:
            raise HTTPException(status_code=404, detail="FPGA not found")
        return fpga
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
