from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any

from fpga_worker.usecases.worker_usecases import WorkerUseCases

router = APIRouter()


async def get_usecases() -> WorkerUseCases:
    raise RuntimeError("DI not configured: override get_usecases in main.py")
