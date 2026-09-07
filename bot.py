from get_schedule import get_schedule, get_next_time, update_groups, get_schedule_data
import get_schedule as schedule_module
from datetime import datetime, timedelta
from pyrogram import Client, filters, idle
from os.path import join, dirname
from dotenv import load_dotenv
import logging
import aiohttp
import asyncio
import html
import json
import base
import os

dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)
bot_token = os.environ.get("BOT_TOKEN")

list_channels = []
times = []
texts = []
seconds_before_send = 420

# параметры телеграм
chat_id = "JetLeica"
# chat_id = -1002210269509

# Параметры api запроса
id_aud="0"
id_fio="0"
id_grp="1005332"

logging.basicConfig(level=logging.INFO)

# Инициализация клиента
app = Client("my_bot", bot_token=bot_token)

async def on_start():
    logging.info("Бот успешно запущен и работает.")

async def detect_topic(message):
    """Определяет ID топика форума из сообщения.
    None - обычный чат (не форум) или General."""
    # Сообщение-ответ внутри топика: reply_to_top_message_id = корень топика
    if getattr(message, "reply_to_top_message_id", None):
        return message.reply_to_top_message_id
    # Обычное сообщение в топике: ответ на корень топика (служебное сообщение)
    rid = getattr(message, "reply_to_message_id", None)
    if rid:
        try:
            root = await app.get_messages(message.chat.id, rid)
            if root and root.service:
                return rid
        except Exception:
            pass
    return None


async def send_on_time(text, date, channel_id):
    if not text or not text.strip():
        return
    wait_time = (date - datetime.now()).total_seconds() - seconds_before_send
    print(f"Запланировано сообщение, отправка через: {wait_time} секунд, Точное время: {date}")
    if wait_time > 0:
        await asyncio.sleep(wait_time)
        topic = base.get_topic(channel_id)
        if topic:
            # В форум-группе постим в сохранённый топик (ответ на корень топика)
            await app.send_message(channel_id, text, disable_web_page_preview=True,
                                   reply_to_message_id=topic)
        else:
            await app.send_message(channel_id, text, disable_web_page_preview=True)

async def update_database():
    await asyncio.sleep(3)
    global texts
    while True:
        # Обновляем список групп каждый день
        update_groups()

        for i in list(base.database["channels"].keys()):
            for unit in base.database["channels"][str(i)]:
                try:
                    times = get_next_time(unit)
                    _, texts = await get_schedule(datetime.now().strftime("%d.%m.%Y"), unit, i)
                    print(texts)

                    for t, j in enumerate(times):
                        print(f"Сообщение отправлено в {j}")
                        if texts[t] and texts[t].strip(): asyncio.create_task(send_on_time(texts[t], j, int(i)))
                except: pass

        now = datetime.now()
        next_run = datetime(now.year, now.month, now.day, 3, 0, 0) + timedelta(days=1)
        wait_time = (next_run - now).total_seconds()
        await asyncio.sleep(wait_time)
        
        print(texts)
        logging.info("База данных обновлена!")

# Обработчик команды /remove
@app.on_message(filters.command("remove"))
async def remove(client, message):
    await base.remove_channel_to_updates(message.chat.id)
    await message.reply_text("Цей канал видалено з бази")

# Обработчик команды /reset
@app.on_message(filters.command("reset"))
async def reset(client, message):
    await base.remove_groups_channel(str(message.chat.id))
    await message.reply_text("Групи видалені з каналу")

# Обработчик команды /plan
@app.on_message(filters.command("plan"))
async def plan(client, message):
    txt = ""
    for u, i in enumerate(times):
        txt += str(i) + "\n" + texts[u] + "\n"
    print(texts)
    await message.reply_text(txt)

# Обработчик команды /help
@app.on_message(filters.command("help"))
async def help(client, message):
    text = ""
    with open("help.txt", "r", encoding="utf-8") as file:
        text = file.read()
    await message.reply_text(text)

# Обработчик команды /setup
@app.on_message(filters.command("setup"))
async def setup(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text("Вкажіть назву групи: /setup І-31/1ем")
        return
    group_id = schedule_module.reversed_groups.get(args[1])
    print(args[1])
    if group_id:
        await base.set_channel_to_updates(str(message.chat.id), group_id)
        # Запоминаем топик форума, где бот был настроен, чтобы писать туда
        try:
            await base.set_topic(str(message.chat.id), await detect_topic(message))
        except Exception as e:
            logging.error(f"setup: не удалось определить топик: {e}")
        await message.reply_text(f"Этот канал добавлен в базу для обновлений: {message.chat.id}\nГруппа: {args[1]}")
    else:
        await message.reply_text(f"Такой группы: {args[1]}, нет в базе? см. [списки](https://schedule.sumdu.edu.ua/index/json/?method=getGroups)")

@app.on_message(filters.command("e") & filters.user("JetLeica"))
async def e(client, message):
    await message.reply_text(f"{eval(message.text[2:])}")

# ================= Rich Messages (Bot API 10.1) =================

esc = html.escape

# Окно дней для /get: вчера, сегодня, завтра, послезавтра
DAY_OFFSETS = [
    ("Вчора", -1),
    ("Сьогодні", 0),
    ("Завтра", 1),
    ("Післязавтра", 2),
]

RICH_CHUNK_LIMIT = 3500


async def send_rich(chat_id, rich_html, fallback_html, message_thread_id=None):
    """sendRichMessage с fallback на sendMessage (старые клиенты/ошибка rich)."""
    url = f"https://api.telegram.org/bot{bot_token}/sendRichMessage"
    payload = {"chat_id": chat_id, "rich_message": {"html": rich_html}}
    if message_thread_id:
        payload["message_thread_id"] = message_thread_id
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload,
                              timeout=aiohttp.ClientTimeout(total=30)) as resp:
                result = await resp.json()
        if result.get("ok"):
            return True
        logging.warning(f"sendRichMessage отклонён: {result}")
    except Exception as e:
        logging.error(f"sendRichMessage ошибка: {e}")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": fallback_html, "parse_mode": "HTML",
               "disable_web_page_preview": True}
    if message_thread_id:
        payload["message_thread_id"] = message_thread_id
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                return (await resp.json()).get("ok", False)
    except Exception as e:
        logging.error(f"sendMessage fallback ошибка: {e}")
        return False


def render_lesson_rich(l):
    link = f' <a href="{esc(l["link"])}">посилання</a>' if l["link"] else ""
    line_type = f' — <i>{esc(l["type"])}</i>' if l["type"] else ""
    line_teacher = f'<br/>{esc(l["teacher"])}' if l["teacher"] else ""
    return (
        f'<p><mark><b>{esc(l["time"])}</b></mark> '
        f'<code>{esc(", ".join(l["groups"]))}</code></p>'
        f'<blockquote><b>{esc(l["subject"])}</b>{line_type}{line_teacher}{link}</blockquote>'
    )


def render_lesson_plain(l):
    link = f'\n{l["link"]}' if l["link"] else ""
    line_type = f' — {l["type"]}' if l["type"] else ""
    line_teacher = f'\n{esc(l["teacher"])}' if l["teacher"] else ""
    return (
        f'<b>{esc(l["time"])}</b> <code>{esc(", ".join(l["groups"]))}</code>\n'
        f'<blockquote><b>{esc(l["subject"])}</b>{line_type}{line_teacher}{link}</blockquote>'
    )


def merge_lessons(lessons):
    """Объединяет пары с одинаковым временем, преподавателем и ссылкой:
    группы таких пар показываются вместе."""
    merged = []
    index = {}
    for l in lessons:
        key = (l["time"], l["teacher"], l["link"])
        if key in index:
            groups = merged[index[key]]["groups"]
            if l["group"] not in groups:
                groups.append(l["group"])
        else:
            m = dict(l)
            m["groups"] = [l["group"]]
            index[key] = len(merged)
            merged.append(m)
    return merged


async def collect_days(channel_groups, channel_id):
    """Расписание по всем группам канала для окна дней.
    Все запросы (4 дня × группы) выполняются параллельно.
    Возвращает [(rich_day, plain_day), ...] — пустые дни пропускаются."""
    # (tm, label, gid) для всех дней и групп сразу
    jobs = []
    for label, offset in DAY_OFFSETS:
        day = datetime.now() + timedelta(days=offset)
        tm = day.strftime("%d.%m.%Y")
        for gid in channel_groups:
            jobs.append((tm, label, gid))

    results = await asyncio.gather(
        *(get_schedule_data(tm, gid, channel_id) for tm, _, gid in jobs),
        return_exceptions=True,
    )

    # Собираем результаты по дням, сохраняя порядок дней
    by_day = {}
    for (tm, label, gid), res in zip(jobs, results):
        if isinstance(res, Exception):
            logging.error(f"/get: группа {gid}, дата {tm}: {res}")
            continue
        by_day.setdefault((tm, label), []).extend(res)

    parts = []
    for label, offset in DAY_OFFSETS:
        day = datetime.now() + timedelta(days=offset)
        tm = day.strftime("%d.%m.%Y")
        lessons = by_day.get((tm, label))
        if not lessons:
            continue
        lessons.sort(key=lambda x: x["time"])
        lessons = merge_lessons(lessons)
        head = f"{label} · {tm}"
        # По умолчанию развёрнут только день на сегодня; если пар сегодня нет —
        # завтра; если нет ни сегодня, ни завтра — все дни свёрнуты
        open_attr = " open" if label in ("Сьогодні", "Завтра") else ""
        rich = (f'<details{open_attr}><summary>{head}</summary>'
                + "".join(render_lesson_rich(l) for l in lessons) + "</details>")
        plain = f"<b>{head}</b>\n" + "\n".join(render_lesson_plain(l) for l in lessons)
        parts.append((rich, plain))
    return parts


# Обработчик команды /get — расписание на 4 дня для всех групп канала
@app.on_message(filters.command("get"))
async def get(client, message):
    channel_groups = base.database["channels"].get(str(message.chat.id)) or []
    if not channel_groups:
        await message.reply_text("Ви ще не встановили жодної групи для розсилки. Використайте: /setup <група>")
        return

    days = await collect_days(channel_groups, str(message.chat.id))

    if not days:
        await message.reply_text("Відпочивайте! Найближчими 4 днями пар немає.")
        return

    # Топик, в котором выполнена команда (иначе сохранённый при /setup)
    try:
        topic = await detect_topic(message) or base.get_topic(message.chat.id)
    except Exception:
        topic = base.get_topic(message.chat.id)

    # Разбивка на несколько сообщений по лимиту
    buf_r, buf_p = "", ""
    for rich, plain in days:
        if len(buf_r) + len(rich) + 10 > RICH_CHUNK_LIMIT:
            await send_rich(message.chat.id, buf_r, buf_p, message_thread_id=topic)
            buf_r, buf_p = "", ""
        sep_r = "<hr/>" if buf_r else ""
        buf_r += sep_r + rich
        buf_p += ("\n\n" if buf_p else "") + plain
    await send_rich(message.chat.id, buf_r, buf_p, message_thread_id=topic)


# Обработчик команды /set or pin
@app.on_message(filters.command("pin"))
async def pin(client, message):
    # Извлекаем текст после команды
    command_params = message.text.split(maxsplit=1)

    # Проверяем, что переданы оба параметра: ссылка и ФИО
    if len(command_params) < 2:
        await message.reply("Вкажіть посилання та повне Фіо вчителя через пробіл.")
        return

    # Разделяем текст на ссылку и ФИО
    link, name = command_params[1].split(maxsplit=1)

    await base.set_link_to_teacher(str(message.chat.id), name, link)

    # Дальнейшая обработка данных
    await message.reply(f"Посилання: {link}\nФіо вчителя: {name}")

# Обработчик команды /set
@app.on_message(filters.command("all") & filters.user("JetLeica"))
async def all(client, message):
    await message.reply(base.database)

async def main():
    # Запуск задач по расписанию
    asyncio.create_task(update_database())
    # asyncio.create_task(scheduled_message())
    
    # Запуск бота
    await app.start()
    logging.info("Бот запущен")
    await on_start()
    await idle()

# Запуск бота
app.run(main())
