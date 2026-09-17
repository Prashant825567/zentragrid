"""Usage / quota routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import get_owner_project, storage_dep
from app.core.storage import Storage
from app.models.project import Project
from app.models.usage import UsagePublic
from app.services.usage_service import UsageService

router = APIRouter(prefix="/projects/{project_id}/usage", tags=["usage"])


@router.get("", response_model=UsagePublic, summary="Project usage and quota")
async def get_usage(
    project: Project = Depends(get_owner_project),
    storage: Storage = Depends(storage_dep),
) -> UsagePublic:
    return await UsageService(storage).public(project)
