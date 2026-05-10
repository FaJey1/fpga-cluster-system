from .main import *


class ProjectIn(BaseModel):
    project_id: str
    project_name: str
    sources_url: str
    pipiline_id: str


class ProjectIdIn(BaseModel):
    project_id: str


@router.get("/get_queue")
async def get_queue(
    _: str = require_viewer,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        queue = await usecases.list_queue()
        return {"queue": queue}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/put_project")
async def put_project(
    payload: ProjectIn,
    _: str = require_operator,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        project = Project(
            project_id=payload.project_id,
            project_name=payload.project_name,
            sources_url=payload.sources_url,
            pipiline_id=payload.pipiline_id,
        )
        await usecases.put_project(project)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pop_project")
async def pop_project(
    _: str = require_operator,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        project = await usecases.pop_project()
        if project is None:
            return {"status": "empty"}
        return {"status": "ok", "project": project}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/remove_project")
async def remove_project(
    payload: ProjectIdIn,
    _: str = require_operator,
    usecases: MasterUseCases = Depends(get_usecases),
):
    try:
        removed, project = await usecases.remove_project(payload.project_id)
        return {"status": "ok", "removed": removed, "project": project}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
