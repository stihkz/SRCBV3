# Chalice access-control layer.
# Keeps the downloader itself intact while enforcing:
#   1) a persistent daily FREEMIUM_LIMIT for non-premium users
#   2) private-source access only through the requesting user's own /login session

from datetime import datetime, timezone

from pyrogram import filters
from pyrogram.errors import UserNotParticipant
from pyrogram.enums import ChatMemberStatus

from config import FREEMIUM_LIMIT
from shared_client import app as X
from utils.func import E, get_user_data_key, save_user_data, is_premium_user
from plugins import batch as batch_plugin


_ORIGINAL_GET_UCLIENT = None
_ORIGINAL_PROCESS_MSG = None


def _today():
    return datetime.now(timezone.utc).date().isoformat()


async def _get_usage(user_id: int) -> int:
    day = await get_user_data_key(user_id, "free_usage_date", None)
    count = await get_user_data_key(user_id, "free_usage_count", 0)
    try:
        count = max(0, int(count or 0))
    except (TypeError, ValueError):
        count = 0
    if day != _today():
        return 0
    return count


async def _has_free_slot(user_id: int) -> bool:
    if await is_premium_user(user_id):
        return True
    if FREEMIUM_LIMIT <= 0:
        return False
    return await _get_usage(user_id) < FREEMIUM_LIMIT


async def _record_success(user_id: int):
    if await is_premium_user(user_id) or FREEMIUM_LIMIT <= 0:
        return
    current = await _get_usage(user_id)
    await save_user_data(user_id, "free_usage_date", _today())
    await save_user_data(user_id, "free_usage_count", current + 1)


async def _gated_get_uclient(uid: int):
    """For private links, never fall back to the bot owner's/global STRING session."""
    state = batch_plugin.Z.get(uid, {})
    if state.get("lt") == "private":
        user_session = await get_user_data_key(uid, "session_string", None)
        if not user_session:
            return None
    return await _ORIGINAL_GET_UCLIENT(uid)


async def _gated_process_msg(c, u, m, d, lt, uid, i):
    """Count only successful extractions, so failed downloads do not consume quota."""
    if not await _has_free_slot(uid):
        if FREEMIUM_LIMIT <= 0:
            return "🔒 Free downloads are disabled. Please upgrade to Premium."
        return f"⚠️ You have reached your free daily limit ({FREEMIUM_LIMIT}).\n\n💎 DM @freebandslime to gain Premium features."

    result = await _ORIGINAL_PROCESS_MSG(c, u, m, d, lt, uid, i)
    if isinstance(result, str) and (result.startswith("Done") or result.startswith("Sent")):
        await _record_success(uid)
    return result


async def _private_source_allowed(user_id: int, link: str) -> bool:
    """Free users must be logged in and actually be members of the private source."""
    chat_id, _, link_type = E(link)
    if link_type != "private":
        return True

    if await is_premium_user(user_id):
        return True

    session = await get_user_data_key(user_id, "session_string", None)
    if not session:
        return False

    try:
        user_client = await _ORIGINAL_GET_UCLIENT(user_id)
        if not user_client:
            return False

        member = await user_client.get_chat_member(int(chat_id), int(user_id))
        status = getattr(member, "status", None)
        status_value = getattr(status, "value", str(status).lower())
        if status_value in {
            ChatMemberStatus.MEMBER.value,
            ChatMemberStatus.ADMINISTRATOR.value,
            ChatMemberStatus.OWNER.value,
        }:
            return True
        if status_value == ChatMemberStatus.RESTRICTED.value:
            return bool(getattr(member, "is_member", False))
        return False
    except UserNotParticipant:
        return False
    except Exception as exc:
        print(
            f"Private membership check failed for user={user_id}, chat={chat_id}: "
            f"{type(exc).__name__}: {exc}"
        )
        return False


@X.on_message(filters.command(["batch", "single"]), group=-1)
async def access_command_guard(client, message):
    uid = message.from_user.id

    if await is_premium_user(uid):
        return

    if FREEMIUM_LIMIT <= 0:
        await message.reply_text(
            "🔒 Free downloads are disabled. Please upgrade to Premium to use this feature.\n\n💎 DM @freebandslime to gain Premium features."
        )
        message.stop_propagation()
        return

    if not await _has_free_slot(uid):
        await message.reply_text(
            f"⚠️ You have reached your free daily limit ({FREEMIUM_LIMIT}).\n\n💎 DM @freebandslime to gain Premium features."
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

    if state.get("step") == "count":
        try:
            count = int((message.text or "").strip())
        except (TypeError, ValueError):
            return

        if count < 1 or count > 100:
            return

        if not await is_premium_user(uid):
            remaining = max(0, FREEMIUM_LIMIT - await _get_usage(uid))
            if count > remaining:
                await message.reply_text(
                    f"⚠️ You have {remaining} free download(s) remaining today.\n"
                    f"Your batch requested {count}.\n\n"
                    f"💎 DM @freebandslime to gain Premium features."
                )
                message.stop_propagation()
        return

    if state.get("step") not in {"start", "start_single"}:
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
            "🔒 You must be logged in with /login and be a member of that private group/channel to download its posts."
        )
        message.stop_propagation()


def apply_patches():
    global _ORIGINAL_GET_UCLIENT, _ORIGINAL_PROCESS_MSG
    if _ORIGINAL_GET_UCLIENT is not None:
        return

    _ORIGINAL_GET_UCLIENT = batch_plugin.get_uclient
    _ORIGINAL_PROCESS_MSG = batch_plugin.process_msg
    batch_plugin.get_uclient = _gated_get_uclient
    batch_plugin.process_msg = _gated_process_msg


apply_patches()
print(f"Chalice access control enabled: FREEMIUM_LIMIT={FREEMIUM_LIMIT}")
