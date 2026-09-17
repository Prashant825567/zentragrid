"""API key issuance and revocation."""

from __future__ import annotations

import logging
from typing import Optional

from app.core.errors import ApiKeyNotFoundError, ConflictError
from app.core.storage import Storage
from app.models.api_key import ApiKey, ApiKeyCreated
from app.models.owner import Owner
from app.models.project import Project

logger = logging.getLogger("zentragrid.services.api_key")

MAX_ACTIVE_KEYS_PER_PROJECT = 20


class ApiKeyService:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    async def create(
        self, owner: Owner, project: Project, *, name: Optional[str]
    ) -> ApiKeyCreated:
        keys = await self._storage.api_keys.list_for_project(project.project_id)
        if sum(1 for k in keys if not k.revoked) >= MAX_ACTIVE_KEYS_PER_PROJECT:
            raise ConflictError(
                f"Active key limit reached ({MAX_ACTIVE_KEYS_PER_PROJECT}). Revoke a key first."
            )

        record, plaintext = await self._storage.api_keys.issue(
            owner_id=owner.owner_id, project_id=project.project_id, name=name
        )
        # key_id is safe to log; the plaintext key is not.
        logger.info(
            "api_key_created owner_id=%s project_id=%s key_id=%s",
            owner.owner_id,
            project.project_id,
            record.key_id,
        )
        return ApiKeyCreated(key=record.public(), api_key=plaintext)

    async def list(self, project: Project) -> list[ApiKey]:
        return await self._storage.api_keys.list_for_project(project.project_id)

    async def revoke(self, owner: Owner, project: Project, key_id: str) -> ApiKey:
        key = await self._storage.api_keys.get(key_id)
        if (
            key is None
            or key.project_id != project.project_id
            or key.owner_id != owner.owner_id
        ):
            raise ApiKeyNotFoundError()
        if key.revoked:
            return key
        key = await self._storage.api_keys.revoke(key)
        logger.info("api_key_revoked project_id=%s key_id=%s", project.project_id, key_id)
        return key
