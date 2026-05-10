from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Optional
from src.entities.project import Project
from src.usecases.master_usecases import MasterUseCases
from src.entities.token import ROLE_RANK

router = APIRouter()


async def get_usecases() -> MasterUseCases:
    raise RuntimeError("DI not configured: override get_usecases in main.py")


# ── RBAC helpers ──────────────────────────────────────────────────────────────

def _get_role(request: Request) -> str:
    return getattr(request.state, "role", "viewer")


def require_role(min_role: str):
    def dep(request: Request):
        role = _get_role(request)
        if ROLE_RANK.get(role, 0) < ROLE_RANK.get(min_role, 0):
            raise HTTPException(status_code=403, detail=f"Требуется роль: {min_role}")
        return role
    return Depends(dep)


require_admin = require_role("admin")
require_operator = require_role("operator")
require_viewer = require_role("viewer")
