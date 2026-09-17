"""Project repository (OWNERS channel)."""

from __future__ import annotations

from typing import Optional

from app.models.project import RECORD_TYPE_PROJECT, Project
from app.repositories.base import IndexedRecordRepository
from app.telegram.messages import RecordChannel
from app.utils.ids import new_project_id, utc_now_iso


class ProjectRepository(IndexedRecordRepository[Project]):
    record_type = RECORD_TYPE_PROJECT
    model = Project
    primary_key = "project_id"

    def __init__(self, channel: RecordChannel) -> None:
        super().__init__(channel)
        self._by_owner: dict[str, set[str]] = {}

    def _on_index(self, entity: Project) -> None:
        self._by_owner.setdefault(entity.owner_id, set()).add(entity.project_id)

    def _on_deindex(self, entity: Project) -> None:
        bucket = self._by_owner.get(entity.owner_id)
        if bucket:
            bucket.discard(entity.project_id)

    async def create_project(
        self, *, owner_id: str, name: str, description: Optional[str] = None
    ) -> Project:
        project = Project(
            project_id=new_project_id(),
            owner_id=owner_id,
            name=name,
            description=description,
        )
        return await self.create(project)

    async def list_for_owner(self, owner_id: str, include_deleted: bool = False) -> list[Project]:
        await self.ensure_loaded()
        ids = self._by_owner.get(owner_id, set())
        projects = [self._by_pk[pid] for pid in ids if pid in self._by_pk]
        if not include_deleted:
            projects = [p for p in projects if not p.deleted]
        return self._sorted(projects)

    async def get_for_owner(self, project_id: str, owner_id: str) -> Optional[Project]:
        """Ownership-scoped fetch — the only way routes should read a project."""
        project = await self.get(project_id)
        if not project or project.deleted or project.owner_id != owner_id:
            return None
        return project

    async def soft_delete(self, project: Project) -> Project:
        project.deleted = True
        project.updated_at = utc_now_iso()
        return await self.save(project)
