"""Project routes (dashboard, Firebase authenticated)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.core.security import get_active_owner, get_owner_project, storage_dep
from app.core.storage import Storage
from app.models.owner import Owner
from app.models.project import Project, ProjectCreate, ProjectList, ProjectPublic
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post(
    "",
    response_model=ProjectPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project",
)
async def create_project(
    payload: ProjectCreate,
    owner: Owner = Depends(get_active_owner),
    storage: Storage = Depends(storage_dep),
) -> ProjectPublic:
    # owner_id is taken from the verified token, never from the request body.
    project = await ProjectService(storage).create(
        owner, name=payload.name, description=payload.description
    )
    return project.public()


@router.get("", response_model=ProjectList, summary="List the owner's projects")
async def list_projects(
    owner: Owner = Depends(get_active_owner),
    storage: Storage = Depends(storage_dep),
) -> ProjectList:
    projects = await ProjectService(storage).list(owner)
    return ProjectList(projects=[p.public() for p in projects])


@router.get("/{project_id}", response_model=ProjectPublic, summary="Get a project")
async def get_project(project: Project = Depends(get_owner_project)) -> ProjectPublic:
    return project.public()


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a project and revoke its API keys",
)
async def delete_project(
    project: Project = Depends(get_owner_project),
    owner: Owner = Depends(get_active_owner),
    storage: Storage = Depends(storage_dep),
) -> Response:
    await ProjectService(storage).delete(owner, project.project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
