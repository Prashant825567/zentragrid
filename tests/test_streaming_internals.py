"""Streaming internals: chunk sizing, media caching, and the replay guard.

These run offline with a fake Telethon-shaped iterator. They exist because a
subtle bug shipped once: Telethon's ``RequestIter.__aiter__`` *resets* the
stream, so mixing a manual ``__anext__()`` with ``async for`` silently
re-yielded the first chunk and corrupted every download.
"""

from __future__ import annotations

import pytest

from app.telegram.files import (
    ALIGNMENT,
    _normalise_chunk_size,
    _pick_chunk_size,
    _cache_get,
    _cache_put,
    _is_stale_reference,
    invalidate_media_cache,
    _MEDIA_CACHE,
)


# --------------------------------------------------------------- chunk sizes
@pytest.mark.parametrize(
    "value,expected",
    [(1, 4096), (4096, 4096), (4097, 8192), (65536, 65536),
     (700_000, 1048576), (1048576, 1048576), (99_999_999, 1048576)],
)
def test_normalise_chunk_size(value, expected):
    assert _normalise_chunk_size(value) == expected


def test_chunk_size_is_always_telegram_legal():
    """Must be a multiple of 4 KiB and divide 1 MiB exactly."""
    for value in [1, 5000, 70_000, 300_000, 900_000, 5_000_000]:
        size = _normalise_chunk_size(value)
        assert size % ALIGNMENT == 0
        assert (1024 * 1024) % size == 0


def test_small_reads_use_small_chunks():
    """A 64 KiB range must not drag a whole 1 MiB across the wire."""
    assert _pick_chunk_size(0, 64 * 1024) <= 64 * 1024


def test_large_reads_use_the_configured_maximum():
    assert _pick_chunk_size(0, 8 * 1024 * 1024) == 1024 * 1024


def test_unbounded_read_uses_configured_maximum():
    assert _pick_chunk_size(0, None) == 1024 * 1024


def test_chunk_size_accounts_for_alignment_waste():
    """Reading 4 KiB from a misaligned offset needs room for the discarded head."""
    offset = ALIGNMENT - 1  # 4095 bytes get thrown away
    size = _pick_chunk_size(offset, 4096)
    assert size >= 4095 + 4096


# -------------------------------------------------------------- media cache
def test_media_cache_roundtrip():
    _MEDIA_CACHE.clear()
    key = ("files", 42)
    assert _cache_get(key) is None
    _cache_put(key, "media-object")
    assert _cache_get(key) == "media-object"


def test_invalidate_removes_entry():
    _MEDIA_CACHE.clear()
    _cache_put(("files", 7), "x")
    invalidate_media_cache("files", 7)
    assert _cache_get(("files", 7)) is None


def test_cache_is_bounded_and_evicts_oldest():
    _MEDIA_CACHE.clear()
    for i in range(600):  # limit is 512
        _cache_put(("files", i), f"m{i}")
    assert len(_MEDIA_CACHE) <= 512
    assert _cache_get(("files", 0)) is None      # evicted
    assert _cache_get(("files", 599)) == "m599"  # kept


def test_cache_entries_expire(monkeypatch):
    import app.telegram.files as module

    _MEDIA_CACHE.clear()
    _cache_put(("files", 1), "old")
    monkeypatch.setattr(module.time, "monotonic", lambda: 10_000_000)
    assert _cache_get(("files", 1)) is None


def test_channels_do_not_share_cache_entries():
    _MEDIA_CACHE.clear()
    _cache_put(("files", 1), "from-files")
    _cache_put(("other", 1), "from-other")
    assert _cache_get(("files", 1)) == "from-files"
    assert _cache_get(("other", 1)) == "from-other"


# --------------------------------------------------- stale reference detect
@pytest.mark.parametrize(
    "exc",
    [
        Exception("FILE_REFERENCE_EXPIRED"),
        Exception("The file reference has expired (FILEREF_UPGRADE_NEEDED)"),
        Exception("LOCATION_INVALID"),
    ],
)
def test_stale_reference_detected(exc):
    assert _is_stale_reference(exc) is True


@pytest.mark.parametrize(
    "exc", [Exception("FLOOD_WAIT_42"), Exception("timeout"), ValueError("nope")]
)
def test_unrelated_errors_are_not_treated_as_stale(exc):
    assert _is_stale_reference(exc) is False


# ------------------------------------------- regression: no first-chunk replay
class _ResettingIter:
    """Mimics Telethon: ``__aiter__`` rewinds the stream back to the start."""

    def __init__(self, chunks):
        self._chunks = chunks
        self._i = 0

    def __aiter__(self):
        self._i = 0  # the trap
        return self

    async def __anext__(self):
        if self._i >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._i]
        self._i += 1
        return chunk


@pytest.mark.asyncio
async def test_manual_anext_then_async_for_would_replay():
    """Proves the trap exists, so the guard below is meaningful."""
    it = _ResettingIter([b"A", b"B", b"C"])
    first = await it.__anext__()
    rest = [c async for c in it]  # __aiter__ rewinds
    assert first == b"A"
    assert rest == [b"A", b"B", b"C"]  # A replayed


@pytest.mark.asyncio
async def test_driving_with_anext_only_is_correct():
    """The pattern iter_download actually uses: __aiter__ once, then __anext__."""
    iterator = _ResettingIter([b"A", b"B", b"C"]).__aiter__()
    first = await iterator.__anext__()

    out = [first]
    while True:
        try:
            out.append(await iterator.__anext__())
        except StopAsyncIteration:
            break

    assert out == [b"A", b"B", b"C"]
    assert b"".join(out) == b"ABC"
