# Copyright (c) 2025 devgagan.
# Licensed under the GNU General Public License v3.0.

import asyncio

from pyrogram import filters
from pyrogram.errors import FloodWait, RPCError

from shared_client import app
import config
from utils.func import users_collection


def is_broadcast_admin(user_id):
    try:
        allowed = {int(x) for x in getattr(config, "OWNER_ID", [])}
        allowed.update(int(x) for x in getattr(config, "ADMIN_ID", []))
        return int(user_id) in allowed
    except Exception as e:
        print(f"Broadcast admin check failed: {e}")
        return False


async def send_broadcast(client, target_id, source_message=None, text=None):
    while True:
        try:
            if source_message is not None:
                await client.copy_message(
                    chat_id=target_id,
                    from_chat_id=source_message.chat.id,
                    message_id=source_message.id,
                )
            else:
                await client.send_message(target_id, text)
            return True
        except FloodWait as e:
            wait = int(getattr(e, "value", 1))
            print(f"Broadcast FloodWait: waiting {wait}s")
            await asyncio.sleep(wait)
        except RPCError as e:
            print(f"Broadcast failed for {target_id}: {e}")
            return False
        except Exception as e:
            print(f"Broadcast failed for {target_id}: {e}")
            return False


@app.on_message(filters.command("broadcast") & filters.private)
async def broadcast(client, message):
    if not message.from_user:
        return

    if not is_broadcast_admin(message.from_user.id):
        await message.reply_text("❌ You are not authorized to use this command.")
        return

    source_message = message.reply_to_message
    text = message.text.split(maxsplit=1)[1].strip() if len(message.text.split(maxsplit=1)) > 1 else None

    if source_message is None and not text:
        await message.reply_text(
            "📢 **Broadcast usage**\n\n"
            "• `/broadcast Your announcement` — send a text announcement\n"
            "• Reply to a message with `/broadcast` — broadcast that message/media"
        )
        return

    status = await message.reply_text("📢 Starting broadcast...")

    cursor = users_collection.find({"bot_banned": {"$ne": True}}, {"user_id": 1})
    sent = 0
    failed = 0
    total = 0

    async for user in cursor:
        user_id = user.get("user_id")
        if not user_id:
            continue
        total += 1
        if await send_broadcast(client, int(user_id), source_message=source_message, text=text):
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)

    try:
        await status.edit_text(
            "📢 **Broadcast completed**\n\n"
            f"👥 Recipients: `{total}`\n"
            f"✅ Sent: `{sent}`\n"
            f"❌ Failed: `{failed}`"
        )
    except Exception:
        pass


print("Chalice broadcast plugin loaded.")
