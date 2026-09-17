"""Repository foundations.

`IndexedRecordRepository` warms an in-process index from the record channel
exactly once at startup, then keeps it in sync on every write. That is what
makes lookups O(1) instead of scanning a Telegram channel per request.

The index is deliberately a plain dict behind a tiny interface so it can be
swapped for Redis or a real search index later without touching services.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Generic, Iterable, Optional, TypeVar

from pydantic import BaseModel, ValidationError

from app.telegram.messages import RecordChannel, StoredRecord

logger = logging.getLogger("zentragrid.repositories")

ModelT = TypeVar("ModelT", bound=BaseModel)


class IndexedRecordRepository(Generic[ModelT]):
    """Base class for all record repositories backed by a :class:`RecordChannel`."""

    record_type: str = ""
    model: type[BaseModel]
    primary_key: str = "id"

    def __init__(self, channel: RecordChannel) -> None:
        self._channel = channel
        self._by_pk: dict[str, ModelT] = {}
        self._message_ids: dict[str, int] = {}
        self._loaded = False
        self._load_lock = asyncio.Lock()

    # --------------------------------------------------------------- index
    async def ensure_loaded(self) -> None:
        if self._loaded:
            return
        async with self._load_lock:
            if self._loaded:
                return
            count = 0
            async for record in self._channel.iter_records():
                if record.data.get("record_type") != self.record_type:
                    continue
                entity = self._parse(record)
                if entity is not None:
                    self._index(entity, record.message_id)
                    count += 1
            self._loaded = True
            logger.info("index_loaded type=%s count=%s", self.record_type, count)

    def _parse(self, record: StoredRecord) -> Optional[ModelT]:
        try:
            return self.model.model_validate(record.data)  # type: ignore[return-value]
        except ValidationError:
            logger.warning(
                "corrupt_record_skipped type=%s message_id=%s",
                self.record_type,
                record.message_id,
            )
            return None

    def _pk(self, entity: ModelT) -> str:
        return getattr(entity, self.primary_key)

    def _index(self, entity: ModelT, message_id: int) -> None:
        pk = self._pk(entity)
        self._by_pk[pk] = entity
        self._message_ids[pk] = message_id
        self._on_index(entity)

    def _deindex(self, pk: str) -> None:
        entity = self._by_pk.pop(pk, None)
        self._message_ids.pop(pk, None)
        if entity is not None:
            self._on_deindex(entity)

    # Subclasses override these to maintain secondary indexes.
    def _on_index(self, entity: ModelT) -> None:  # noqa: B027
        pass

    def _on_deindex(self, entity: ModelT) -> None:  # noqa: B027
        pass

    # ---------------------------------------------------------------- CRUD
    async def create(self, entity: ModelT) -> ModelT:
        await self.ensure_loaded()
        record = await self._channel.append(entity.model_dump(mode="json"))
        self._index(entity, record.message_id)
        return entity

    async def save(self, entity: ModelT) -> ModelT:
        """Update an existing record in place (falls back to create)."""
        await self.ensure_loaded()
        pk = self._pk(entity)
        message_id = self._message_ids.get(pk)
        if message_id is None:
            return await self.create(entity)
        await self._channel.update(message_id, entity.model_dump(mode="json"))
        self._index(entity, message_id)
        return entity

    async def get(self, pk: str) -> Optional[ModelT]:
        await self.ensure_loaded()
        return self._by_pk.get(pk)

    async def hard_delete(self, pk: str) -> None:
        await self.ensure_loaded()
        message_id = self._message_ids.get(pk)
        if message_id is not None:
            await self._channel.delete(message_id)
        self._deindex(pk)

    async def list_all(self) -> list[ModelT]:
        await self.ensure_loaded()
        return list(self._by_pk.values())

    async def find(self, predicate: Callable[[ModelT], bool]) -> list[ModelT]:
        await self.ensure_loaded()
        return [entity for entity in self._by_pk.values() if predicate(entity)]

    def _sorted(self, items: Iterable[ModelT], key: str = "created_at") -> list[ModelT]:
        return sorted(items, key=lambda item: getattr(item, key, "") or "")

    # Test/maintenance helper.
    def reset_index(self) -> None:
        self._by_pk.clear()
        self._message_ids.clear()
        self._loaded = False

    def message_id_of(self, pk: str) -> Optional[int]:
        """Internal pointer — must never be serialised into an API response."""
        return self._message_ids.get(pk)


def dump(entity: BaseModel) -> dict[str, Any]:
    return entity.model_dump(mode="json")
