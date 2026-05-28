"""
КОНФИГ — читает настройки из файла .env
Твой токен и другие секреты хранятся только в .env, не в коде!
"""

import os
from dotenv import load_dotenv

# Загружаем переменные из файла .env
load_dotenv()

# Токен бота (берётся из .env файла)
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Твой Telegram ID — ты будешь владельцем/админом
# Узнать свой ID можно написав боту @userinfobot
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Как часто проверять билеты (в секундах)
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден! Проверь файл .env")
