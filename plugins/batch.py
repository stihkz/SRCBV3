# Copyright (c) 2025 devgagan : https://github.com/devgaganin.  
# Licensed under the GNU General Public License v3.0.  
# See LICENSE file in the repository root for full license text.

import os, re, time, asyncio, json
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import UserNotParticipant
from config import API_ID, API_HASH, LOG_GROUP, STRING, FORCE_SUB, FREEMIUM_LIMIT, PREMIUM_LIMIT
from utils.func import get_user_data, screenshot, thumbnail, get_video_metadata
from utils.func import get_user_data_key, process_text_with_rules, is_premium_user, E
from shared_client import app as X
from plugins.settings import rename_file
from plugins.start import subscribe as sub
from utils.custom_filters import login_in_progress
from utils.encrypt import dcs
from typing import Dict, Any, Optional

Y = None if not STRING else __import__('shared_client').userbot
Z, P, UB, UC, emp = {}, {}, {}, {}, {}

ACTIVE_USERS = {}
ACTIVE_USERS_FILE = "active_users.json"

def sanitize(filename):
    return re.sub(r'[<>:"/\\|?*\']', '_', filename).strip(" .")[:255]

def load_active_users():
    try:
        if os.path.exists(ACTIVE_USERS_FILE):
            with open(ACTIVE_USERS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception:
        return {}

async def save_active_users_to_file():
    try:
        with open(ACTIVE_USERS_FILE, 'w') as f:
            json.dump(ACTIVE_USERS, f)
    except Exception as e:
        print(f"Error saving active users: {e}")

async def add_active_batch(user_id: int, batch_info: Dict[str, Any]):
    ACTIVE_USERS[str(user_id)] = batch_info
    await save_active_users_to_file()

def is_user_active(user_id: int) -> bool:
    return str(user_id) in ACTIVE_USERS

async def update_batch_progress(user_id: int, current: int, success: int):
    if str(user_id) in ACTIVE_USERS:
        ACTIVE_USERS[str(user_id)]["current"] = current
        ACTIVE_USERS[str(user_id)]["success"] = success
        await save_active_users_to_file()

async def request_batch_cancel(user_id: int):
    if str(user_id) in ACTIVE_USERS:
        ACTIVE_USERS[str(user_id)]["cancel_requested"] = True
        await save_active_users_to_file()
        return True
    return False

def should_cancel(user_id: int) -> bool:
    user_str = str(user_id)
    return user_str in ACTIVE_USERS and ACTIVE_USERS[user_str].get("cancel_requested", False)

async def remove_active_batch(user_id: int):
    if str(user_id) in ACTIVE_USERS:
        del ACTIVE_USERS[str(user_id)]
        await save_active_users_to_file()

def get_batch_info(user_id: int) -> Optional[Dict[str, Any]]:
    return ACTIVE_USERS.get(str(user_id))

ACTIVE_USERS = load_active_users()

async def upd_dlg(c):
    try:
        async for _ in c.get_dialogs(limit=200):
            pass
        return True
    except Exception as e:
        print(f'Failed to update dialogs: {e}')
        return False

async def _resolve_private_chat(u, i):
    """Resolve a /c/ chat through the authorized user session.

    Pyrogram can know that the account is a member of a channel while still
    lacking a usable input peer in its local cache.  Always resolve the peer
    with the user client before requesting the message.
    """
    raw = str(i).strip()
    candidates = []
    if raw.startswith('-100'):
        candidates.append(int(raw))
        base = raw[4:]
        if base.isdigit():
            candidates.append(int(f'-{base}'))
    elif raw.lstrip('-').isdigit():
        base = raw.lstrip('-')
        candidates.extend([int(f'-100{base}'), int(f'-{base}')])
    else:
        candidates.append(raw)

    last_error = None
    for candidate in candidates:
        try:
            chat = await u.get_chat(candidate)
            return chat
        except Exception as e:
            last_error = e

    # Refresh the dialog/peer cache and retry once. This is important after a
    # newly generated session string is used on a fresh Heroku worker.
    await upd_dlg(u)
    for candidate in candidates:
        try:
            chat = await u.get_chat(candidate)
            return chat
        except Exception as e:
            last_error = e

    raise last_error or ValueError(f"Could not resolve source chat {i}")

# Fetch a batch message reliably using the authorized user session for private
# chats. The message is re-fetched from that same session after peer resolution
# so download_media() never receives a stale/bot-side Message object.
async def get_msg(c, u, i, d, lt):
    try:
        if lt == 'public':
            chat = str(i).lstrip('@')
            emp[chat] = True
            try:
                xm = await c.get_messages(chat, d)
                if xm and not getattr(xm, "empty", False):
                    emp[chat] = False
                    print(f"Public message fetched by bot: @{chat}/{d}")
                    return xm
            except Exception as e:
                print(f"Bot could not fetch public message @{chat}/{d}: {e}")

            if u:
                try:
                    chat_obj = await u.get_chat(chat)
                    xm = await u.get_messages(chat_obj.id, d)
                    if xm and not getattr(xm, "empty", False):
                        emp[chat] = True
                        print(f"Public message fetched by user client: @{chat}/{d}")
                        return xm
                except Exception as e:
                    print(f"User client could not fetch public message @{chat}/{d}: {e}")
            return None

        if not u:
            print(f"No authorized user client available for private chat {i}")
            return None

        try:
            chat_obj = await _resolve_private_chat(u, i)
            xm = await u.get_messages(chat_obj.id, int(d))
            if xm and not getattr(xm, "empty", False):
                print(f"Private message resolved and fetched: chat={chat_obj.id}, message={d}")
                return xm
            print(f"Private message {d} was empty in chat {chat_obj.id}")
            return None
        except Exception as e:
            print(f"Private peer/message resolution failed for {i}/{d}: {e}")
            return None
    except Exception as e:
        print(f'Error fetching message: {e}')
        return None

async def get_ubot(uid):
    bt = await get_user_data_key(uid, "bot_token", None)
    if not bt: return None
    if uid in UB: return UB.get(uid)
    try:
        bot = Client(f"user_{uid}", bot_token=bt, api_id=API_ID, api_hash=API_HASH)
        await bot.start()
        UB[uid] = bot
        return bot
    except Exception as e:
        print(f"Error starting bot for user {uid}: {e}")
        return None

async def get_uclient(uid):
    ud = await get_user_data(uid)
    ubot = UB.get(uid)
    cl = UC.get(uid)
    if cl: return cl
    if not ud: return ubot if ubot else None
    xxx = ud.get('session_string')
    if xxx:
        try:
            ss = dcs(xxx)
            gg = Client(f'{uid}_client', api_id=API_ID, api_hash=API_HASH, device_model="v3saver", session_string=ss)
            await gg.start()
            await upd_dlg(gg)
            UC[uid] = gg
            return gg
        except Exception as e:
            print(f'User client error: {e}')
            return ubot if ubot else Y
    return Y

async def prog(c, t, C, h, m, st):
    global P
    p = c / t * 100
    interval = 10 if t >= 100 * 1024 * 1024 else 20 if t >= 50 * 1024 * 1024 else 30 if t >= 10 * 1024 * 1024 else 50
    step = int(p // interval) * interval
    if m not in P or P[m] != step or p >= 100:
        P[m] = step
        c_mb = c / (1024 * 1024)
        t_mb = t / (1024 * 1024)
        bar = '🟢' * int(p / 10) + '🔴' * (10 - int(p / 10))
        speed = c / (time.time() - st) / (1024 * 1024) if time.time() > st else 0
        eta = time.strftime('%M:%S', time.gmtime((t - c) / (speed * 1024 * 1024))) if speed > 0 else '00:00'
        await C.edit_message_text(h, m, f"__**Pyro Handler...**__\n\n{bar}\n\n⚡**__Completed__**: {c_mb:.2f} MB / {t_mb:.2f} MB\n📊 **__Done__**: {p:.2f}%\n🚀 **__Speed__**: {speed:.2f} MB/s\n⏳ **__ETA__**: {eta}\n\n**__Powered by Team SPY__**")
        if p >= 100: P.pop(m, None)

async def send_direct(c, m, tcid, ft=None, rtmid=None):
    try:
        if m.video:
            await c.send_video(tcid, m.video.file_id, caption=ft, duration=m.video.duration, width=m.video.width, height=m.video.height, reply_to_message_id=rtmid)
        elif m.video_note:
            await c.send_video_note(tcid, m.video_note.file_id, reply_to_message_id=rtmid)
        elif m.voice:
            await c.send_voice(tcid, m.voice.file_id, reply_to_message_id=rtmid)
        elif m.sticker:
            await c.send_sticker(tcid, m.sticker.file_id, reply_to_message_id=rtmid)
        elif m.audio:
            await c.send_audio(tcid, m.audio.file_id, caption=ft, duration=m.audio.duration, performer=m.audio.performer, title=m.audio.title, reply_to_message_id=rtmid)
        elif m.photo:
            photo_id = m.photo.file_id if hasattr(m.photo, 'file_id') else m.photo[-1].file_id
            await c.send_photo(tcid, photo_id, caption=ft, reply_to_message_id=rtmid)
        elif m.document:
            await c.send_document(tcid, m.document.file_id, caption=ft, file_name=m.document.file_name, reply_to_message_id=rtmid)
        else:
            return False
        return True
    except Exception as e:
        print(f'Direct send error: {e}')
        return False

async def process_msg(c, u, m, d, lt, uid, i):
    try:
        cfg_chat = await get_user_data_key(d, 'chat_id', None)
        tcid = d
        rtmid = None
        if cfg_chat:
            if '/' in cfg_chat:
                parts = cfg_chat.split('/', 1)
                tcid = int(parts[0])
                rtmid = int(parts[1]) if len(parts) > 1 else None
            else:
                tcid = int(cfg_chat)

        # For private links, force the message to come from the authorized
        # user client immediately before downloading. This prevents
        # PEER_ID_INVALID when a cached/stale Message object is used.
        if lt == 'private' and u:
            try:
                chat_obj = await _resolve_private_chat(u, i)
                fresh = await u.get_messages(chat_obj.id, int(d))
                if fresh and not getattr(fresh, 'empty', False):
                    m = fresh
                    i = chat_obj.id
                    print(f"Using fresh user-session message for download: chat={i}, message={d}")
            except Exception as e:
                print(f"Fresh private message resolution before download failed: {e}")

        if m.media:
            orig_text = m.caption.markdown if m.caption else ''
            proc_text = await process_text_with_rules(d, orig_text)
            user_cap = await get_user_data_key(d, 'caption', '')
            ft = f'{proc_text}\n\n{user_cap}' if proc_text and user_cap else user_cap if user_cap else proc_text

            if lt == 'public' and not emp.get(str(i).lstrip('@'), True):
                sent = await send_direct(c, m, tcid, ft, rtmid)
                return 'Sent directly.' if sent else 'Failed.'

            st = time.time()
            p = await c.send_message(d, 'Downloading...')
            c_name = f"{time.time()}"
            if m.video:
                file_name = m.video.file_name
                if not file_name:
                    file_name = f"{time.time()}.mp4"
                    c_name = sanitize(file_name)
            elif m.audio:
                file_name = m.audio.file_name
                if not file_name:
                    file_name = f"{time.time()}.mp3"
                    c_name = sanitize(file_name)
            elif m.document:
                file_name = m.document.file_name
                if not file_name:
                    file_name = f"{time.time()}"
                else:
                    c_name = sanitize(file_name)
            elif m.photo:
                file_name = f"{time.time()}.jpg"
                c_name = sanitize(file_name)

            # Always download through the authorized user client. If it still
            # cannot resolve the peer, surface the actual error in the batch log.
            try:
                f = await u.download_media(m, file_name=c_name, progress=prog, progress_args=(c, d, p.id, st))
            except Exception as e:
                print(f"User-session download failed for chat={i}, message={d}: {type(e).__name__}: {e}")
                await c.edit_message_text(d, p.id, f'Download failed: {str(e)[:80]}')
                return f'Error: {str(e)[:80]}'

            if not f:
                await c.edit_message_text(d, p.id, 'Failed.')
                return 'Failed.'

            await c.edit_message_text(d, p.id, 'Renaming...')
            if ((m.video and m.video.file_name) or (m.audio and m.audio.file_name) or (m.document and m.document.file_name)):
                f = await rename_file(f, d, p)

            fsize = os.path.getsize(f) / (1024 * 1024 * 1024)
            th = thumbnail(d)

            if fsize > 2 and Y:
                st = time.time()
                await c.edit_message_text(d, p.id, 'File is larger than 2GB. Using alternative method...')
                await upd_dlg(Y)
                mtd = await get_video_metadata(f)
                dur, h, w = mtd['duration'], mtd['width'], mtd['height']
                th = await screenshot(f, dur, d)
                send_funcs = {'video': Y.send_video, 'video_note': Y.send_video_note, 'voice': Y.send_voice, 'audio': Y.send_audio, 'photo': Y.send_photo, 'document': Y.send_document}
                for mtype, func in send_funcs.items():
                    if f.endswith('.mp4'): mtype = 'video'
                    if getattr(m, mtype, None):
                        sent = await func(LOG_GROUP, f, thumb=th if mtype == 'video' else None, duration=dur if mtype == 'video' else None, height=h if mtype == 'video' else None, width=w if mtype == 'video' else None, caption=ft if m.caption and mtype not in ['video_note', 'voice'] else None, reply_to_message_id=rtmid, progress=prog, progress_args=(c, d, p.id, st))
                        break
                else:
                    sent = await Y.send_document(LOG_GROUP, f, thumb=th, caption=ft if m.caption else None, reply_to_message_id=rtmid, progress=prog, progress_args=(c, d, p.id, st))
                await c.copy_message(d, LOG_GROUP, sent.id)
                os.remove(f)
                await c.delete_messages(d, p.id)
                return 'Done (Large file).'

            await c.edit_message_text(d, p.id, 'Uploading...')
            st = time.time()
            try:
                video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.ogv']
                audio_extensions = ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.opus', '.aiff', '.ac3']
                file_ext = os.path.splitext(f)[1].lower()
                if m.video or (m.document and file_ext in video_extensions):
                    mtd = await get_video_metadata(f)
                    dur, h, w = mtd['duration'], mtd['height'], mtd['width']
                    th = await screenshot(f, dur, d)
                    await c.send_video(tcid, video=f, caption=ft if m.caption else None, thumb=th, width=w, height=h, duration=dur, progress=prog, progress_args=(c, d, p.id, st), reply_to_message_id=rtmid)
                elif m.video_note:
                    await c.send_video_note(tcid, video_note=f, progress=prog, progress_args=(c, d, p.id, st), reply_to_message_id=rtmid)
                elif m.voice:
                    await c.send_voice(tcid, f, progress=prog, progress_args=(c, d, p.id, st), reply_to_message_id=rtmid)
                elif m.sticker:
                    await c.send_sticker(tcid, m.sticker.file_id, reply_to_message_id=rtmid)
                elif m.audio or (m.document and file_ext in audio_extensions):
                    await c.send_audio(tcid, audio=f, caption=ft if m.caption else None, thumb=th, progress=prog, progress_args=(c, d, p.id, st), reply_to_message_id=rtmid)
                elif m.photo:
                    await c.send_photo(tcid, photo=f, caption=ft if m.caption else None, progress=prog, progress_args=(c, d, p.id, st), reply_to_message_id=rtmid)
                elif m.document:
                    await c.send_document(tcid, document=f, caption=ft if m.caption else None, progress=prog, progress_args=(c, d, p.id, st), reply_to_message_id=rtmid)
                else:
                    await c.send_document(tcid, document=f, caption=ft if m.caption else None, progress=prog, progress_args=(c, d, p.id, st), reply_to_message_id=rtmid)
            except Exception as e:
                await c.edit_message_text(d, p.id, f'Upload failed: {str(e)[:30]}')
                if os.path.exists(f): os.remove(f)
                return 'Failed.'
            os.remove(f)
            await c.delete_messages(d, p.id)
            return 'Done.'
        elif m.text:
            await c.send_message(tcid, text=m.text.markdown, reply_to_message_id=rtmid)
            return 'Sent.'
    except Exception as e:
        return f'Error: {str(e)[:80]}'

@X.on_message(filters.command(['batch', 'single']))
async def process_cmd(c, m):
    uid = m.from_user.id
    cmd = m.command[0]
    if FREEMIUM_LIMIT == 0 and not await is_premium_user(uid):
        await m.reply_text("This bot does not provide free servies, get subscription from OWNER")
        return
    if await sub(c, m) == 1: return
    pro = await m.reply_text('Doing some checks hold on...')
    if is_user_active(uid):
        await pro.edit('You have an active task. Use /stop to cancel it.')
        return
    ubot = await get_ubot(uid)
    if not ubot:
        await pro.edit('Add your bot with /setbot first')
        return
    Z[uid] = {'step': 'start' if cmd == 'batch' else 'start_single'}
    await pro.edit(f'Send {"start link..." if cmd == "batch" else "link you to process"}.')

@X.on_message(filters.command(['cancel', 'stop']))
async def cancel_cmd(c, m):
    uid = m.from_user.id
    if is_user_active(uid):
        if await request_batch_cancel(uid):
            await m.reply_text('Cancellation requested. The current batch will stop after the current download completes.')
        else:
            await m.reply_text('Failed to request cancellation. Please try again.')
    else:
        await m.reply_text('No active batch process found.')

@X.on_message(filters.text & filters.private & ~login_in_progress & ~filters.command(['start', 'batch', 'cancel', 'login', 'logout', 'stop', 'set', 'pay', 'redeem', 'gencode', 'single', 'generate', 'keyinfo', 'encrypt', 'decrypt', 'keys', 'setbot', 'rembot']))
async def text_handler(c, m):
    uid = m.from_user.id
    if uid not in Z: return
    s = Z[uid].get('step')
    x = await get_ubot(uid)
    if not x:
        await m.reply("Add your bot /setbot `token`")
        return
    if s == 'start':
        L = m.text
        i, d, lt = E(L)
        if not i or not d:
            await m.reply_text('Invalid link format.')
            Z.pop(uid, None)
            return
        Z[uid].update({'step': 'count', 'cid': i, 'sid': d, 'lt': lt})
        await m.reply_text('How many messages?')
    elif s == 'start_single':
        L = m.text
        i, d, lt = E(L)
        if not i or not d:
            await m.reply_text('Invalid link format.')
            Z.pop(uid, None)
            return
        Z[uid].update({'step': 'process_single', 'cid': i, 'sid': d, 'lt': lt})
        i, s, lt = Z[uid]['cid'], Z[uid]['sid'], Z[uid]['lt']
        pt = await m.reply_text('Processing...')
        ubot = UB.get(uid)
        if not ubot:
            await pt.edit('Add bot with /setbot first')
            Z.pop(uid, None)
            return
        uclient = await get_uclient(uid)
        msg = await get_msg(c, uclient, i, s, lt)
        if not msg:
            await pt.edit('Failed to fetch that message. Make sure your user session can access the source chat.')
            Z.pop(uid, None)
            return
        result = await process_msg(c, uclient, msg, uid, lt, uid, i)
        await pt.edit(result)
        Z.pop(uid, None)
    elif s == 'count':
        try:
            count = int(m.text)
        except ValueError:
            await m.reply_text('Please enter a valid number.')
            return
        if count < 1 or count > 100:
            await m.reply_text('Batch size must be between 1 and 100.')
            return
        Z[uid]['count'] = count
        Z[uid]['step'] = 'process_batch'
        await m.reply_text('Starting batch...')
        i, s, lt = Z[uid]['cid'], Z[uid]['sid'], Z[uid]['lt']
        uclient = await get_uclient(uid)
        if not uclient:
            await m.reply_text('No authorized user session found. Use /login first.')
            Z.pop(uid, None)
            return
        success = 0
        for idx in range(s, s + count):
            if should_cancel(uid):
                break
            msg = await get_msg(c, uclient, i, idx, lt)
            if not msg:
                print(f"Batch item {idx - s + 1}/{count}: message={idx}, result=Failed to fetch message")
                continue
            result = await process_msg(c, uclient, msg, uid, lt, uid, i)
            print(f"Batch item {idx - s + 1}/{count}: message={idx}, result={result}")
            if result.startswith('Done') or result.startswith('Sent'):
                success += 1
        await m.reply_text(f'Batch Completed ✅ Success: {success}/{count}')
        await remove_active_batch(uid)
        Z.pop(uid, None)

