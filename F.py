"""
Telegram File Storage Bot
=========================
ইউজার ফাইল পাঠাবে, বট Telegram সার্ভারে রেখে একটি unique কোড দেবে।
সেই কোড দিয়ে পরে ফাইল ফেরত পাওয়া যাবে।

Setup:
    pip install python-telegram-bot==20.7

Run:
    python telegram_file_bot.py
"""

import logging
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
BOT_TOKEN = "8385695620:AAEQ4_yq3kK5tEU2LHOEy2tiY99VRJdqW0o"   # @BotFather থেকে নিন

# ফাইল ইনডেক্স স্টোরেজ চ্যানেল/গ্রুপ ID (optional)
# যদি শুধু per-user রাখতে চান তাহলে এটা দরকার নেই
STORAGE_CHANNEL_ID = None  # যেমন: -1001234567890

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# IN-MEMORY STORE  (Telegram-এই সব থাকে, এটা শুধু session cache)
# প্রতিটি ইউজারের ফাইল তার নিজের চ্যাটে Telegram সার্ভারে থাকে।
# আমরা শুধু file_id ও metadata মনে রাখি।
# ─────────────────────────────────────────────
# Structure: { user_id: { "file_code": { meta }, ... } }
user_files: dict[int, dict[str, dict]] = {}

def _next_code(user_id: int) -> str:
    """ইউজারের জন্য পরবর্তী সিরিয়াল কোড তৈরি করে। যেমন F001, F002…"""
    existing = user_files.get(user_id, {})
    num = len(existing) + 1
    return f"F{num:03d}"

def _store(user_id: int, code: str, meta: dict):
    if user_id not in user_files:
        user_files[user_id] = {}
    user_files[user_id][code] = meta

def _get(user_id: int, code: str) -> dict | None:
    return user_files.get(user_id, {}).get(code.upper())

def _list(user_id: int) -> dict:
    return user_files.get(user_id, {})

# ─────────────────────────────────────────────
# HANDLERS
# ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """বটের পরিচয় ও ব্যবহার বিধি।"""
    text = (
        "👋 *স্বাগতম File Storage Bot-এ!*\n\n"
        "আমি আপনার ফাইল Telegram সার্ভারে সংরক্ষণ করি এবং একটি *কোড* দিই।\n"
        "পরে সেই কোড দিয়ে ফাইল ফেরত নিতে পারবেন।\n\n"
        "📌 *কমান্ড সমূহ:*\n"
        "• যেকোনো ফাইল/ছবি/ভিডিও পাঠান → সেভ হবে\n"
        "• `/get F001` → কোড দিয়ে ফাইল নিন\n"
        "• `/list` → আপনার সব ফাইলের তালিকা\n"
        "• `/delete F001` → ফাইল মুছুন (শুধু তালিকা থেকে)\n"
        "• `/help` → সাহায্য\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ইউজার যেকোনো ফাইল পাঠালে সংরক্ষণ করে কোড দেয়।"""
    msg = update.message
    user_id = msg.from_user.id
    code = _next_code(user_id)

    # ফাইল টাইপ ও file_id বের করি
    if msg.document:
        file_obj = msg.document
        file_id = file_obj.file_id
        file_name = file_obj.file_name or "document"
        file_size = file_obj.file_size or 0
        file_type = "📄 Document"
    elif msg.photo:
        file_obj = msg.photo[-1]  # সর্বোচ্চ মানের ছবি
        file_id = file_obj.file_id
        file_name = f"photo_{code}.jpg"
        file_size = file_obj.file_size or 0
        file_type = "🖼️ Photo"
    elif msg.video:
        file_obj = msg.video
        file_id = file_obj.file_id
        file_name = msg.video.file_name or f"video_{code}.mp4"
        file_size = file_obj.file_size or 0
        file_type = "🎬 Video"
    elif msg.audio:
        file_obj = msg.audio
        file_id = file_obj.file_id
        file_name = msg.audio.file_name or f"audio_{code}.mp3"
        file_size = file_obj.file_size or 0
        file_type = "🎵 Audio"
    elif msg.voice:
        file_obj = msg.voice
        file_id = file_obj.file_id
        file_name = f"voice_{code}.ogg"
        file_size = file_obj.file_size or 0
        file_type = "🎤 Voice"
    elif msg.video_note:
        file_obj = msg.video_note
        file_id = file_obj.file_id
        file_name = f"videonote_{code}.mp4"
        file_size = file_obj.file_size or 0
        file_type = "📹 Video Note"
    elif msg.sticker:
        file_obj = msg.sticker
        file_id = file_obj.file_id
        file_name = f"sticker_{code}.webp"
        file_size = file_obj.file_size or 0
        file_type = "🎭 Sticker"
    else:
        await msg.reply_text("❌ এই ধরনের ফাইল সাপোর্ট করে না।")
        return

    # মেটাডেটা সেভ করি
    meta = {
        "file_id": file_id,
        "file_name": file_name,
        "file_size": file_size,
        "file_type": file_type,
        "code": code,
        "chat_id": msg.chat_id,
        "message_id": msg.message_id,
    }
    _store(user_id, code, meta)

    # সাইজ ফরম্যাট
    size_str = _format_size(file_size)

    reply = (
        f"✅ *ফাইল সেভ হয়েছে!*\n\n"
        f"🏷️ কোড: `{code}`\n"
        f"{file_type}\n"
        f"📁 নাম: `{file_name}`\n"
        f"📦 সাইজ: {size_str}\n\n"
        f"💡 ফাইল পেতে লিখুন:\n`/get {code}`"
    )

    keyboard = [[InlineKeyboardButton(f"📥 ফাইল নিন ({code})", callback_data=f"get:{code}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await msg.reply_text(reply, parse_mode="Markdown", reply_markup=reply_markup)


async def get_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/get F001 — কোড দিয়ে ফাইল ফেরত দেয়।"""
    user_id = update.message.from_user.id

    if not context.args:
        await update.message.reply_text("❓ কোড দিন। যেমন: `/get F001`", parse_mode="Markdown")
        return

    code = context.args[0].upper()
    meta = _get(user_id, code)

    if not meta:
        await update.message.reply_text(
            f"❌ `{code}` কোডের কোনো ফাইল পাওয়া যায়নি।\n"
            f"আপনার সব ফাইল দেখতে: `/list`",
            parse_mode="Markdown",
        )
        return

    await _send_file(update.message, meta)


async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/list — ইউজারের সব ফাইল দেখায়।"""
    user_id = update.message.from_user.id
    files = _list(user_id)

    if not files:
        await update.message.reply_text(
            "📭 আপনার কোনো ফাইল নেই।\nযেকোনো ফাইল পাঠান সেভ করতে!"
        )
        return

    lines = ["📂 *আপনার সেভ করা ফাইলসমূহ:*\n"]
    for code, meta in files.items():
        size_str = _format_size(meta.get("file_size", 0))
        lines.append(
            f"{meta['file_type']} `{code}` — {meta['file_name']} ({size_str})"
        )

    lines.append(f"\n💡 মোট: {len(files)}টি ফাইল")
    lines.append("ফাইল নিতে: `/get <কোড>`")

    # ইনলাইন বাটন তৈরি
    keyboard = [
        [InlineKeyboardButton(f"📥 {code}", callback_data=f"get:{code}")]
        for code in list(files.keys())[:10]  # সর্বোচ্চ ১০টি বাটন
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


async def delete_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/delete F001 — তালিকা থেকে ফাইল মুছে দেয়।"""
    user_id = update.message.from_user.id

    if not context.args:
        await update.message.reply_text("❓ কোড দিন। যেমন: `/delete F001`", parse_mode="Markdown")
        return

    code = context.args[0].upper()

    if user_id not in user_files or code not in user_files[user_id]:
        await update.message.reply_text(f"❌ `{code}` পাওয়া যায়নি।", parse_mode="Markdown")
        return

    file_name = user_files[user_id][code]["file_name"]
    del user_files[user_id][code]

    await update.message.reply_text(
        f"🗑️ `{code}` ({file_name}) তালিকা থেকে মুছে দেওয়া হয়েছে।",
        parse_mode="Markdown",
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ইনলাইন বাটন প্রেস হলে ফাইল পাঠায়।"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data  # "get:F001"

    if data.startswith("get:"):
        code = data.split(":")[1]
        meta = _get(user_id, code)
        if meta:
            await _send_file(query.message, meta)
        else:
            await query.message.reply_text(f"❌ `{code}` পাওয়া যায়নি।", parse_mode="Markdown")


# ─────────────────────────────────────────────
# HELPER: ফাইল পাঠানো
# ─────────────────────────────────────────────

async def _send_file(message, meta: dict):
    """file_id দিয়ে Telegram সার্ভার থেকে ফাইল পাঠায়।"""
    file_id = meta["file_id"]
    file_type = meta["file_type"]
    code = meta["code"]

    caption = f"📥 *{code}* — {meta['file_name']}"

    try:
        if "Photo" in file_type:
            await message.reply_photo(photo=file_id, caption=caption, parse_mode="Markdown")
        elif "Video Note" in file_type:
            await message.reply_video_note(video_note=file_id)
        elif "Video" in file_type:
            await message.reply_video(video=file_id, caption=caption, parse_mode="Markdown")
        elif "Audio" in file_type:
            await message.reply_audio(audio=file_id, caption=caption, parse_mode="Markdown")
        elif "Voice" in file_type:
            await message.reply_voice(voice=file_id, caption=caption, parse_mode="Markdown")
        elif "Sticker" in file_type:
            await message.reply_sticker(sticker=file_id)
        else:
            await message.reply_document(document=file_id, caption=caption, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"ফাইল পাঠাতে সমস্যা: {e}")
        await message.reply_text(
            f"⚠️ ফাইল পাঠাতে সমস্যা হয়েছে।\nfile_id: `{file_id}`",
            parse_mode="Markdown",
        )


def _format_size(size_bytes: int) -> str:
    """বাইট থেকে পাঠযোগ্য সাইজ ফরম্যাট।"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.2f} GB"


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # কমান্ড হ্যান্ডলার
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("get", get_file))
    app.add_handler(CommandHandler("list", list_files))
    app.add_handler(CommandHandler("delete", delete_file))

    # ফাইল হ্যান্ডলার
    app.add_handler(MessageHandler(
        filters.Document.ALL
        | filters.PHOTO
        | filters.VIDEO
        | filters.AUDIO
        | filters.VOICE
        | filters.VIDEO_NOTE
        | filters.Sticker.ALL,
        receive_file,
    ))

    # বাটন কলব্যাক
    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info("✅ বট চালু হয়েছে...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
