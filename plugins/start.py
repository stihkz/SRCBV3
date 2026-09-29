# Copyright (c) 2025 devgagan : https://github.com/devgaganin.  
# Licensed under the GNU General Public License v3.0.  
# See LICENSE file in the repository root for full license text.

from shared_client import app
from pyrogram import filters
from pyrogram.errors import UserNotParticipant
from pyrogram.types import BotCommand, BotCommandScopeDefault, InlineKeyboardButton, InlineKeyboardMarkup
from config import LOG_GROUP, OWNER_ID, FORCE_SUB

WELCOME_TEXT = """👋 **Welcome to BandzVault!**

📥 Save posts from channels/groups with forwarding disabled, or download videos & audio from YouTube, Instagram, and more.

🔗 Send a public post link to get started. For private channels, use `/login`.

💡 Use `/help` to see all commands."""
WELCOME_IMAGE = "https://drive.google.com/uc?export=download&id=1nPt6Nn-G2F1tnLfsIEhIqihcjVEyXzu_"

async def subscribe(app, message):
    if not FORCE_SUB or not message.from_user:
        return 0
    try:
        member = await app.get_chat_member(FORCE_SUB, message.from_user.id)
        status = str(member.status).lower()
        if "left" in status or "banned" in status or "kicked" in status:
            raise UserNotParticipant
        return 0
    except UserNotParticipant:
        try:
            link = await app.export_chat_invite_link(FORCE_SUB)
        except Exception:
            link = None
        buttons = InlineKeyboardMarkup([])
        if link:
            buttons = InlineKeyboardMarkup([[InlineKeyboardButton("Join Now...", url=link)]])
        await message.reply_photo(photo="https://graph.org/file/d44f024a08ded19452152.jpg", caption="Join our channel to use the bot", reply_markup=buttons)
        return 1
    except Exception as ggn:
        await message.reply_text(f"Something Went Wrong. Contact admins... with following message {ggn}")
        return 1

@app.on_message(filters.command("start"))
async def start(client, message):
    join = await subscribe(client, message)
    if join == 1: return
    try:
        await message.reply_photo(photo=WELCOME_IMAGE, caption=WELCOME_TEXT)
    except Exception as e:
        print(f"Start image failed: {e}")
        await message.reply_text(WELCOME_TEXT)

@app.on_message(filters.command("set"))
async def set(_, message):
    if message.from_user.id not in OWNER_ID:
        await message.reply("You are not authorized to use this command.")
        return
    commands = [
        BotCommand("start", "🚀 Start the bot"), BotCommand("single", "📥 Download a single post"),
        BotCommand("batch", "🫠 Extract in bulk"), BotCommand("login", "🔑 Get into the bot"),
        BotCommand("logout", "🚪 Get out of the bot"), BotCommand("adl", "👻 Download audio from 30+ sites"),
        BotCommand("dl", "💀 Download videos from 30+ sites"), BotCommand("status", "⟳ Refresh Payment status"),
        BotCommand("transfer", "💘 Gift premium to others"), BotCommand("add", "➕ Add user to premium"),
        BotCommand("rem", "➖ Remove from premium"), BotCommand("rembot", "🤨 Remove your custom bot"),
        BotCommand("settings", "⚙️ Personalize things"), BotCommand("plan", "🗓️ Check our premium plans"),
        BotCommand("terms", "🥺 Terms and conditions"), BotCommand("help", "❓ If you're a noob, still!"),
        BotCommand("cancel", "🚫 Cancel login/batch/settings process"), BotCommand("stop", "🚫 Cancel batch process")
    ]
    try:
        await app.delete_bot_commands(scope=BotCommandScopeDefault())
    except Exception as e:
        print(f"Could not clear existing default commands: {e}")
    await app.set_bot_commands(commands, scope=BotCommandScopeDefault())
    await message.reply("✅ Commands configured successfully!")

help_pages = [
    ("📝 **Bot Commands Overview (1/2):**\n\n1. **/add userID**\n> Add user to premium (Owner only)\n\n2. **/rem userID**\n> Remove user from premium (Owner only)\n\n3. **/transfer userID**\n> Transfer premium to your beloved major purpose for resellers (Premium members only)\n\n4. **/get**\n> Get all user IDs (Owner only)\n\n5. **/lock**\n> Lock channel from extraction (Owner only)\n\n6. **/single link**\n> Download a single post\n\n7. **/dl link**\n> Download videos (Not available in v1 if you are using)\n\n8. **/adl link**\n> Download audio (Not available in v1 if you are using)\n\n9. **/login**\n> Log into the bot for private channel access\n\n10. **/batch**\n> Bulk extraction for posts (After login)\n\n"),
    ("📝 **Bot Commands Overview (2/2):**\n\n11. **/logout**\n> Logout from the bot\n\n12. **/stats**\n> Get bot stats\n\n13. **/plan**\n> Check premium plans\n\n14. **/speedtest**\n> Test the server speed (not available in v1)\n\n15. **/terms**\n> Terms and conditions\n\n16. **/cancel**\n> Cancel ongoing batch process\n\n17. **/myplan**\n> Get details about your plans\n\n18. **/session**\n> Generate Pyrogram V2 session\n\n19. **/settings**\n> 1. SETCHATID : To directly upload in channel or group or user's dm use it with -100[chatID]\n> 2. SETRENAME : To add custom rename tag or username of your channels\n> 3. CAPTION : To add custom caption\n> 4. REPLACEWORDS : Can be used for words in deleted set via REMOVE WORDS\n> 5. RESET : To set the things back to default\n\n> You can set CUSTOM THUMBNAIL, PDF WATERMARK, VIDEO WATERMARK, etc. from settings\n\n**__Powered by Chalice__**")
]

async def send_or_edit_help_page(_, message, page_number):
    if page_number < 0 or page_number >= len(help_pages): return
    buttons = []
    if page_number > 0: buttons.append(InlineKeyboardButton("◀️ Previous", callback_data=f"help_prev_{page_number}"))
    if page_number < len(help_pages) - 1: buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"help_next_{page_number}"))
    await message.delete()
    await message.reply(help_pages[page_number], reply_markup=InlineKeyboardMarkup([buttons]))

@app.on_message(filters.command("help"))
async def help(client, message):
    join = await subscribe(client, message)
    if join == 1: return
    await send_or_edit_help_page(client, message, 0)

@app.on_callback_query(filters.regex(r"help_(prev|next)_(\d+)"))
async def on_help_navigation(client, callback_query):
    action, page_number = callback_query.data.split("_")[1], int(callback_query.data.split("_")[2])
    page_number += 1 if action == "next" else -1
    await send_or_edit_help_page(client, callback_query.message, page_number)
    await callback_query.answer()

TERMS_TEXT = ("• We are not responsible for how users choose to use BandzVault. We do not promote or encourage copyright infringement or other unlawful activity. Users are solely responsible for their actions.\n\n" "• Purchases do not guarantee service uptime, availability, or plan validity. We reserve the right to authorize, restrict, or ban users at any time at our discretion.\n\n" "• Payment does **not guarantee** access to the `/batch` command. Authorization is granted at our sole discretion and may be changed or revoked at any time.")
CONTACT_URL = "https://t.me/freebandslime"

@app.on_message(filters.command("terms") & filters.private)
async def terms(client, message):
    buttons = InlineKeyboardMarkup([[InlineKeyboardButton("📋 See Plans", callback_data="see_plan")],[InlineKeyboardButton("💬 Contact Now", url=CONTACT_URL)]])
    await message.reply_text(TERMS_TEXT, reply_markup=buttons)

@app.on_message(filters.command("plan") & filters.private)
async def plan(client, message):
    # Keep /plan consistent with the current See Plans content.
    await send_plan_message(message)

async def send_plan_message(message):
    plan_text = "• Week — **$8**\n• Month — **$25**\n• Lifetime — **$40** *(Terms & Conditions apply)*\n\n📥 **Download Limit**\nDownload up to **100,000 files** in a single batch command.\n\n🛑 **/batch Mode**\nGet access to an extra `/batch` mode with support for files up to **4GB**.\n\n⏳ Please wait for the process to automatically cancel or finish before starting another download or upload.\n\n📜 **Terms & Conditions**\nSend `/terms` or click **See Terms 👇** for the full details."
    buttons = InlineKeyboardMarkup([[InlineKeyboardButton("📜 See Terms", callback_data="see_terms")],[InlineKeyboardButton("💬 Contact Now", url=CONTACT_URL)]])
    await message.reply_text(plan_text, reply_markup=buttons)

@app.on_callback_query(filters.regex("see_plan"))
async def see_plan(client, callback_query):
    await callback_query.message.edit_text(
        "• Week — **$8**\n• Month — **$25**\n• Lifetime — **$40** *(Terms & Conditions apply)*\n\n📥 **Download Limit**\nDownload up to **100,000 files** in a single batch command.\n\n🛑 **/batch Mode**\nGet access to an extra `/batch` mode with support for files up to **4GB**.\n\n⏳ Please wait for the process to automatically cancel or finish before starting another download or upload.\n\n📜 **Terms & Conditions**\nSend `/terms` or click **See Terms 👇** for the full details.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📜 See Terms", callback_data="see_terms")],[InlineKeyboardButton("💬 Contact Now", url=CONTACT_URL)])
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex("see_terms"))
async def see_terms(client, callback_query):
    await callback_query.message.edit_text(
        TERMS_TEXT,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 See Plans", callback_data="see_plan")],[InlineKeyboardButton("💬 Contact Now", url=CONTACT_URL)])
    )
    await callback_query.answer()
