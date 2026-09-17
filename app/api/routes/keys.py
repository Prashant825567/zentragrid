"""API key routes (dashboard, Firebase authenticated).

The plaintext key is returned by ``POST`` exactly once and can never be
retrieved again — only a 4-character hint is stored for display.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, status

from app.core.security import get_active_owner, get_owner_project, storage_dep
from app.core.storage import Storage
from app.models.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyList, ApiKeyPublic
from app.models.owner import Owner
from app.models.project import Project
from app.services.api_key_service import ApiKeyService

router = APIRouter(prefix="/projects/{project_id}/keys", tags=["api-keys"])


@router.post(
    "",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create an API key (plaintext shown once)",
)
async def create_key(
    payload: ApiKeyCreate = Body(default=ApiKeyCreate()),
    project: Project = Depends(get_owner_project),
    owner: Owner = Depends(get_active_owner),
    storage: Storage = Depends(storage_dep),
) -> ApiKeyCreated:
    return await ApiKeyService(storage).create(owner, project, name=payload.name)


@router.get("", response_model=ApiKeyList, summary="List API keys for a project")
async def list_keys(
    project: Project = Depends(get_owner_project),
    storage: Storage = Depends(storage_dep),
) -> ApiKeyList:
    keys = await ApiKeyService(storage).list(project)
    return ApiKeyList(keys=[k.public() for k in keys])


@router.delete("/{key_id}", response_model=ApiKeyPublic, summary="Revoke an API key")
async def revoke_key(
    key_id: str,
    project: Project = Depends(get_owner_project),
    owner: Owner = Depends(get_active_owner),
    storage: Storage = Depends(storage_dep),
) -> ApiKeyPublic:
    key = await ApiKeyService(storage).revoke(owner, project, key_id)
    return key.public()
