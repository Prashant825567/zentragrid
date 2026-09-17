"""API key repository (OWNERS channel).

Lookups happen on the peppered hash, so the plaintext key never needs to be
stored or compared in bulk.
"""

from __future__ import annotations

from typing import Optional

from app.models.api_key import RECORD_TYPE_API_KEY, ApiKey
from app.repositories.base import IndexedRecordRepository
from app.telegram.messages import RecordChannel
from app.utils.hashing import generate_api_key, hash_api_key
from app.utils.ids import new_key_id, utc_now_iso


class ApiKeyRepository(IndexedRecordRepository[ApiKey]):
    record_type = RECORD_TYPE_API_KEY
    model = ApiKey
    primary_key = "key_id"

    def __init__(self, channel: RecordChannel) -> None:
        super().__init__(channel)
        self._by_hash: dict[str, str] = {}
        self._by_project: dict[str, set[str]] = {}

    def _on_index(self, entity: ApiKey) -> None:
        self._by_hash[entity.key_hash] = entity.key_id
        self._by_project.setdefault(entity.project_id, set()).add(entity.key_id)

    def _on_deindex(self, entity: ApiKey) -> None:
        self._by_hash.pop(entity.key_hash, None)
        bucket = self._by_project.get(entity.project_id)
        if bucket:
            bucket.discard(entity.key_id)

    async def issue(
        self, *, owner_id: str, project_id: str, name: Optional[str] = None
    ) -> tuple[ApiKey, str]:
        """Create a key. Returns ``(record, plaintext)`` — plaintext is shown once."""
        plaintext = generate_api_key()
        record = ApiKey(
            key_id=new_key_id(),
            owner_id=owner_id,
            project_id=project_id,
            name=name,
            key_hash=hash_api_key(plaintext),
            key_hint=plaintext[-4:],
        )
        await self.create(record)
        return record, plaintext

    async def get_by_plaintext(self, plaintext: str) -> Optional[ApiKey]:
        await self.ensure_loaded()
        key_id = self._by_hash.get(hash_api_key(plaintext))
        return self._by_pk.get(key_id) if key_id else None

    async def list_for_project(self, project_id: str) -> list[ApiKey]:
        await self.ensure_loaded()
        ids = self._by_project.get(project_id, set())
        return self._sorted([self._by_pk[kid] for kid in ids if kid in self._by_pk])

    async def revoke(self, key: ApiKey) -> ApiKey:
        key.revoked = True
        key.updated_at = utc_now_iso()
        return await self.save(key)

    async def revoke_all_for_project(self, project_id: str) -> int:
        keys = [k for k in await self.list_for_project(project_id) if not k.revoked]
        for key in keys:
            await self.revoke(key)
        return len(keys)

    async def touch(self, key: ApiKey) -> None:
        """Record last usage.

        Only persisted at most once per minute to avoid an edit round-trip on
        every single API call.
        """
        now = utc_now_iso()
        if key.last_used_at and key.last_used_at[:16] == now[:16]:
            return
        key.last_used_at = now
        await self.save(key)
