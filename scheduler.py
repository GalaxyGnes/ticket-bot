"""
ПЛАНИРОВЩИК
Каждые N секунд проверяет все активные мониторинги
и отправляет уведомление если появились билеты
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from config import ADMIN_ID
from datetime import datetime
from config import CHECK_INTERVAL
from database import get_active_monitors, deactivate_monitor
from checker import check_tickets

async def notify_admin(bot: Bot, text: str):
    """Отправляет сообщение об ошибке администратору"""
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="HTML")
    except Exception:
        pass


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
    monitors = await get_active_monitors()
    if not monitors:
        return

    logging.info(f"Проверяем {len(monitors)} мониторингов...")

    for monitor in monitors:
        try:
            train_date = datetime.strptime(monitor["date"], "%d.%m.%Y")
            if train_date.date() < datetime.now().date():
                logging.info(f"Мониторинг #{monitor['id']} устарел")
                await deactivate_monitor(monitor["id"])
                try:
                    await bot.send_message(
                        chat_id=monitor["user_id"],
                        text=(
                            f"⏰ Мониторинг автоматически остановлен\n\n"
                            f"🚂 Поезд <b>{monitor['train_num']}</b> "
                            f"{monitor['from_city']} → {monitor['to_city']} "
                            f"на <b>{monitor['date']}</b> уже отправился.\n\n"
                            f"Билеты так и не появились."
                        ),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
                continue
        except Exception:
            pass

        try:
            result = await check_tickets(
                train_num=monitor["train_num"],
                from_city=monitor["from_city"],
                to_city=monitor["to_city"],
                date=monitor["date"],
                wagon_type=monitor["wagon_type"],
            )

            if result.get("available"):
                await notify_user(bot, monitor, result)
                await deactivate_monitor(monitor["id"])

        except Exception as e:
            error_text = (
                f"⚠️ <b>Ошибка мониторинга #{monitor['id']}</b>\n\n"
                f"🚂 {monitor['train_num']} {monitor['from_city']}→{monitor['to_city']}\n"
                f"📅 {monitor['date']}\n\n"
                f"❌ {str(e)[:200]}"
            )
            logging.error(f"Ошибка мониторинга #{monitor['id']}: {e}")
            await notify_admin(bot, error_text)

async def notify_user(bot: Bot, monitor, result: dict):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Повторить мониторинг", callback_data=f"repeat_{monitor['id']}")
    kb.button(text="🛒 Купить билет", url=result.get("url", "https://pass.rw.by"))
    kb.adjust(1)

    text = (
        f"🎫 <b>Билеты появились!</b>\n\n"
        f"🚂 Поезд: <b>{monitor['train_num']}</b>\n"
        f"📍 {monitor['from_city']} → {monitor['to_city']}\n"
        f"📅 Дата: <b>{monitor['date']}</b>\n"
        f"💺 {result['details']}\n"
        f"💰 Цена: <b>{result.get('price', 'уточните на сайте')}</b>"
    )

    try:
        await bot.send_message(
            chat_id=monitor["user_id"],
            text=text,
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
        logging.info(f"Уведомление отправлено пользователю {monitor['user_id']}")
    except Exception as e:
        logging.error(f"Не удалось отправить уведомление: {e}")
        await notify_admin(bot,
            f"⚠️ <b>Не удалось отправить уведомление</b>\n\n"
            f"👤 Пользователь: {monitor['user_id']}\n"
            f"🚂 {monitor['train_num']} {monitor['from_city']}→{monitor['to_city']}\n"
            f"❌ {str(e)[:200]}"
        )
