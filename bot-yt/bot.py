"""Bot Telegram: unduh MP3/MP4 dari link YouTube atau Facebook, user pilih format & resolusi."""

import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from downloader import DownloadError, TooLargeError, download_media, extract_supported_url

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)  # hanya error, bukan tiap request
logger = logging.getLogger(__name__)

# Batas download bersamaan agar server tidak kewalahan.
MAX_CONCURRENT = 3
_semaphore = asyncio.Semaphore(MAX_CONCURRENT)

START_TIME = time.time()
STATS_FILE = Path(__file__).parent / "downloads.json"


def _load_count() -> int:
    try:
        return int(json.loads(STATS_FILE.read_text())["count"])
    except (OSError, ValueError, KeyError):
        return 0


def _save_count(n: int) -> None:
    tmp = STATS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"count": n}))
    tmp.replace(STATS_FILE)


async def _bump_count() -> None:
    global _download_count
    async with _count_lock:
        _download_count += 1
        _save_count(_download_count)


def _fmt_uptime(seconds: float) -> str:
    s = int(seconds)
    d, rem = divmod(s, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d} hari {h} jam"
    if h:
        return f"{h} jam {m} menit"
    return f"{m} menit"


_download_count = _load_count()
_count_lock = asyncio.Lock()

RESOLUTIONS = (144, 240, 360, 480, 720, 1080)

WELCOME = (
    "\U0001F3B5 *Bot Download Media*\n\n"
    "Kirim link, lalu pilih:\n"
    "\u2022 \U0001F3B5 MP3 (audio)\n"
    "\u2022 \U0001F3AC MP4 (video, pilih resolusi 144p\u20131080p)\n\n"
    "Sumber didukung: YouTube, Facebook, TikTok, Instagram, X"
)

GUIDANCE = (
    "Kirim link yang valid dari: YouTube, Facebook, TikTok, Instagram, X.\n"
    "Contoh:\n"
    "`https://youtube.com/watch?v=dQw4w9WgXcQ`"
)

KIND_LABEL = {"mp3": "audio", "mp4": "video"}


def format_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("\U0001F3B5 MP3", callback_data="mp3"),
                InlineKeyboardButton("\U0001F3AC MP4", callback_data="mp4"),
            ]
        ]
    )


def resolution_buttons() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(f"{h}p", callback_data=f"res_{h}")
            for h in RESOLUTIONS[i : i + 2]
        ]
        for i in range(0, len(RESOLUTIONS), 2)
    ]
    rows.append([InlineKeyboardButton("\u2699\uFE0F Auto (terbaik)", callback_data="res_auto")])
    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(WELCOME, parse_mode="Markdown")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uptime = _fmt_uptime(time.time() - START_TIME)
    total, free = shutil.disk_usage("/")[1], shutil.disk_usage("/")[2]
    text = (
        "\U0001F4CA *Status Bot*\n\n"
        f"\u23F1\uFE0F Uptime: {uptime}\n"
        f"\u2B07\uFE0F Total download: {_download_count}\n"
        f"\U0001F4BE Sisa disk: {free / 1e9:.1f} GB (dari {total / 1e9:.1f} GB)"
    )
    await update.effective_message.reply_text(text, parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    url = extract_supported_url(message.text or "")
    if not url:
        await message.reply_text(GUIDANCE, parse_mode="Markdown")
        return

    context.user_data["pending_url"] = url
    await message.reply_text(
        "Pilih format untuk:\n`%s`" % url, reply_markup=format_buttons(), parse_mode="Markdown"
    )


async def _download(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    kind: str,
    max_height: int | None = None,
) -> None:
    query = update.callback_query
    status = query.message
    what = KIND_LABEL.get(kind, "media")
    state = {"pct": -1, "at": 0.0}

    async def progress(pct: float) -> None:
        now = time.monotonic()
        pct_int = int(pct // 10 * 10)
        if pct_int != state["pct"] and now - state["at"] >= 3:
            state["pct"] = pct_int
            state["at"] = now
            try:
                await status.edit_text(f"\u23F3 Mengunduh {what}... {pct_int}%")
            except TelegramError:
                pass  # progres hanya informasi

    async def stage(msg: str) -> None:
        try:
            await status.edit_text(f"\u23F3 {msg}")
        except TelegramError:
            pass

    try:
        await status.edit_text(f"\u23F3 Mengunduh {what}...")
        async with _semaphore:
            path, title = await download_media(url, kind, progress, stage, max_height=max_height)
    except TooLargeError as e:
        await status.edit_text(f"\u26A0\uFE0F {e}")
        return
    except DownloadError as e:
        await status.edit_text(f"\u274C {e}")
        return
    except Exception as e:
        logger.exception("Error tak terduga saat mengunduh")
        try:
            await status.edit_text(f"\u274C Error tak terduga: {e}")
        except TelegramError:
            pass
        return

    try:
        await status.edit_text("\U0001F4E4 Mengirim file...")
        with path.open("rb") as f:
            if kind == "mp3":
                await status.reply_audio(audio=f, title=title, filename=path.name)
            else:
                await status.reply_video(video=f, filename=path.name)
        await _bump_count()
    except TelegramError as e:
        await status.edit_text(f"\u274C Gagal mengirim: {e}")
    except Exception as e:
        logger.exception("Error tak terduga saat mengirim")
        try:
            await status.edit_text(f"\u274C Error tak terduga: {e}")
        except TelegramError:
            pass
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)  # bersihkan direktori temp
        await status.delete()


async def handle_format_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if not context.user_data.get("pending_url"):
        await query.edit_message_text("\u23F3 Link kedaluwarsa \u2014 kirim link baru lagi.")
        return
    if query.data == "mp4":
        await query.edit_message_text(
            "Pilih resolusi:", reply_markup=resolution_buttons()
        )
        return
    await _download(update, context, context.user_data.pop("pending_url"), "mp3")


async def handle_resolution_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    url = context.user_data.pop("pending_url", None)
    if not url:
        await query.edit_message_text("\u23F3 Link kedaluwarsa \u2014 kirim link baru lagi.")
        return

    height = query.data.removeprefix("res_")
    max_height = None if height == "auto" else int(height)
    await _download(update, context, url, "mp4", max_height=max_height)


async def _auto_update() -> None:
    """Update yt-dlp/curl_cffi harian lalu restart sendiri (PID sama, systemd tetap)."""
    while True:
        await asyncio.sleep(86400)
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "-q", "-U",
                "yt-dlp", "curl_cffi>=0.10,<0.16",
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            if await proc.wait() == 0:
                os.execv(sys.executable, [sys.executable, *sys.argv])
        except Exception:
            logger.exception("Auto-update yt-dlp gagal")


async def _spawn_auto_update(application: Application) -> None:
    application.create_task(_auto_update())


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN belum diset. Salin .env.example ke .env dan isi token dari @BotFather."
        )

    app = Application.builder().token(token).build()
    app.post_init = _spawn_auto_update
    # Bersihkan sisa dir temp download dari proses yang di-kill.
    for stale in Path(tempfile.gettempdir()).glob("ytdl_*"):
        shutil.rmtree(stale, ignore_errors=True)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_format_choice, pattern="^(mp3|mp4)$"))
    app.add_handler(
        CallbackQueryHandler(
            handle_resolution_choice, pattern="^res_(144|240|360|480|720|1080|auto)$"
        )
    )
    logger.info("Bot berjalan, tekan Ctrl+C untuk berhenti.")
    app.run_polling()


if __name__ == "__main__":
    main()
