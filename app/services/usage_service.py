"""Usage tracking & quota enforcement.

All counters live in the OWNERS channel as a per-project summary record. The
service API is deliberately narrow so the storage can move to Redis/a database
later without changing any caller.
"""

from __future__ import annotations

import logging

from app.core.errors import QuotaExceededError
from app.core.storage import Storage
from app.models.project import Project
from app.models.usage import UsagePublic, UsageRecord

logger = logging.getLogger("zentragrid.services.usage")


class UsageService:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    async def get(self, project: Project) -> UsageRecord:
        return await self._storage.usage.get_or_create(
            owner_id=project.owner_id, project_id=project.project_id
        )

    async def public(self, project: Project) -> UsagePublic:
        record = await self.get(project)
        return record.public(project.max_bytes, project.max_files)

    async def assert_can_store(self, project: Project, incoming_bytes: int) -> None:
        """Pre-flight quota check before accepting an upload."""
        record = await self.get(project)
        if record.total_files + 1 > project.max_files:
            raise QuotaExceededError(
                f"File count quota reached ({project.max_files} files)."
            )
        if incoming_bytes and record.total_bytes + incoming_bytes > project.max_bytes:
            raise QuotaExceededError(
                "Storage quota exceeded. Free up space or upgrade the plan."
            )

    async def record_upload(self, project: Project, size: int) -> None:
        await self._storage.usage.increment(
            owner_id=project.owner_id,
            project_id=project.project_id,
            files=1,
            bytes_stored=size,
            uploads=1,
            api_requests=1,
            flush=True,  # storage totals must be durable immediately
        )

    async def record_delete(self, project: Project, size: int) -> None:
        await self._storage.usage.increment(
            owner_id=project.owner_id,
            project_id=project.project_id,
            files=-1,
            bytes_stored=-size,
            api_requests=1,
            flush=True,
        )

    async def record_download(self, project: Project, bytes_out: int) -> None:
        await self._storage.usage.increment(
            owner_id=project.owner_id,
            project_id=project.project_id,
            downloads=1,
            bandwidth_out=bytes_out,
            api_requests=1,
        )

    async def record_stream(self, project: Project, bytes_out: int) -> None:
        await self._storage.usage.increment(
            owner_id=project.owner_id,
            project_id=project.project_id,
            streams=1,
            bandwidth_out=bytes_out,
            api_requests=1,
        )

    async def record_request(self, project: Project) -> None:
        await self._storage.usage.increment(
            owner_id=project.owner_id, project_id=project.project_id, api_requests=1
        )

    async def flush_all(self) -> None:
        await self._storage.usage.flush()
