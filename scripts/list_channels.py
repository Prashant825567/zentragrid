"""Print the ids of private channels your session account can access.

Use the output to fill TG_FILES_CHANNEL / TG_METADATA_CHANNEL /
TG_OWNERS_CHANNEL::

    python scripts/list_channels.py
"""

from __future__ import annotations

import asyncio
import os

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Channel


async def main() -> None:
    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]
    session = os.environ["TG_SESSION"]

    async with TelegramClient(StringSession(session), api_id, api_hash) as client:
        print(f"{'channel id':>16}  {'private':>7}  title")
        print("-" * 70)
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if isinstance(entity, Channel) and not entity.megagroup:
                private = "yes" if not entity.username else "NO (public)"
                print(f"{dialog.id:>16}  {private:>7}  {dialog.name}")

    print("\nCopy the ids (including the leading -100) into your environment.")


if __name__ == "__main__":
    asyncio.run(main())
