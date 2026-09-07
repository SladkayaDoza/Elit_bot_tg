from icalendar import Calendar
from bs4 import BeautifulSoup
from datetime import datetime
import requests
import urllib3  # WARNING - urllib3<2
import logging
import json
import base
import re

requests.packages.urllib3.disable_warnings()
requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS += ':HIGH:!DH:!aNULL'

groups = json.load(open("groups.json", encoding="utf-8"))
reversed_groups = {v: k for k, v in groups.items()}

def update_groups():
    """Загружает список групп с API SumDU и обновляет groups.json"""
    global groups, reversed_groups
    try:
        url = "https://schedule.sumdu.edu.ua/index/json/?method=getGroups"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, verify=False, timeout=30)
        data = response.json()

        # API возвращает список [{"ID": ..., "NAME": ...}, ...]
        new_groups = {}
        for item in data:
            new_groups[str(item["ID"])] = item["NAME"]

        # Сохраняем в файл
        with open("groups.json", "w", encoding="utf-8") as f:
            json.dump(new_groups, f, ensure_ascii=False)

        # Обновляем глобальные переменные
        groups = new_groups
        reversed_groups = {v: k for k, v in groups.items()}
        logging.info(f"Группы обновлены: {len(groups)} записей")
    except Exception as e:
        logging.error(f"Ошибка обновления групп: {e}")

async def get_schedule(tm, id_grp: str, channel_id: str):
    pattern = re.compile(r'https?://[^\s"]+')


    url = f"http://schedule.sumdu.edu.ua/index/json/?method=getSchedules&date_beg={tm}&date_end={tm}&id_aud=0&id_fio=0&id_grp={id_grp}"

    headers = {
        "accept": "*/*",
        "accept-language": "ru",
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    }

    response = requests.post(url, headers=headers, verify = False)
    content = response.json()

    data_list = []
    for i in content:
        # Пропускаем фантомные записи (пустые NAME_STUD и NAME_DISC)
        name_stud = i.get("NAME_STUD", "").strip().strip("-").strip()
        name_disc = i.get("NAME_DISC", "").strip().strip("-").strip()
        if not name_stud and not name_disc:
            continue

        matches = re.findall(pattern, i["INFO"])
        if matches: matches[0] = re.sub(r"<[^>]+>", "", matches[0], flags=re.S)

        try:
            if base.database["update_channels"][channel_id][i["NAME_FIO"]]:
                matches = [base.database["update_channels"][channel_id][i["NAME_FIO"]]]
        except: pass

        data_list.append(f'`{groups[id_grp] if id_grp in groups.keys() else id_grp}`\n{i["NAME_PAIR"]} {"[" + i["TIME_PAIR"] + "](" + matches[0] + ")" if matches else i["TIME_PAIR"]} - {i["NAME_STUD"]}\n`{i["NAME_DISC"]}`\n{i["NAME_FIO"]}')

    text = ""
    for i in data_list: text += i + "\n\n"

    return text, data_list


def get_next_time(id_grp):
    # URL файла .ics
    url = f'https://sh.cabinet.sumdu.edu.ua/uk/index/ical?id_grp={id_grp}&date_end={datetime.now().strftime("%d.%m.%Y")}'

    # Выполнение GET-запроса для получения файла .ics
    response = requests.get(url)

    # Проверка, что запрос выполнен успешно
    if response.status_code == 200:
        ics_content = response.text  # Получаем содержимое файла .ics

        # Парсинг файла .ics с помощью библиотеки icalendar
        calendar = Calendar.from_ical(ics_content)

        times = []
        # Пример чтения событий из календаря
        for component in calendar.walk():
            if component.name == "VEVENT":
                dtstart = component.get('dtstart').dt
                print(dtstart)
                if isinstance(dtstart, datetime):
                    if dtstart.tzinfo is not None:  # Если datetime имеет информацию о временной зоне
                        dtstart = dtstart.replace(tzinfo=None)
                elif isinstance(dtstart, datetime):  # Если dtstart - это объект date
                    dtstart = datetime.combine(dtstart, datetime.min.time())
                
                # Сравнение с текущим временем
                # if isinstance(dtstart, datetime) and dtstart > datetime.now():
                #     times.append(dtstart)

                # test
                if isinstance(dtstart, datetime):
                    times.append(dtstart)
        return times

    else:
        print(f"Ошибка при получении файла: {response.status_code}")