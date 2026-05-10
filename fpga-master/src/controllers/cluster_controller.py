from .main import *


@router.get("/get_masters")
async def get_masters(
    _: str = require_viewer,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        return await usecases.get_masters()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_workers")
async def get_workers(
    _: str = require_viewer,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        return await usecases.get_workers()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/who_master")
async def who_master(
    _: str = require_viewer,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        return await usecases.is_quorum_master()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quorum")
async def quorum(
    _: str = require_viewer,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        return await usecases.quorum_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
