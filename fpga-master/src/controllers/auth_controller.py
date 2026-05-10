from typing import Optional
from pydantic import BaseModel, Field
from fastapi import Request

from .main import router, get_usecases, MasterUseCases, Depends, HTTPException, require_admin


class IssueTokenRequest(BaseModel):
    role: str = Field(..., description="admin | operator | viewer")
    description: str = ""
    ttl_seconds: Optional[int] = Field(None, description="TTL in seconds; None = never expires")


@router.post("/auth/tokens", tags=["auth"])
async def issue_token(
    body: IssueTokenRequest,
    _: str = require_admin,
    usecases: MasterUseCases = Depends(get_usecases),
):
    """Issue a new token (admin only)."""
    if usecases.token_uc is None:
        raise HTTPException(500, "Token service not initialized")
    try:
        token = await usecases.token_uc.issue_token(
            role=body.role,
            description=body.description,
            ttl_seconds=body.ttl_seconds,
        )
        return token.to_dict()
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/auth/tokens", tags=["auth"])
async def list_tokens(
    _: str = require_admin,
    usecases: MasterUseCases = Depends(get_usecases),
):
    """List all active tokens without plaintext values (admin only)."""
    if usecases.token_uc is None:
        raise HTTPException(500, "Token service not initialized")
    return await usecases.token_uc.list_tokens()


@router.delete("/auth/tokens/{token_id}", tags=["auth"])
async def revoke_token(
    token_id: str,
    _: str = require_admin,
    usecases: MasterUseCases = Depends(get_usecases),
):
    """Revoke a token by ID (admin only; root token cannot be revoked)."""
    if usecases.token_uc is None:
        raise HTTPException(500, "Token service not initialized")
    ok = await usecases.token_uc.revoke_token(token_id)
    if not ok:
        raise HTTPException(404, "Token not found or is a root token")
    return {"status": "revoked", "token_id": token_id}


@router.get("/auth/whoami", tags=["auth"])
async def whoami(request: Request):
    """Return current token metadata (any authenticated user)."""
    token = getattr(request.state, "token", None)
    if token is None:
        raise HTTPException(401, "Not authenticated")
    safe = {k: v for k, v in token.items() if k != "token"}
    return safe
