"""Composition root for the storage layer.

Everything above this module depends on repositories, and repositories depend
on the abstract channel contracts. Replacing Telegram later = editing only the
``_build_*`` functions here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.core.config import settings
from app.repositories.api_keys import ApiKeyRepository
from app.repositories.documents import DocumentRepository
from app.repositories.files import FileRepository
from app.repositories.owners import OwnerRepository
from app.repositories.projects import ProjectRepository
from app.repositories.usage import UsageRepository
from app.telegram.messages import MediaChannel, RecordChannel

logger = logging.getLogger("zentragrid.storage")


@dataclass
class Storage:
    owners: OwnerRepository
    projects: ProjectRepository
    api_keys: ApiKeyRepository
    files: FileRepository
    usage: UsageRepository
    documents: DocumentRepository
    media: MediaChannel

    async def warm(self) -> None:
        """Preload all indexes so the first request is not penalised."""
        for repo in (
            self.owners,
            self.projects,
            self.api_keys,
            self.files,
            self.usage,
            self.documents,
        ):
            await repo.ensure_loaded()


_storage: Optional[Storage] = None


def _build_channels() -> tuple[RecordChannel, RecordChannel, RecordChannel, MediaChannel]:
    """Return ``(owners, metadata, data, files)`` channels."""
    if settings.STORAGE_BACKEND == "memory":
        from app.telegram.memory import InMemoryMediaChannel, InMemoryRecordChannel

        logger.warning("storage_backend=memory (non-persistent, development only)")
        metadata = InMemoryRecordChannel()
        return InMemoryRecordChannel(), metadata, metadata, InMemoryMediaChannel()

    from app.telegram.data import build_data_channel
    from app.telegram.files import TelegramMediaChannel
    from app.telegram.metadata import build_metadata_channel
    from app.telegram.owners import build_owners_channel

    metadata_channel = build_metadata_channel(settings.TG_METADATA_CHANNEL)
    # A dedicated DATA channel is optional. Without one, documents share the
    # METADATA channel: correct (records are filtered by ``record_type``) but
    # slower to warm, because both indexes scan the same history.
    if settings.TG_DATA_CHANNEL:
        data_channel: RecordChannel = build_data_channel(settings.TG_DATA_CHANNEL)
    else:
        logger.info("data_channel_shared_with_metadata")
        data_channel = metadata_channel

    return (
        build_owners_channel(settings.TG_OWNERS_CHANNEL),
        metadata_channel,
        data_channel,
        TelegramMediaChannel(settings.TG_FILES_CHANNEL),
    )


def build_storage() -> Storage:
    owners_channel, metadata_channel, data_channel, media_channel = _build_channels()
    return Storage(
        owners=OwnerRepository(owners_channel),
        projects=ProjectRepository(owners_channel),
        api_keys=ApiKeyRepository(owners_channel),
        usage=UsageRepository(owners_channel),
        files=FileRepository(metadata_channel),
        documents=DocumentRepository(data_channel),
        media=media_channel,
    )


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = build_storage()
    return _storage


def set_storage(storage: Optional[Storage]) -> None:
    """Test hook for injecting a fully in-memory storage container."""
    global _storage
    _storage = storage
