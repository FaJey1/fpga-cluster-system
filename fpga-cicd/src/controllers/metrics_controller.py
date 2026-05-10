from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "service": "fpga-cicd"}


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    return "# fpga-cicd metrics\nfpga_cicd_up 1\n"
