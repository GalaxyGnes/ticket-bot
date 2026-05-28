"""
ГЛАВНЫЙ ФАЙЛ БОТА
Запускай именно его: python bot.py
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db
from handlers import router
from scheduler import start_scheduler

# Настройка логов — будем видеть что происходит в консоли
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

async def main():
    # Инициализируем базу данных (создаём таблицы если их нет)
    await init_db()

    # Создаём объект бота с твоим токеном
    bot = Bot(token=BOT_TOKEN)

    # Dispatcher управляет обработчиками сообщений
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # Запускаем планировщик проверки билетов (каждые 60 секунд)
    scheduler = start_scheduler(bot)
    scheduler.start()

    logging.info("Бот запущен!")

    # Запускаем бота (polling = бот сам спрашивает Telegram есть ли новые сообщения)
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
