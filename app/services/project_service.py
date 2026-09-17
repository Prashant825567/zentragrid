"""Project lifecycle."""

from __future__ import annotations

import logging
from typing import Optional

from app.core.errors import ConflictError, ProjectNotFoundError
from app.core.storage import Storage
from app.models.owner import Owner
from app.models.project import Project

logger = logging.getLogger("zentragrid.services.project")

MAX_PROJECTS_PER_OWNER = 50


class ProjectService:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    async def create(self, owner: Owner, *, name: str, description: Optional[str]) -> Project:
        existing = await self._storage.projects.list_for_owner(owner.owner_id)
        if len(existing) >= MAX_PROJECTS_PER_OWNER:
            raise ConflictError(
                f"Project limit reached ({MAX_PROJECTS_PER_OWNER}). Delete a project first."
            )
        if any(p.name.strip().lower() == name.strip().lower() for p in existing):
            raise ConflictError("A project with this name already exists.")

        project = await self._storage.projects.create_project(
            owner_id=owner.owner_id, name=name.strip(), description=description
        )
        await self._storage.usage.get_or_create(
            owner_id=owner.owner_id, project_id=project.project_id
        )
        logger.info("project_created owner_id=%s project_id=%s", owner.owner_id, project.project_id)
        return project

    async def list(self, owner: Owner) -> list[Project]:
        return await self._storage.projects.list_for_owner(owner.owner_id)

    async def get(self, owner: Owner, project_id: str) -> Project:
        project = await self._storage.projects.get_for_owner(project_id, owner.owner_id)
        if project is None:
            raise ProjectNotFoundError()
        return project

    async def delete(self, owner: Owner, project_id: str) -> None:
        """Soft-delete the project and revoke every key that pointed at it."""
        project = await self.get(owner, project_id)
        revoked = await self._storage.api_keys.revoke_all_for_project(project.project_id)
        await self._storage.projects.soft_delete(project)
        await self._storage.usage.flush(project.project_id)
        logger.info(
            "project_deleted owner_id=%s project_id=%s revoked_keys=%s",
            owner.owner_id,
            project_id,
            revoked,
        )
