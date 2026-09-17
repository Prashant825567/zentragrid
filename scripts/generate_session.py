"""Generate a Telethon StringSession for TG_SESSION.

Run once on your own machine (never on Render)::

    python scripts/generate_session.py

You will be prompted for your phone number, the Telegram login code and your
2FA password if enabled. The printed string is a FULL credential for your
Telegram account — store it only in Render's secret env vars.
"""

from __future__ import annotations

import asyncio
import os

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    api_id = os.getenv("TG_API_ID") or input("TG_API_ID: ").strip()
    api_hash = os.getenv("TG_API_HASH") or input("TG_API_HASH: ").strip()

    async with TelegramClient(StringSession(), int(api_id), api_hash) as client:
        session = client.session.save()
        me = await client.get_me()
        print("\n" + "=" * 70)
        print(f"Logged in as: {me.first_name} (@{me.username}) id={me.id}")
        print("=" * 70)
        print("\nTG_SESSION=" + session)
        print("\nStore this as a SECRET. Never commit it, never log it.\n")


if __name__ == "__main__":
    asyncio.run(main())
