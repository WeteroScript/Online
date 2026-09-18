# bot.py
# language: Python, target: Python 3.10+, aiogram 3 + aiohttp
# *BotHost: BOT_TOKEN и PORT ставятся платформой. CHAT_ID и WEBHOOK_SECRET — вручную.*

import os
import json
import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

# ── config ──────────────────────────────────────────────────────────
# BotHost: BOT_TOKEN ставится автоматически. Локально: TELEGRAM_TOKEN в .env
TELEGRAM_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")

# BotHost: PORT ставится автоматически. Локально: WEBHOOK_PORT в .env
PORT = int(os.getenv("PORT") or os.getenv("WEBHOOK_PORT", 8080))

CHAT_ID        = os.getenv("CHAT_ID")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "changeme")
WEBHOOK_HOST   = "0.0.0.0"   # BotHost требует 0.0.0.0, не 127.0.0.1

RARITY_FILTER = {"secret", "divine", "legendary", "eternal"}
RARITY_EMOJI  = {
    "secret":    "🟣",
    "divine":    "🟡",
    "legendary": "🔴",
    "eternal":   "🔵",
}

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("egg-notifier")

bot = Bot(
    token=TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

# ── webhook receiver ────────────────────────────────────────────────
async def handle_webhook(request: web.Request) -> web.Response:
    if request.headers.get("X-Webhook-Secret", "") != WEBHOOK_SECRET:
        log.warning("unauthorized webhook from %s", request.remote)
        return web.json_response({"error": "unauthorized"}, status=401)

    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid json"}, status=400)

    egg_name = data.get("egg_name", "Unknown Egg")
    rarity   = data.get("rarity", "unknown").lower()
    zone     = data.get("zone", "Unknown Zone")

    log.info("received: %s [%s] in %s", egg_name, rarity, zone)

    if rarity not in RARITY_FILTER:
        return web.json_response({"status": "filtered", "rarity": rarity})

    emoji = RARITY_EMOJI.get(rarity, "⚪")
    text = (
        f"{emoji} <b>{rarity.upper()} EGG SPAWNED</b>\n\n"
        f"🥚 <b>{egg_name}</b>\n"
        f"📍 Зона: <b>{zone}</b>\n"
        f"⭐ Редкость: <b>{rarity.capitalize()}</b>\n"
        f"🕐 {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
    )

    try:
        await bot.send_message(chat_id=CHAT_ID, text=text, disable_web_page_preview=True)
        log.info("sent: %s", egg_name)
    except Exception as e:
        log.exception("telegram send failed: %s", e)
        return web.json_response({"error": str(e)}, status=500)

    return web.json_response({"status": "sent"})

# ── startup ─────────────────────────────────────────────────────────
async def start_webhook():
    app = web.Application()
    app.router.add_post("/webhook", handle_webhook)
    app.router.add_get("/health", lambda r: web.json_response({"ok": True}))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEBHOOK_HOST, PORT)
    await site.start()
    log.info("webhook listening on %s:%s", WEBHOOK_HOST, PORT)

async def main():
    if not TELEGRAM_TOKEN:
        raise SystemExit("BOT_TOKEN / TELEGRAM_TOKEN не задан")
    if not CHAT_ID:
        raise SystemExit("CHAT_ID не задан")

    me = await bot.get_me()
    log.info("bot ready as @%s", me.username)
    await start_webhook()
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("shutdown")
