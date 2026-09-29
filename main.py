# Copyright (c) 2025 devgagan : https://github.com/devgaganin.  
# Licensed under the GNU General Public License v3.0.  
# See LICENSE file in the repository root for full license text.

import asyncio
from shared_client import start_client
import importlib
import os
import sys

async def _compat_get_uclient(uid):
    """Compatibility helper for batch.py after /setbot was removed.

    Prefer the user's logged-in session. If none exists, fall back to the
    main/custom bot client so public downloads continue to work.
    """
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
    ubot = UB.get(uid)

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

    # No per-user login: use the existing bot client for public content.
    return ubot or Y or getattr(batch, "X", None)

async def load_and_run_plugins():
    await start_client()
    plugin_dir = "plugins"
    plugins = [f[:-3] for f in os.listdir(plugin_dir) if f.endswith(".py") and f != "__init__.py"]

    for plugin in plugins:
        module = importlib.import_module(f"plugins.{plugin}")

        # Older/custom batch.py versions call get_uclient(), while the current
        # fork no longer defines it after removing the per-user /setbot flow.
        # Install the compatibility function after batch.py has loaded so no
        # command handler is changed or lost.
        if plugin == "batch" and not hasattr(module, "get_uclient"):
            module.get_uclient = _compat_get_uclient
            print("Installed batch.get_uclient compatibility handler.")

        if hasattr(module, f"run_{plugin}_plugin"):
            print(f"Running {plugin} plugin...")
            await getattr(module, f"run_{plugin}_plugin")()

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
