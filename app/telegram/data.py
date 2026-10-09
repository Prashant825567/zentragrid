"""DATA channel binding.

Holds one JSON record per document in the document store. Optional: when
``TG_DATA_CHANNEL`` is unset the document repository shares the METADATA
channel instead, which still works because records are keyed by
``record_type``.
"""

from __future__ import annotations

from app.telegram.messages import RecordChannel
from app.telegram.records import TelegramRecordChannel


def build_data_channel(channel_id: str) -> RecordChannel:
    return TelegramRecordChannel(channel_id, label="data")
