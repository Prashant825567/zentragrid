"""OWNERS channel binding.

Holds owner records, project records, API-key metadata, plan/quota info and
usage summaries. Never contains raw uploaded media.
"""

from __future__ import annotations

from app.telegram.messages import RecordChannel
from app.telegram.records import TelegramRecordChannel


def build_owners_channel(channel_id: str) -> RecordChannel:
    return TelegramRecordChannel(channel_id, label="owners")
