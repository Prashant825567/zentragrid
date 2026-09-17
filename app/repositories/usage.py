"""Usage repository (OWNERS channel).

Counters are mutated in memory immediately and flushed to Telegram lazily
(dirty-set + periodic/threshold flush) so a download does not cost a message
edit. Moving this to Redis later is a drop-in replacement of this class.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.models.usage import RECORD_TYPE_USAGE, UsageRecord
from app.repositories.base import IndexedRecordRepository
from app.telegram.messages import RecordChannel
from app.utils.ids import utc_now_iso

logger = logging.getLogger("zentragrid.usage")


class UsageRepository(IndexedRecordRepository[UsageRecord]):
    record_type = RECORD_TYPE_USAGE
    model = UsageRecord
    primary_key = "project_id"

    def __init__(self, channel: RecordChannel, flush_threshold: int = 20) -> None:
        super().__init__(channel)
        self._dirty: set[str] = set()
        self._flush_threshold = flush_threshold
        self._lock = asyncio.Lock()

    async def get_or_create(self, *, owner_id: str, project_id: str) -> UsageRecord:
        await self.ensure_loaded()
        record = self._by_pk.get(project_id)
        if record is None:
            record = UsageRecord(owner_id=owner_id, project_id=project_id)
            await self.create(record)
        return record

    async def increment(
        self,
        *,
        owner_id: str,
        project_id: str,
        files: int = 0,
        bytes_stored: int = 0,
        uploads: int = 0,
        downloads: int = 0,
        streams: int = 0,
        bandwidth_out: int = 0,
        api_requests: int = 0,
        flush: bool = False,
    ) -> UsageRecord:
        record = await self.get_or_create(owner_id=owner_id, project_id=project_id)
        async with self._lock:
            record.total_files = max(record.total_files + files, 0)
            record.total_bytes = max(record.total_bytes + bytes_stored, 0)
            record.uploads += uploads
            record.downloads += downloads
            record.streams += streams
            record.bandwidth_out_bytes += bandwidth_out
            record.api_requests += api_requests
            record.updated_at = utc_now_iso()
            self._dirty.add(project_id)
            should_flush = flush or len(self._dirty) >= self._flush_threshold

        if should_flush:
            await self.flush()
        return record

    async def flush(self, project_id: Optional[str] = None) -> None:
        """Persist dirty counters back into the OWNERS channel."""
        async with self._lock:
            targets = {project_id} & self._dirty if project_id else set(self._dirty)
            self._dirty -= targets
        for pid in targets:
            record = self._by_pk.get(pid)
            if record is None:
                continue
            try:
                await self.save(record)
            except Exception:  # pragma: no cover - never fail a request on usage
                logger.warning("usage_flush_failed project_id=%s", pid)
                async with self._lock:
                    self._dirty.add(pid)
