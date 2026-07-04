import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatType, ParseMode
from aiogram.types import Message

# ==================== НАСТРОЙКИ ====================

# Токен бота берётся из переменной окружения, которую нужно задать
# в панели BotHost (Настройки проекта -> Переменные окружения -> BOT_TOKEN)
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ID канала, куда бот будет присылать уведомления об изменении онлайна
NOTIFY_CHAT_ID = int(os.getenv("NOTIFY_CHAT_ID", "-1003980753812"))

# API со списком серверов
API_URL = "https://api.blackrussia.online/client/servers.json"

# Как часто опрашивать API (в секундах)
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "0.1"))

# Файл, в котором бот хранит последнее известное состояние серверов
# (нужно, чтобы после перезапуска бот "помнил" прошлые значения онлайна)
STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")

# Текст, который бот отправляет в личные сообщения
PRIVATE_REPLY_TEXT = "Доступ запрещён ⚠️ канал @BlackRussiaOnlineServer"

# Часовой пояс для отображения времени в уведомлениях (МСК = UTC+3)
TZ = timezone(timedelta(hours=3))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("online-bot")

if not BOT_TOKEN:
    raise RuntimeError(
        "Не найден BOT_TOKEN. Добавьте переменную окружения BOT_TOKEN "
        "в панели BotHost со значением токена вашего бота."
    )

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


# ==================== РАБОТА С СОСТОЯНИЕМ ====================

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("Не удалось прочитать state.json, начинаю с чистого состояния")
    return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ==================== РАБОТА С API ====================

def _first(d: dict, keys: list, default=None):
    """Возвращает значение первого найденного ключа из списка keys."""
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def normalize_server(raw: dict) -> dict:
    """
    Приводит "сырую" запись сервера из API к единому виду.
    Названия полей подобраны по наиболее частым вариантам ("name", "online" и т.д.).
    Если реальные названия полей в API другие — поправьте списки ключей ниже.
    """
    name = _first(raw, ["name", "server_name", "title", "label"], default="Неизвестный сервер")
    online = _first(raw, ["online", "players", "players_online", "current_players", "onlineCount"], default=0)
    max_players = _first(raw, ["max_players", "maxPlayers", "slots", "max_online", "max"], default=None)
    ping = _first(raw, ["ping", "latency", "responseTime"], default=None)

    try:
        online = int(online)
    except (TypeError, ValueError):
        online = 0

    if max_players is not None:
        try:
            max_players = int(max_players)
        except (TypeError, ValueError):
            max_players = None

    if ping is not None:
        try:
            ping = round(float(ping))
        except (TypeError, ValueError):
            ping = None

    server_id = _first(raw, ["id", "server_id", "code"], default=name)

    return {
        "id": str(server_id),
        "name": str(name),
        "online": online,
        "max": max_players,
        "ping": ping,
    }


async def fetch_servers() -> list:
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)

    # API может вернуть либо просто список, либо объект с полем-списком внутри
    if isinstance(data, dict):
        for key in ("servers", "data", "result", "list"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break

    if not isinstance(data, list):
        logger.error("Неожиданный формат ответа API: %r", type(data))
        return []

    return [normalize_server(item) for item in data if isinstance(item, dict)]


# ==================== ФОРМИРОВАНИЕ И ОТПРАВКА УВЕДОМЛЕНИЙ ====================

def build_message(server: dict, diff: int) -> str:
    now = datetime.now(TZ).strftime("%d.%m.%Y %H:%M:%S")

    if diff > 0:
        direction = "📈 Добавление онлайна"
        count_line = f"➕ Зашло: {diff}"
    else:
        direction = "📉 Уменьшение онлайна"
        count_line = f"➖ Вышло: {abs(diff)}"

    ping_line = f"{server['ping']} мс" if server["ping"] is not None else "н/д"
    online_line = f"{server['online']}"
    if server["max"] is not None:
        online_line += f"/{server['max']}"

    text = (
        f"🖥 <b>Сервер:</b> {server['name']}\n"
        f"{direction}\n"
        f"{count_line}\n"
        f"👥 <b>Онлайн сейчас:</b> {online_line}\n"
        f"🕒 <b>Время:</b> {now}\n"
        f"📶 <b>Пинг:</b> {ping_line}"
    )
    return text


async def check_servers_once(state: dict) -> dict:
    servers = await fetch_servers()
    if not servers:
        return state

    for server in servers:
        prev = state.get(server["id"])
        if prev is not None and prev.get("online") != server["online"]:
            diff = server["online"] - prev["online"]
            if diff != 0:
                text = build_message(server, diff)
                try:
                    await bot.send_message(NOTIFY_CHAT_ID, text)
                except Exception as e:
                    logger.error("Не удалось отправить сообщение в канал: %s", e)

        state[server["id"]] = {"online": server["online"], "name": server["name"]}

    return state


async def poller():
    state = load_state()
    logger.info("Запущен опрос API каждые %s секунд", POLL_INTERVAL)
    while True:
        try:
            state = await check_servers_once(state)
            save_state(state)
        except Exception as e:
            logger.exception("Ошибка при опросе API: %s", e)
        await asyncio.sleep(POLL_INTERVAL)


# ==================== ОБРАБОТКА ЛИЧНЫХ СООБЩЕНИЙ ====================

@dp.message()
async def handle_private(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(PRIVATE_REPLY_TEXT)


# ==================== ЗАПУСК ====================

async def main():
    asyncio.create_task(poller())
    logger.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
