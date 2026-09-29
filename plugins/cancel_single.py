# Copyright (c) 2025 devgagan
# Licensed under the GNU General Public License v3.0.

import asyncio
from pyrogram import filters, StopPropagation
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

    # /single waiting for a link, or currently processing one.
    if uid in batch.Z and batch.Z[uid].get("step") in ("start_single", "process_single"):
        batch.Z.pop(uid, None)

        # The single handler awaits process_msg(), so cancelling that task
        # interrupts the active download as well.
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

    # No single task: let the existing /cancel /stop batch handler run.
    return
