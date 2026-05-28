"""
ПЛАНИРОВЩИК
Каждые N секунд проверяет все активные мониторинги
и отправляет уведомление если появились билеты
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from config import CHECK_INTERVAL
from database import get_active_monitors, deactivate_monitor
from checker import check_tickets


def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Создаёт и возвращает планировщик"""
    scheduler = AsyncIOScheduler()

    # Добавляем задачу: запускать check_all_monitors каждые CHECK_INTERVAL секунд
    scheduler.add_job(
        check_all_monitors,
        trigger="interval",
        seconds=CHECK_INTERVAL,
        args=[bot],
        id="ticket_checker",
        max_instances=1,   # не запускать повторно если предыдущая проверка ещё идёт
    )

    logging.info(f"Планировщик настроен: проверка каждые {CHECK_INTERVAL} сек.")
    return scheduler


async def check_all_monitors(bot: Bot):
    """Проверяет все активные мониторинги и шлёт уведомления"""
    monitors = await get_active_monitors()

    if not monitors:
        return  # Нет активных мониторингов — ничего не делаем

    logging.info(f"Проверяем {len(monitors)} мониторингов...")

    for monitor in monitors:
        result = await check_tickets(
            train_num=monitor["train_num"],
            from_city=monitor["from_city"],
            to_city=monitor["to_city"],
            date=monitor["date"],
            wagon_type=monitor["wagon_type"],
        )

        if result.get("available"):
            # 🎉 Билеты появились! Отправляем уведомление
            await notify_user(bot, monitor, result)

            # Останавливаем этот мониторинг (билет найден)
            await deactivate_monitor(monitor["id"])


async def notify_user(bot: Bot, monitor, result: dict):
    """Отправляет пользователю сообщение о появлении билетов"""
    text = (
        f"🎫 <b>Билеты появились!</b>\n\n"
        f"🚂 Поезд: <b>{monitor['train_num']}</b>\n"
        f"📍 {monitor['from_city']} → {monitor['to_city']}\n"
        f"📅 Дата: <b>{monitor['date']}</b>\n"
        f"💺 {result['details']}\n\n"
        f"⚡ <a href='https://pass.rw.by'>Купить на rw.by</a>"
    )

    try:
        await bot.send_message(
            chat_id=monitor["user_id"],
            text=text,
            parse_mode="HTML",
        )
        logging.info(f"Уведомление отправлено пользователю {monitor['user_id']}")
    except Exception as e:
        logging.error(f"Не удалось отправить уведомление: {e}")
