from icalendar import Calendar
from bs4 import BeautifulSoup
from datetime import datetime
import requests
import asyncio
import ssl
import urllib3  # WARNING - urllib3<2
import logging
import json
import base
import re

requests.packages.urllib3.disable_warnings()


class TlsAdapter(requests.adapters.HTTPAdapter):
    """Сервер SumDU отдаёт только слабые DH-шифры, которые заблокированы
    в новых OpenSSL/urllib3. Явно задаём набор шифров без DH - работает
    и на urllib3<2, и на urllib3 2.x."""

    def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
        ctx = urllib3.util.ssl_.create_urllib3_context(ciphers="HIGH:!DH:!aNULL")
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(connections, maxsize, block, **kwargs)


session = requests.Session()
session.verify = False
session.headers.update({
    "accept": "*/*",
    "accept-language": "ru",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
})
session.mount("https://", TlsAdapter())
session.mount("http://", TlsAdapter())

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
        response = session.get(url, timeout=30)
        data = response.json()

        new_groups = {}
        if isinstance(data, dict):
            # Новый формат API: {"ID": "NAME", ...}
            for k, v in data.items():
                key = str(k).strip()
                name = str(v).strip()
                if key and name:
                    new_groups[key] = name
        elif isinstance(data, list):
            # Старый формат API: [{"ID": ..., "NAME": ...}, ...]
            for item in data:
                key = str(item.get("ID", "")).strip()
                name = str(item.get("NAME", "")).strip()
                if key and name:
                    new_groups[key] = name
        else:
            raise ValueError(f"Неизвестный формат ответа getGroups: {type(data).__name__}")

        # Если API вернул мусор/пустоту - не трогаем рабочие данные
        if not new_groups:
            raise ValueError("API getGroups вернул пустой список групп")

        # Сохраняем в файл
        with open("groups.json", "w", encoding="utf-8") as f:
            json.dump(new_groups, f, ensure_ascii=False)

        # Обновляем глобальные переменные
        groups = new_groups
        reversed_groups = {v: k for k, v in groups.items()}
        logging.info(f"Группы обновлены: {len(groups)} записей")
    except Exception as e:
        logging.error(f"Ошибка обновления групп: {e}")

def _parse_pair_start(time_pair):
    """'08:30-10:00' -> datetime(сегодня, 08:30). None при ошибке разбора."""
    try:
        start = str(time_pair).split("-")[0].strip()
        h, m = start.split(":")[:2]
        now = datetime.now()
        return datetime(now.year, now.month, now.day, int(h), int(m))
    except Exception:
        return None


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

    response = session.post(url, headers=headers)
    content = response.json()

    data_list = []
    times = []
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

        pair_start = _parse_pair_start(i["TIME_PAIR"])
        if pair_start is None:
            continue

        data_list.append(f'`{groups[id_grp] if id_grp in groups.keys() else id_grp}`\n{i["NAME_PAIR"]} {"[" + i["TIME_PAIR"] + "](" + matches[0] + ")" if matches else i["TIME_PAIR"]} - {i["NAME_STUD"]}\n`{i["NAME_DISC"]}`\n{i["NAME_FIO"]}')
        times.append(pair_start)

    text = ""
    for i in data_list: text += i + "\n\n"

    return text, data_list, times


def _fetch_schedule_data(tm, id_grp: str, channel_id: str):
    """Синхронный запрос расписания за дату tm в виде списка dict (без форматирования).
    Поля: time, pair, subject, type, teacher, link, group."""
    pattern = re.compile(r'https?://[^\s"]+')

    url = f"http://schedule.sumdu.edu.ua/index/json/?method=getSchedules&date_beg={tm}&date_end={tm}&id_aud=0&id_fio=0&id_grp={id_grp}"

    response = session.post(url, timeout=30)
    content = response.json()

    group_name = groups.get(id_grp, id_grp)
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

        data_list.append({
            "time": i["TIME_PAIR"],
            "pair": i["NAME_PAIR"],
            "subject": i["NAME_DISC"],
            "type": name_stud,
            "teacher": i["NAME_FIO"],
            "link": matches[0] if matches else None,
            "group": group_name,
        })

    return data_list


async def get_schedule_data(tm, id_grp: str, channel_id: str):
    """Расписание за дату tm в виде списка dict.
    Запрос выполняется в отдельном потоке, чтобы не блокировать event loop
    и позволить параллельную загрузку нескольких групп."""
    loop = asyncio.get_event_loop()
    data_list = await loop.run_in_executor(None, _fetch_schedule_data, tm, id_grp, channel_id)
    data_list.sort(key=lambda x: x["time"])
    return data_list


def get_next_time(id_grp):
    # URL файла .ics
    url = f'https://sh.cabinet.sumdu.edu.ua/uk/index/ical?id_grp={id_grp}&date_end={datetime.now().strftime("%d.%m.%Y")}'

    # Выполнение GET-запроса для получения файла .ics
    response = session.get(url)

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