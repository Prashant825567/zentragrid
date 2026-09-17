"""Telethon MTProto client lifecycle.

The client is a lazily-created process-wide singleton guarded by a lock so
concurrent requests share one MTProto connection. Credentials come from the
environment only (``TG_API_ID`` / ``TG_API_HASH`` / ``TG_SESSION``) and are
never logged or returned by any endpoint.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Union

from app.core.config import settings
from app.core.errors import ConfigurationError, StorageBackendError

logger = logging.getLogger("zentragrid.telegram")

_client = None  # type: ignore[var-annotated]
_lock = asyncio.Lock()
_entity_cache: dict[str, object] = {}


def _parse_channel(raw: str) -> Union[int, str]:
    """Channel ids may be numeric (-100…) or a @username / invite-less handle."""
    raw = str(raw).strip()
    try:
        return int(raw)
    except ValueError:
        return raw


async def get_client():
    """Return a connected, authorised Telethon client."""
    global _client

    if settings.STORAGE_BACKEND != "telegram":
        raise ConfigurationError("Telegram client requested while STORAGE_BACKEND is not 'telegram'.")
    if not settings.telegram_configured:
        raise ConfigurationError(
            "Telegram is not configured. Set TG_API_ID, TG_API_HASH, TG_SESSION and the "
            "three channel ids."
        )

    if _client is not None and _client.is_connected():
        return _client

    async with _lock:
        if _client is not None and _client.is_connected():
            return _client

        # Imported lazily so unit tests never need Telethon configured.
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        client = TelegramClient(
            StringSession(settings.TG_SESSION),
            settings.TG_API_ID,
            settings.TG_API_HASH,
            connection_retries=3,
            request_retries=3,
            timeout=settings.TG_CONNECT_TIMEOUT,
            auto_reconnect=True,
        )
        try:
            await client.connect()
        except Exception as exc:  # pragma: no cover - network dependent
            logger.error("telegram_connect_failed error=%s", type(exc).__name__)
            raise StorageBackendError("Could not connect to Telegram.") from exc

        if not await client.is_user_authorized():
            await client.disconnect()
            raise ConfigurationError(
                "TG_SESSION is not authorised. Regenerate the string session."
            )

        _client = client
        logger.info("telegram_client_ready")
        return _client


async def close_client() -> None:
    """Disconnect on application shutdown."""
    global _client
    if _client is not None:
        try:
            await _client.disconnect()
        except Exception:  # pragma: no cover
            logger.warning("telegram_disconnect_failed")
        finally:
            _client = None
            _entity_cache.clear()
            logger.info("telegram_client_closed")


async def resolve_entity(channel: str):
    """Resolve (and cache) a private channel entity.

    Resolution is cached because ``get_entity`` is a network round trip and the
    three storage channels never change at runtime.
    """
    key = str(channel)
    if key in _entity_cache:
        return _entity_cache[key]

    client = await get_client()
    try:
        entity = await client.get_entity(_parse_channel(channel))
    except Exception as exc:
        logger.error("telegram_entity_resolve_failed error=%s", type(exc).__name__)
        raise StorageBackendError(
            "Storage channel could not be resolved. Check the channel id and that the "
            "session account is a member."
        ) from exc

    _entity_cache[key] = entity
    return entity


async def healthcheck() -> dict:
    """Lightweight connectivity probe used by /health."""
    if settings.STORAGE_BACKEND != "telegram":
        return {"backend": settings.STORAGE_BACKEND, "connected": True}
    try:
        client = await get_client()
        me = await client.get_me()
        return {"backend": "telegram", "connected": bool(me), "authorized": True}
    except Exception as exc:
        return {"backend": "telegram", "connected": False, "error": type(exc).__name__}
