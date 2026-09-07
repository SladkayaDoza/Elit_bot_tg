import json
import os

database = {}

if not os.path.exists("base.json"):
    with open("base.json", "w+", encoding="utf-8") as file:
        json.dump(database, file)
else:
    with open("base.json", "r", encoding="utf-8") as file:
        database = json.load(file)

async def save_data():
    with open("base.json", "w+", encoding="utf-8") as file:
        json.dump(database, file, sort_keys=False, indent=4, ensure_ascii=False, separators=(',', ': '))

async def remove_channel_to_updates(channel):
	try:
		database["channels"].pop(str(channel))
	except: pass
	try:
		database["update_channels"].pop(str(channel))
	except: pass
	await save_data()

async def remove_groups_channel(channel: str):
    try:
        database["channels"][channel] = []
    except: pass
    await save_data()

async def set_channel_to_updates(channel: str, group):
    if "channels" not in database:
        database["channels"] = {}

    if channel not in database["channels"]:
        database["channels"][channel] = []

    if not group in database["channels"][channel]: database["channels"][channel].append(group)
    await save_data()

async def set_link_to_teacher(channel: str, name, link):
    if "update_channels" not in database:
        database["update_channels"] = {}
    if channel not in database["update_channels"]:
        database["update_channels"][channel] = {}

    database["update_channels"][channel][name] = link
    await save_data()