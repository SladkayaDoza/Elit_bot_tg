from get_schedule import get_schedule, get_next_time, reversed_groups, groups, update_groups
from datetime import datetime, timedelta
from pyrogram import Client, filters, idle
from os.path import join, dirname
from tools import extract_digits
from dotenv import load_dotenv
import logging
import asyncio
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

async def send_on_time(text, date, channel_id):
    if not text or not text.strip():
        return
    wait_time = (date - datetime.now()).total_seconds() - seconds_before_send
    print(f"Запланировано сообщение, отправка через: {wait_time} секунд, Точное время: {date}")
    if wait_time > 0:
        await asyncio.sleep(wait_time)
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
    print(args[1])
    if reversed_groups[args[1]]:
        await base.set_channel_to_updates(str(message.chat.id), reversed_groups[args[1]])
        await message.reply_text(f"Этот канал добавлен в базу для обновлений: {message.chat.id}\nГруппа: {args[1]}")
    else:
        await message.reply_text(f"Такой группы: {args[1]}, нет в базе? см. [списки](https://schedule.sumdu.edu.ua/index/json/?method=getGroups)")

@app.on_message(filters.command("e") & filters.user("JetLeica"))
async def e(client, message):
    await message.reply_text(f"{eval(message.text[2:])}")

# Обработчик команды /get
@app.on_message(filters.command("get"))
async def get(client, message):
    args = message.text.split(maxsplit=3)
    num_list = 0
    

    tm = datetime.now().strftime("%d.%m.%Y")
    if len(args) > 1: 
        tm = args[1] if len(args[1]) > 3 else await extract_digits(args[1])
        if len(args[1]) < 4:
            date = datetime.now() + timedelta(days=int(tm))
            tm = date.strftime("%d.%m.%Y")
    if len(args) > 2:
        num_list = int(args[2])

    id_group = base.database["channels"][str(message.chat.id)][num_list]
    
    if len(args) > 3:
        id_group = args[3]

    response = ""
    try:
        if not base.database["channels"][str(message.chat.id)][0]:
            await message.reply_text(f"Ви ще не встановили жодної групи для розсилки")
            return
        response, _ = await get_schedule(tm, id_group, str(message.chat.id))
        if len(response) < 5: response = "Відпочивайте! На цей день немає пар!"
    except Exception as e:
        # response = "ValueError, Example: 17.03.2024"
        response = e

    await message.reply_text(f"{tm}\n\n{response}", disable_web_page_preview=True)


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
