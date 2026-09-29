# Copyright (c) 2025 devgagan
# Licensed under the GNU General Public License v3.0.

import asyncio
from pyrogram import filters
from pyrogram.handlers import MessageHandler
from pyrogram.errors import MessageIdInvalid
from pyrogram import StopPropagation
from shared_client import app as X


def _get_batch_module():
    import plugins.batch as batch
    return batch


def _task_belongs_to_user(task, uid):
    """Find the current batch.py text-handler task for this user."""
    try:
        coro = task.get_coro()
        if getattr(getattr(coro, "cr_code", None), "co_name", "") != "text_handler":
            return False
        frame = getattr(coro, "cr_frame", None)
        if not frame:
            return False
        msg = frame.f_locals.get("m")
        return bool(msg and msg.from_user and msg.from_user.id == uid)
    except Exception:
        return False


@X.on_message(filters.command(["cancel", "stop"]), group=-1)
async def cancel_single_or_waiting(c, m):
    uid = m.from_user.id
    batch = _get_batch_module()

    # If /single is waiting for the link, cancel its conversation state.
    if uid in batch.Z and batch.Z[uid].get("step") in ("start_single", "process_single"):
        batch.Z.pop(uid, None)

        # If the single download is already running, cancel the handler task
        # that is awaiting process_msg(). This also interrupts download_media().
        cancelled = False
        for task in asyncio.all_tasks():
            if task is asyncio.current_task() or task.done():
                continue
            if _task_belongs_to_user(task, uid):
                task.cancel()
                cancelled = True
                break

        await m.reply_text("🛑 Single download cancelled." if cancelled else "🛑 Single process cancelled.")
        raise StopPropagation

    # Let the existing batch cancellation handler handle real batch jobs.
    raise StopPropagation
