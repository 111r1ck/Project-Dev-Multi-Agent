from fastapi import APIRouter

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/{project_id}")
async def get_project(project_id: str):
    return {"project_id": project_id, "status": "not_implemented"}
