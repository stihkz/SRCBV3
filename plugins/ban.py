# Copyright (c) 2025 devgagan.
# Licensed under the GNU General Public License v3.0.

from pyrogram import filters, StopPropagation
from shared_client import app
from config import OWNER_ID
from utils.func import users_collection


def is_owner(user_id):
    """Handle OWNER_ID whether it is configured as ints, strings, or a list."""
    try:
        if isinstance(OWNER_ID, (list, tuple, set)):
            values = OWNER_ID
        else:
            values = str(OWNER_ID).replace(",", " ").split()
        return int(user_id) in {int(x) for x in values}
    except Exception:
        return False


async def get_target_user(client, message, argument=None):
    # Reply is the most reliable way to target a user, including users without usernames.
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user

    if not argument:
        return None

    argument = argument.strip()
    if argument.startswith("@"):
        argument = argument[1:]

    try:
        if argument.lstrip("-").isdigit():
            return await client.get_users(int(argument))
        return await client.get_users(argument)
    except Exception as e:
        print(f"Ban target lookup failed for {argument}: {e}")
        return None


async def get_banned(user_id):
    return await users_collection.find_one({"user_id": int(user_id), "bot_banned": True})


@app.on_message(filters.all, group=-100)
async def enforce_bot_ban(client, message):
    if not message.from_user:
        return

    user_id = message.from_user.id
    if is_owner(user_id):
        return

    if await get_banned(user_id):
        try:
            await message.reply_text("🚫 **You are banned from using this bot.**")
        except Exception as e:
            print(f"Could not send ban message to {user_id}: {e}")
        raise StopPropagation


@app.on_message(filters.command("ban"), group=0)
async def ban_user(client, message):
    print(f"/ban received from user_id={message.from_user.id if message.from_user else None}")

    if not message.from_user:
        return

    if not is_owner(message.from_user.id):
        await message.reply_text("❌ You are not authorized to use this command.")
        print(f"Unauthorized /ban attempt by {message.from_user.id}")
        return

    argument = message.command[1] if len(message.command) > 1 else None
    target = await get_target_user(client, message, argument)

    if not target:
        await message.reply_text(
            "Usage: `/ban @username` or `/ban user_id`\n\n"
            "You can also reply to a user's message with `/ban`."
        )
        return

    if is_owner(target.id):
        await message.reply_text("❌ You cannot ban an owner.")
        return

    await users_collection.update_one(
        {"user_id": target.id},
        {"$set": {
            "user_id": target.id,
            "bot_banned": True,
            "ban_username": target.username
        }},
        upsert=True,
    )

    name = f"@{target.username}" if target.username else (target.first_name or str(target.id))
    await message.reply_text(
        f"🚫 **{name} has been banned from using the bot.**\nID: `{target.id}`"
    )


@app.on_message(filters.command("unban"), group=0)
async def unban_user(client, message):
    if not message.from_user:
        return

    if not is_owner(message.from_user.id):
        await message.reply_text("❌ You are not authorized to use this command.")
        return

    argument = message.command[1] if len(message.command) > 1 else None
    target = await get_target_user(client, message, argument)

    if not target:
        await message.reply_text(
            "Usage: `/unban @username` or `/unban user_id`\n\n"
            "You can also reply to a user's message with `/unban`."
        )
        return

    result = await users_collection.update_one(
        {"user_id": target.id},
        {"$unset": {"bot_banned": "", "ban_username": ""}}
    )

    if result.modified_count:
        await message.reply_text(f"✅ User `{target.id}` has been unbanned.")
    else:
        await message.reply_text("ℹ️ That user is not currently banned.")


@app.on_message(filters.command("banned"), group=0)
async def list_banned(client, message):
    if not message.from_user:
        return

    if not is_owner(message.from_user.id):
        await message.reply_text("❌ You are not authorized to use this command.")
        return

    users = []
    async for user in users_collection.find({"bot_banned": True}):
        username = user.get("ban_username")
        user_id = user.get("user_id")
        users.append(f"@{username}" if username else str(user_id))

    if not users:
        await message.reply_text("✅ No users are currently banned.")
        return

    text = "🚫 **Banned users:**\n\n" + "\n".join(f"• {u}" for u in users)
    await message.reply_text(text)
