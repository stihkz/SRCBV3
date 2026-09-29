# Copyright (c) 2025 devgagan : https://github.com/devgaganin.  
# Licensed under the GNU General Public License v3.0.  
# See LICENSE file in the repository root for full license text.

import asyncio
import sys
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from config import API_ID, API_HASH, BOT_TOKEN, STRING
from pyrogram import Client
from pyrogram.errors import PeerIdInvalid

# Pyrogram can raise PEER_ID_INVALID when a numeric channel/group ID has not
# yet been resolved into the current session's peer cache.  Resolve the peer
# from the session's dialogs and retry the original request.
_original_get_messages = Client.get_messages

async def _get_messages_peer_safe(self, chat_id, *args, **kwargs):
    try:
        return await _original_get_messages(self, chat_id, *args, **kwargs)
    except PeerIdInvalid:
        target = str(chat_id)
        target_clean = target.lstrip('@')
        print(f"PEER_ID_INVALID for {chat_id}; refreshing dialogs and retrying...")

        try:
            async for dialog in self.get_dialogs():
                chat = getattr(dialog, "chat", None)
                if not chat:
                    continue
                chat_id_str = str(getattr(chat, "id", ""))
                username = (getattr(chat, "username", None) or "").lstrip("@")
                if chat_id_str == target or username.lower() == target_clean.lower():
                    resolved_id = chat.id
                    print(f"Resolved peer {chat_id} -> {resolved_id}; retrying message lookup")
                    return await _original_get_messages(self, resolved_id, *args, **kwargs)
        except Exception as resolve_error:
            print(f"Peer refresh failed for {chat_id}: {resolve_error}")

        return await _original_get_messages(self, chat_id, *args, **kwargs)

Client.get_messages = _get_messages_peer_safe

client = TelegramClient("telethonbot", API_ID, API_HASH)
app = Client("pyrogrambot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
userbot = Client("4gbbot", api_id=API_ID, api_hash=API_HASH, session_string=STRING)

async def _start_telethon_with_flood_retry():
    """Start the Telethon bot without crashing Heroku on Telegram flood waits."""
    while not client.is_connected():
        try:
            await client.start(bot_token=BOT_TOKEN)
            print("Chalice started...")
            return
        except FloodWaitError as e:
            wait_seconds = max(1, int(e.seconds))
            print(
                f"Telegram authorization is rate-limited. Waiting {wait_seconds} "
                f"seconds before retrying instead of crashing the worker."
            )
            await asyncio.sleep(wait_seconds)
        except Exception:
            raise

async def start_client():
    await _start_telethon_with_flood_retry()

    if STRING:
        try:
            await userbot.start()
            print("Chalice user session started...")
        except FloodWaitError as e:
            wait_seconds = max(1, int(e.seconds))
            print(
                f"Telegram user-session authorization is rate-limited. "
                f"Waiting {wait_seconds} seconds before retrying."
            )
            await asyncio.sleep(wait_seconds)
            await userbot.start()
        except Exception as e:
            print(f"Chalice session error: {e}")
            sys.exit(1)

    await app.start()
    print("Chalice bot started...")
    return client, app, userbot
