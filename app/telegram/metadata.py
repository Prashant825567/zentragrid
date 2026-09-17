"""METADATA channel binding.

Holds one JSON record per uploaded file, pointing at the message id of the
blob inside the FILES channel.
"""

from __future__ import annotations

from app.telegram.messages import RecordChannel
from app.telegram.records import TelegramRecordChannel


def build_metadata_channel(channel_id: str) -> RecordChannel:
    return TelegramRecordChannel(channel_id, label="metadata")
