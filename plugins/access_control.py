# Chalice access control: free-use limits + private-source membership checks.
# This plugin intentionally runs in a higher-priority handler group so the
# existing batch.py flow remains unchanged for allowed requests.

from datetime import datetime, timezone

from pyrogram import Client, filters
from pyrogram.errors import UserNotParticipant
from pyrogram.enums import ChatMemberStatus

from config import FREEMIUM_LIMIT
from shared_client import app as X
from utils.func import E, get_user_data, is_premium_user
from plugins import batch as batch_plugin

try:
    from utils.func import users_collection
except Exception:
    users_collection = None


async def _reserve_free_quota(user_id: int, amount: int) -> bool:
    """Reserve up to amount of free downloads for the current UTC day."""
    if amount <= 0:
        return True
    if await is_premium_user(user_id):
        return True
    if FREEMIUM_LIMIT <= 0:
        return False
    if users_collection is None:
        # Fail closed: do not accidentally make free access unlimited if the DB
        # counter is unavailable.
        return False

    today = datetime.now(timezone.utc).date().isoformat()
    doc = await users_collection.find_one({"user_id": int(user_id)}) or {}
    used = int(doc.get("free_usage_count", 0) or 0)
    usage_date = doc.get("free_usage_date")

    if usage_date != today:
        used = 0

    if used + amount > FREEMIUM_LIMIT:
        return False

    await users_collection.update_one(
        {"user_id": int(user_id)},
        {"$set": {"free_usage_date": today, "free_usage_count": used + amount}},
        upsert=True,
    )
    return True


async def _private_source_allowed(user_id: int, link: str) -> bool:
    """Premium users may use the existing service session; free users must
    actually belong to the private source chat.
    """
    chat_id, _, link_type = E(link)
    if link_type != "private":
        return True

    if await is_premium_user(user_id):
        return True

    uclient = await batch_plugin.get_uclient(user_id)
    if not uclient:
        return False

    try:
        member = await uclient.get_chat_member(int(chat_id), int(user_id))
        status = str(member.status).lower()
        if status in {
            ChatMemberStatus.MEMBER.value,
            ChatMemberStatus.ADMINISTRATOR.value,
            ChatMemberStatus.OWNER.value,
        }:
            return True
        if status == ChatMemberStatus.RESTRICTED.value:
            return bool(getattr(member, "is_member", False))
        return False
    except UserNotParticipant:
        return False
    except Exception as exc:
        print(f"Private membership check failed for user={user_id}, chat={chat_id}: {type(exc).__name__}: {exc}")
        return False


@X.on_message(filters.command(["batch", "single"]), group=-1)
async def access_command_guard(client, message):
    uid = message.from_user.id
    cmd = message.command[0].lower()

    if await is_premium_user(uid):
        return

    if FREEMIUM_LIMIT <= 0:
        await message.reply_text(
            "🔒 Free downloads are disabled. Please upgrade to Premium to use this feature."
        )
        message.stop_propagation()
        return

    # /single consumes one free slot when it is started. /batch is checked
    # against the requested count when the count is sent below.
    if cmd == "single":
        if not await _reserve_free_quota(uid, 1):
            await message.reply_text(
                f"⚠️ You have reached your free daily limit ({FREEMIUM_LIMIT})."
            )
            message.stop_propagation()


@X.on_message(filters.text, group=-1)
async def access_flow_guard(client, message):
    if not message.from_user:
        return

    uid = message.from_user.id
    state = batch_plugin.Z.get(uid)
    if not state:
        return

    step = state.get("step")

    # /batch asks for the number of messages in a separate text update.
    if step == "count":
        try:
            count = int(message.text.strip())
        except (TypeError, ValueError):
            return

        if count < 1 or count > 100:
            return

        if not await is_premium_user(uid):
            if FREEMIUM_LIMIT <= 0:
                await message.reply_text("🔒 Free batch downloads are disabled. Please upgrade to Premium.")
                message.stop_propagation()
                return
            if not await _reserve_free_quota(uid, count):
                await message.reply_text(
                    f"⚠️ Your free daily limit is {FREEMIUM_LIMIT} download(s). You requested {count}."
                )
                message.stop_propagation()
                return
        return

    # Once a /batch or /single flow asks for the source link, enforce access
    # to private groups/channels for non-premium users.
    if step not in {"start", "start_single"}:
        return

    link = (message.text or "").strip()
    try:
        _, _, link_type = E(link)
    except Exception:
        return

    if link_type != "private":
        return

    if not await _private_source_allowed(uid, link):
        await message.reply_text(
            "🔒 You must be a member of that private group/channel to download its posts. Premium users may use their Premium access."
        )
        message.stop_propagation()
