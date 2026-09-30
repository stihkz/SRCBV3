# Copyright (c) 2025 devgagan : https://github.com/devgaganin.  
# Licensed under the GNU General Public License v3.0.  
# See LICENSE file in the repository root for full license text.

import asyncio
import importlib
import os
import sys
from shared_client import start_client


async def _compat_get_uclient(uid):
    """Return a logged-in user client when available, otherwise a usable bot client."""
    from pyrogram import Client
    from config import API_ID, API_HASH
    from utils.func import get_user_data
    from utils.encrypt import dcs

    batch = sys.modules.get("plugins.batch")
    if batch is None:
        return None

    UC = getattr(batch, "UC", {})
    UB = getattr(batch, "UB", {})
    Y = getattr(batch, "Y", None)
    upd_dlg = getattr(batch, "upd_dlg", None)

    cached = UC.get(uid)
    if cached:
        return cached

    user_data = await get_user_data(uid)
    if user_data:
        encrypted = user_data.get("session_string")
        if encrypted:
            try:
                session_string = dcs(encrypted)
                client = Client(
                    f"{uid}_client",
                    api_id=API_ID,
                    api_hash=API_HASH,
                    device_model="v3saver",
                    session_string=session_string,
                )
                await client.start()
                if upd_dlg:
                    await upd_dlg(client)
                UC[uid] = client
                return client
            except Exception as e:
                print(f"User client error for {uid}: {e}")

    return UB.get(uid) or Y or getattr(batch, "X", None)


class _ChaliceProgressClient:
    def __init__(self, client):
        self._client = client

    async def edit_message_text(self, chat_id, message_id, text, *args, **kwargs):
        text = text.replace("Powered by Team SPY", "Powered by Chalice")
        return await self._client.edit_message_text(chat_id, message_id, text, *args, **kwargs)


def install_batch_compat():
    try:
        batch = importlib.import_module("plugins.batch")
        if not hasattr(batch, "get_uclient"):
            batch.get_uclient = _compat_get_uclient
            print("Installed batch.get_uclient compatibility handler.")

        original_prog = getattr(batch, "prog", None)
        if original_prog and not getattr(batch, "_chalice_prog_patched", False):
            async def chalice_prog(c, t, C, h, m, st):
                return await original_prog(c, t, _ChaliceProgressClient(C), h, m, st)
            batch.prog = chalice_prog
            batch._chalice_prog_patched = True
            print("Installed Chalice progress branding handler.")
    except Exception as e:
        print(f"Could not initialize batch compatibility: {e}")


async def load_and_run_plugins():
    # Register every handler BEFORE connecting either Telegram client.  This
    # prevents the Telethon command handlers (/add, /rem, /status, /dl, /adl,
    # etc.) from being registered after the update loop has already started.
    plugin_dir = "plugins"
    plugins = [
        f[:-3]
        for f in os.listdir(plugin_dir)
        if f.endswith(".py") and f != "__init__.py"
    ]

    # batch compatibility must exist before access_control is imported.
    install_batch_compat()

    # Keep batch first, then the remaining plugins in a deterministic order.
    ordered = []
    if "batch" in plugins:
        ordered.append("batch")
    for plugin in sorted(plugins):
        if plugin != "batch":
            ordered.append(plugin)

    loaded = []
    for plugin in ordered:
        try:
            module = importlib.import_module(f"plugins.{plugin}")
            loaded.append((plugin, module))
            print(f"Loaded plugin module: {plugin}")
        except Exception as e:
            print(f"ERROR loading plugin {plugin}: {e}")
            raise

    # Now that all decorators have registered their handlers, connect the
    # Telethon and Pyrogram clients. No command handler is missed during startup.
    await start_client()

    for plugin, module in loaded:
        if plugin == "batch":
            if not hasattr(module, "get_uclient"):
                module.get_uclient = _compat_get_uclient
                print("Re-installed batch.get_uclient compatibility handler.")
            if not getattr(module, "_chalice_prog_patched", False):
                install_batch_compat()

        hook = getattr(module, f"run_{plugin}_plugin", None)
        if hook:
            print(f"Running {plugin} plugin...")
            await hook()


async def main():
    await load_and_run_plugins()
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    print("Starting clients ...")
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Shutting down...")
    except Exception as e:
        print(e)
        sys.exit(1)
    finally:
        try:
            loop.close()
        except Exception:
            pass
