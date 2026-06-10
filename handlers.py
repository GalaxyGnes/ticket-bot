"""
ОБРАБОТЧИКИ КОМАНД БОТА
"""

import logging
import aiosqlite
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_ID
from database import (
    get_or_create_user, get_user_credits, add_credits,
    deduct_credit, create_monitor, get_user_monitors,
    deactivate_monitor, get_all_users, deactivate_user,
    get_user_by_ref, get_user_referrals
)

router = Router()


class AddMonitor(StatesGroup):
    waiting_from  = State()
    waiting_to    = State()
    waiting_date  = State()
    waiting_train = State()
    waiting_wagon = State()
class AdminStates(StatesGroup):
    waiting_broadcast = State()
    waiting_give      = State()
    waiting_take      = State()


def main_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить мониторинг", callback_data="add_monitor")
    kb.button(text="📋 Мои мониторинги",     callback_data="my_monitors")
    kb.button(text="💳 Мой баланс",          callback_data="my_balance")
    kb.button(text="🔗 Пригласить друга",    callback_data="referral")
    kb.button(text="❓ Как это работает",    callback_data="how_it_works")
    kb.button(text="🆘 Поддержка",          callback_data="support")
    kb.adjust(1)
    return kb.as_markup()

async def show_wagon_keyboard(message):
    kb = InlineKeyboardBuilder()
    kb.button(text="🎯 Любое место",   callback_data="wagon_Любое")
    kb.button(text="СВ (люкс)",        callback_data="wagon_СВ")
    kb.button(text="К (купе)",         callback_data="wagon_К")
    kb.button(text="П (плацкарт)",     callback_data="wagon_П")
    kb.button(text="О (общий)",        callback_data="wagon_О")
    kb.button(text="С (сидячий)",      callback_data="wagon_С")
    kb.adjust(1, 2, 2, 2)
    await message.answer(
        "💺 <b>Шаг 5/5</b> — Тип вагона:",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


# ─── СТАРТ ───────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user

    # Проверяем реферальный параметр — /start ref_123456789
    args = message.text.split()
    ref_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_id = int(args[1].replace("ref_", ""))
            if ref_id == user.id:
                ref_id = None  # нельзя пригласить самого себя
        except Exception:
            ref_id = None

    # Проверяем новый ли пользователь
    async with aiosqlite.connect("bot_database.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user.id,)) as cursor:
            existing = await cursor.fetchone()

    is_new = existing is None

    await get_or_create_user(user.id, user.username or "", user.full_name)

    # Если новый пользователь пришёл по реферальной ссылке
    if is_new and ref_id:
        ref_user = await get_user_by_ref(ref_id)
        if ref_user:
            # Записываем кто пригласил
            async with aiosqlite.connect("bot_database.db") as db:
                await db.execute(
                    "UPDATE users SET referred_by = ? WHERE user_id = ?",
                    (ref_id, user.id)
                )
                await db.commit()

            # Даём кредит пригласившему
            await add_credits(ref_id, 1)

            # Уведомляем пригласившего
            try:
                await message.bot.send_message(
                    chat_id=ref_id,
                    text=(
                        f"🎉 По твоей ссылке зарегистрировался "
                        f"<b>{user.full_name}</b>!\n\n"
                        f"💳 Тебе начислен <b>1 кредит</b>."
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass

    credits = await get_user_credits(user.id)
    try:
        await message.answer(
            f"👋 Привет, <b>{user.first_name}</b>!\n\n"
            f"Я слежу за билетами на <b>rw.by</b> и сообщу когда появятся места.\n\n"
            f"💳 Доступно мониторингов: <b>{credits}</b>",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
    except Exception as e:
        logging.warning(f"Не удалось отправить приветствие {user.id}: {e}")
        if "Forbidden" in str(e):
            await deactivate_user(user.id)


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Как пользоваться ботом:</b>\n\n"
        "1️⃣ Нажми <b>Добавить мониторинг</b>\n"
        "2️⃣ Введи маршрут и дату — бот покажет список поездов\n"
        "3️⃣ Выбери поезд и тип вагона\n"
        "4️⃣ Бот проверяет билеты каждую минуту\n"
        "5️⃣ Как только появятся — пришлю уведомление\n\n"
        "💳 Каждый мониторинг стоит 1 кредит.\n"
        "Купить кредиты — кнопка <b>💳 Мой баланс</b>",
        parse_mode="HTML",
    )


# ─── ДОБАВИТЬ МОНИТОРИНГ ─────────────────────────────────────

@router.callback_query(F.data == "add_monitor")
async def cb_add_monitor(callback: CallbackQuery, state: FSMContext):
    credits = await get_user_credits(callback.from_user.id)
    if credits <= 0:
        await callback.message.answer(
            "❌ У тебя нет доступных мониторингов.\n"
            "Обратись к администратору для пополнения."
        )
        await callback.answer()
        return

    await state.set_state(AddMonitor.waiting_from)
    await callback.message.answer(
        "📍 <b>Шаг 1/4</b> — Откуда едешь?\n\nНапример: <code>Минск</code>\n\nОтмена: /start",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddMonitor.waiting_from)
async def step_from(message: Message, state: FSMContext):
    await state.update_data(from_city=message.text.strip())
    await state.set_state(AddMonitor.waiting_to)
    await message.answer(
        "📍 <b>Шаг 2/4</b> — Куда едешь?\n\nНапример: <code>Гродно</code>\n\nОтмена: /start",
        parse_mode="HTML",
    )


@router.message(AddMonitor.waiting_to)
async def step_to(message: Message, state: FSMContext):
    await state.update_data(to_city=message.text.strip())
    await state.set_state(AddMonitor.waiting_date)
    await message.answer(
        "📅 <b>Шаг 3/4</b> — Дата отправления?\n\nФормат: <code>ДД.ММ.ГГГГ</code>\nНапример: <code>15.06.2026</code>\n\nОтмена: /start",
        parse_mode="HTML",
    )


@router.message(AddMonitor.waiting_date)
async def step_date(message: Message, state: FSMContext):
    from datetime import datetime
    date_text = message.text.strip()
    try:
        datetime.strptime(date_text, "%d.%m.%Y")
    except ValueError:
        await message.answer("❌ Неверный формат! Введи дату так: <code>15.06.2026</code>", parse_mode="HTML")
        return

    await state.update_data(date=date_text)
    data = await state.get_data()
    await message.answer("🔍 Ищу поезда, подожди...")

    from trains import get_trains
    trains = await get_trains(data["from_city"], data["to_city"], date_text)

    await state.set_state(AddMonitor.waiting_train)

    if not trains:
        await message.answer(
            "😔 Не смог загрузить список поездов.\n\n"
            "Введи номер поезда вручную:\nНапример: <code>731Б</code>",
            parse_mode="HTML",
        )
        return

    kb = InlineKeyboardBuilder()
    for t in trains:
        btn_text = f"🚂 {t['num']} | {t['dep']}→{t['arr']}"
        kb.button(text=btn_text, callback_data=f"train_{t['num']}")
    kb.button(text="✏️ Ввести номер вручную", callback_data="train_manual")
    kb.adjust(1)

    await message.answer(
        f"🚂 <b>Поезда {data['from_city']} → {data['to_city']} на {date_text}:</b>\n\n"
        f"Выбери поезд:",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.message(AddMonitor.waiting_train)
async def step_train(message: Message, state: FSMContext):
    await state.update_data(train_num=message.text.strip().upper())
    await state.set_state(AddMonitor.waiting_wagon)
    await show_wagon_keyboard(message)


@router.callback_query(F.data.startswith("train_"), AddMonitor.waiting_train)
async def cb_train_select(callback: CallbackQuery, state: FSMContext):
    train_id = callback.data.replace("train_", "")

    if train_id == "manual":
        await callback.message.answer(
            "✏️ Введи номер поезда вручную:\nНапример: <code>731Б</code>",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    await state.update_data(train_num=train_id)
    await state.set_state(AddMonitor.waiting_wagon)
    await callback.message.answer(f"✅ Выбран поезд <b>{train_id}</b>", parse_mode="HTML")
    await show_wagon_keyboard(callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("wagon_"), AddMonitor.waiting_wagon)
async def step_wagon(callback: CallbackQuery, state: FSMContext):
    wagon_type = callback.data.replace("wagon_", "")
    data = await state.get_data()

    if not data.get("train_num"):
        await state.clear()
        await callback.message.answer("⚠️ Что-то пошло не так. Нажми /start и попробуй снова.")
        await callback.answer()
        return

    await callback.message.answer("🔍 Проверяю поезд на rw.by, подожди...")
    await callback.answer()

    from checker import check_tickets
    result = await check_tickets(
        train_num=data["train_num"],
        from_city=data["from_city"],
        to_city=data["to_city"],
        date=data["date"],
        wagon_type=wagon_type,
    )

    await state.clear()
    user_id = callback.from_user.id
    await deduct_credit(user_id)
    await create_monitor(
        user_id=user_id,
        train_num=data["train_num"],
        from_city=data["from_city"],
        to_city=data["to_city"],
        date=data["date"],
        wagon_type=wagon_type,
    )

    credits_left = await get_user_credits(user_id)

    if result.get("available"):
        status = f"🟢 Уже есть {result['seats']} мест — уведомление отправлено!"
    else:
        status = "🟡 Мест пока нет, слежу каждые 30 секунд..."

    await callback.message.answer(
        f"✅ <b>Мониторинг запущен!</b>\n\n"
        f"🚂 Поезд: <b>{data['train_num']}</b>\n"
        f"📍 {data['from_city']} → {data['to_city']}\n"
        f"📅 {data['date']} | 💺 {wagon_type}\n"
        f"{status}\n\n"
        f"💳 Осталось мониторингов: <b>{credits_left}</b>",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )


# ─── МОИ МОНИТОРИНГИ ─────────────────────────────────────────

@router.callback_query(F.data == "my_monitors")
async def cb_my_monitors(callback: CallbackQuery):
    monitors = await get_user_monitors(callback.from_user.id)

    if not monitors:
        await callback.message.answer("📋 У тебя пока нет активных мониторингов.", reply_markup=main_menu_kb())
        await callback.answer()
        return

    text = "📋 <b>Твои активные мониторинги:</b>\n\n"
    kb = InlineKeyboardBuilder()

    for m in monitors:
        text += f"🔍 #{m['id']} | <b>{m['train_num']}</b> {m['from_city']} → {m['to_city']} ({m['date']}, {m['wagon_type']})\n"
        kb.button(text=f"❌ Отменить #{m['id']}", callback_data=f"cancel_{m['id']}")

    kb.button(text="🏠 Главное меню", callback_data="main_menu")
    kb.adjust(1)

    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_"))
async def cb_cancel_monitor(callback: CallbackQuery):
    monitor_id = int(callback.data.replace("cancel_", ""))
    await deactivate_monitor(monitor_id)
    await callback.message.answer(f"✅ Мониторинг #{monitor_id} остановлен.", reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery):
    credits = await get_user_credits(callback.from_user.id)
    await callback.message.answer(
        f"🏠 Главное меню\n💳 Мониторингов: <b>{credits}</b>",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


# ─── БАЛАНС ──────────────────────────────────────────────────

@router.callback_query(F.data == "my_balance")
async def cb_balance(callback: CallbackQuery):
    credits = await get_user_credits(callback.from_user.id)
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Купить мониторинги", callback_data="buy_credits")
    kb.button(text="🏠 Главное меню",       callback_data="main_menu")
    kb.adjust(1)
    await callback.message.answer(
        f"💳 <b>Твой баланс:</b> {credits} мониторингов\n\n"
        f"Купи дополнительные мониторинги через Telegram Stars:",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()

@router.callback_query(F.data == "buy_credits")
async def cb_buy_credits(callback: CallbackQuery):
    from config import CREDIT_PACKAGES
    kb = InlineKeyboardBuilder()
    for i, pkg in enumerate(CREDIT_PACKAGES):
        kb.button(text=pkg["label"], callback_data=f"buy_{i}")
    kb.button(text="◀️ Назад", callback_data="my_balance")
    kb.adjust(1)
    await callback.message.answer(
        "💳 <b>Купить мониторинги</b>\n\n"
        "Выбери пакет — оплата через Telegram Stars:",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("buy_"))
async def cb_buy_package(callback: CallbackQuery):
    from config import CREDIT_PACKAGES
    from aiogram.types import LabeledPrice

    try:
        idx = int(callback.data.replace("buy_", ""))
        pkg = CREDIT_PACKAGES[idx]
    except Exception:
        await callback.answer("❌ Ошибка")
        return

    await callback.bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"Мониторинги БЖД",
        description=f"{pkg['credits']} мониторингов билетов на rw.by",
        payload=f"credits_{idx}_{callback.from_user.id}",
        currency="XTR",  # XTR = Telegram Stars
        prices=[LabeledPrice(label=pkg["label"], amount=pkg["stars"])],
        provider_token="",  # для Stars всегда пустой
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(query):
    """Telegram спрашивает подтвердить платёж — всегда говорим OK"""
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message):
    """Платёж прошёл — начисляем кредиты"""
    from config import CREDIT_PACKAGES

    payload = message.successful_payment.invoice_payload
    # payload формат: credits_IDX_USERID
    parts = payload.split("_")
    idx = int(parts[1])
    pkg = CREDIT_PACKAGES[idx]

    await add_credits(message.from_user.id, pkg["credits"])
    credits = await get_user_credits(message.from_user.id)

    await message.answer(
        f"✅ <b>Оплата прошла!</b>\n\n"
        f"💳 Начислено: <b>{pkg['credits']} мониторингов</b>\n"
        f"💰 Итого на балансе: <b>{credits}</b>",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )

@router.callback_query(F.data == "referral")
async def cb_referral(callback: CallbackQuery):
    user_id = callback.from_user.id
    referrals = await get_user_referrals(user_id)
    
    # Генерируем реферальную ссылку
    bot_info = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    await callback.message.answer(
        f"🔗 <b>Реферальная программа</b>\n\n"
        f"Приглашай друзей и получай <b>1 кредит</b> за каждого!\n\n"
        f"Твоя ссылка:\n<code>{ref_link}</code>\n\n"
        f"👥 Приглашено друзей: <b>{referrals}</b>",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()

@router.callback_query(F.data == "how_it_works")
async def cb_how_it_works(callback: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Попробовать", callback_data="add_monitor")
    kb.button(text="🏠 Главное меню", callback_data="main_menu")
    kb.adjust(1)
    await callback.message.answer(
        "🚂 <b>Как работает бот?</b>\n\n"
        "Ты хочешь купить билет на поезд, но мест нет.\n"
        "Что делать? Ждать и обновлять страницу вручную?\n\n"
        "Бот делает это за тебя!\n\n"
        "⚙️ <b>Принцип работы:</b>\n"
        "Каждые 30 секунд бот проверяет rw.by — "
        "и как только кто-то сдаёт билет, "
        "ты мгновенно получаешь уведомление.\n\n"
        "📌 <b>Пример:</b>\n"
        "Поезд Минск → Гродно, все места заняты. "
        "Ты запускаешь мониторинг. "
        "Через час кто-то возвращает билет — "
        "бот сразу пишет тебе и даёт ссылку на покупку.\n\n"
        "💳 <b>Стоимость:</b>\n"
        "1 мониторинг = 30 ⭐ Telegram Stars\n"
        "3 мониторинга = 80 ⭐\n"
        "5 мониторингов = 125 ⭐\n\n"
        "🔗 <b>Пригласи друга</b> — получи 1 мониторинг бесплатно!",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()

@router.callback_query(F.data == "support")
async def cb_support(callback: CallbackQuery):
    from config import SUPPORT_USERNAME
    kb = InlineKeyboardBuilder()
    kb.button(text="✉️ Написать в поддержку", url=f"https://t.me/{SUPPORT_USERNAME}")
    kb.button(text="🏠 Главное меню", callback_data="main_menu")
    kb.adjust(1)
    await callback.message.answer(
        "🆘 <b>Поддержка</b>\n\n"
        "Если у тебя возникли вопросы или проблемы — "
        "напиши нам, ответим в ближайшее время!\n\n"
        "⏰ Время ответа: обычно до 4 часов",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


# ─── ПОВТОРИТЬ МОНИТОРИНГ ────────────────────────────────────

@router.callback_query(F.data.startswith("repeat_"))
async def cb_repeat_monitor(callback: CallbackQuery):
    try:
        monitor_id = int(callback.data.replace("repeat_", ""))
    except Exception:
        await callback.message.answer("❌ Не удалось повторить мониторинг.")
        await callback.answer()
        return

    # Берём данные старого мониторинга из БД
    import aiosqlite
    from database import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM monitors WHERE id = ?", (monitor_id,)
        ) as cursor:
            old_monitor = await cursor.fetchone()

    if not old_monitor:
        await callback.message.answer("❌ Мониторинг не найден.")
        await callback.answer()
        return

    user_id = callback.from_user.id
    credits = await get_user_credits(user_id)

    if credits <= 0:
        await callback.message.answer("❌ У тебя нет доступных мониторингов.")
        await callback.answer()
        return

    await deduct_credit(user_id)
    await create_monitor(
        user_id=user_id,
        train_num=old_monitor["train_num"],
        from_city=old_monitor["from_city"],
        to_city=old_monitor["to_city"],
        date=old_monitor["date"],
        wagon_type=old_monitor["wagon_type"],
    )

    credits_left = await get_user_credits(user_id)
    await callback.message.answer(
        f"✅ <b>Мониторинг возобновлён!</b>\n\n"
        f"🚂 Поезд: <b>{old_monitor['train_num']}</b>\n"
        f"📍 {old_monitor['from_city']} → {old_monitor['to_city']}\n"
        f"📅 {old_monitor['date']} | 💺 {old_monitor['wagon_type']}\n\n"
        f"💳 Осталось мониторингов: <b>{credits_left}</b>",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


# ─── АДМИН КОМАНДЫ ───────────────────────────────────────────

@router.message(Command("give"))
async def cmd_give(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Использование: /give <user_id> <количество>")
        return
    try:
        target_id = int(parts[1])
        amount = int(parts[2])
    except ValueError:
        await message.answer("❌ Пример: /give 123456789 10")
        return
    await add_credits(target_id, amount)
    await message.answer(f"✅ Пользователю {target_id} добавлено {amount} кредитов.")


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    from database import get_active_monitors
    monitors = await get_active_monitors()
    users = await get_all_users()
    await message.answer(
        f"📊 <b>Статистика:</b>\n\n"
        f"👥 Пользователей: <b>{len(users)}</b>\n"
        f"🔍 Активных мониторингов: <b>{len(monitors)}</b>",
        parse_mode="HTML",
    )


@router.message(Command("users"))
async def cmd_users(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    users = await get_all_users()
    if not users:
        await message.answer("Пользователей пока нет.")
        return

    from database import get_active_monitors
    all_monitors = await get_active_monitors()

    text = f"👥 <b>Все пользователи ({len(users)}):</b>\n\n"
    for u in users:
        username = f"@{u['username']}" if u['username'] else "без username"
        user_monitors = [m for m in all_monitors if m["user_id"] == u["user_id"]]
        monitors_str = f"{len(user_monitors)} активных" if user_monitors else "нет"
        text += (
            f"👤 <b>{u['full_name']}</b> ({username})\n"
            f"🆔 <code>{u['user_id']}</code> | 💳 {u['credits']} кред. | 🔍 {monitors_str}\n\n"
        )

    if len(text) > 4000:
        text = text[:4000] + "\n...(список обрезан)"

    await message.answer(text, parse_mode="HTML")


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    text = message.text.replace("/broadcast", "", 1).strip()
    if not text:
        await message.answer(
            "Использование: /broadcast Текст сообщения\n\n"
            "Например: /broadcast Бот будет недоступен 5 минут"
        )
        return

    users = await get_all_users()
    if not users:
        await message.answer("Пользователей нет.")
        return

    sent = 0
    failed = 0
    await message.answer(f"📤 Начинаю рассылку {len(users)} пользователям...")

    for user in users:
        try:
            await message.bot.send_message(
                chat_id=user["user_id"],
                text=f"📢 <b>Сообщение от администратора:</b>\n\n{text}",
                parse_mode="HTML",
            )
            sent += 1
        except Exception as e:
            logging.warning(f"Не удалось отправить {user['user_id']}: {e}")
            failed += 1
            if "Forbidden" in str(e):
                await deactivate_user(user["user_id"])

    await message.answer(
        f"✅ Рассылка завершена\n\nОтправлено: {sent}\nНе доставлено: {failed}"
    )

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    from database import get_active_monitors
    monitors = await get_active_monitors()
    users = await get_all_users()

    kb = InlineKeyboardBuilder()
    kb.button(text="👥 Пользователи",         callback_data="admin_users")
    kb.button(text="📊 Статистика",           callback_data="admin_stats")
    kb.button(text="📢 Рассылка",             callback_data="admin_broadcast")
    kb.button(text="💳 Выдать кредиты",       callback_data="admin_give")
    kb.button(text="🔍 Активные мониторинги", callback_data="admin_monitors")
    kb.button(text="➖ Забрать кредиты", callback_data="admin_take")
    kb.adjust(2)

    await message.answer(
        f"⚙️ <b>Админ панель</b>\n\n"
        f"👥 Пользователей: <b>{len(users)}</b>\n"
        f"🔍 Активных мониторингов: <b>{len(monitors)}</b>",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "admin_users")
async def cb_admin_users(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    users = await get_all_users()
    from database import get_active_monitors
    all_monitors = await get_active_monitors()

    text = f"👥 <b>Все пользователи ({len(users)}):</b>\n\n"
    for u in users:
        username = f"@{u['username']}" if u['username'] else "без username"
        user_monitors = [m for m in all_monitors if m["user_id"] == u["user_id"]]
        monitors_str = f"{len(user_monitors)} активных" if user_monitors else "нет"
        text += (
            f"👤 <b>{u['full_name']}</b> ({username})\n"
            f"🆔 <code>{u['user_id']}</code> | 💳 {u['credits']} кред. | 🔍 {monitors_str}\n\n"
        )

    if len(text) > 4000:
        text = text[:4000] + "\n...(список обрезан)"

    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Назад", callback_data="admin_back")
    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    from database import get_active_monitors
    monitors = await get_active_monitors()
    users = await get_all_users()

    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Назад", callback_data="admin_back")

    await callback.message.answer(
        f"📊 <b>Статистика:</b>\n\n"
        f"👥 Пользователей: <b>{len(users)}</b>\n"
        f"🔍 Активных мониторингов: <b>{len(monitors)}</b>",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_monitors")
async def cb_admin_monitors(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    from database import get_active_monitors
    monitors = await get_active_monitors()

    if not monitors:
        kb = InlineKeyboardBuilder()
        kb.button(text="◀️ Назад", callback_data="admin_back")
        await callback.message.answer("🔍 Активных мониторингов нет.", reply_markup=kb.as_markup())
        await callback.answer()
        return

    text = f"🔍 <b>Активные мониторинги ({len(monitors)}):</b>\n\n"
    for m in monitors:
        text += (
            f"#{m['id']} | {m['user_id']} | <b>{m['train_num']}</b> "
            f"{m['from_city']}→{m['to_city']} {m['date']}\n"
        )

    if len(text) > 4000:
        text = text[:4000] + "\n...(обрезано)"

    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Назад", callback_data="admin_back")
    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    await state.set_state(AdminStates.waiting_broadcast)
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="admin_back")
    await callback.message.answer(
        "📢 Введи текст рассылки:",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_give")
async def cb_admin_give(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    await state.set_state(AdminStates.waiting_give)
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="admin_back")
    await callback.message.answer(
        "💳 Введи user_id и количество кредитов через пробел:\n\n"
        "Например: <code>123456789 10</code>",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()

@router.callback_query(F.data == "admin_take")
async def cb_admin_take(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.waiting_take)
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="admin_back")
    await callback.message.answer(
        "➖ Введи user_id и количество кредитов для списания:\n\n"
        "Например: <code>123456789 5</code>",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.message(AdminStates.waiting_take)
async def admin_do_take(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    try:
        parts = message.text.split()
        target_id = int(parts[0])
        amount = int(parts[1])
        await add_credits(target_id, -amount)
        await message.answer(
            f"✅ У пользователя <code>{target_id}</code> списано <b>{amount}</b> кредитов.",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
    except Exception:
        await message.answer("❌ Неверный формат. Пример: <code>123456789 5</code>", parse_mode="HTML")


@router.message(AdminStates.waiting_broadcast)
async def admin_do_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    await state.clear()
    users = await get_all_users()
    sent = 0
    failed = 0

    for user in users:
        try:
            await message.bot.send_message(
                chat_id=user["user_id"],
                text=f"📢 <b>Сообщение от администратора:</b>\n\n{message.text}",
                parse_mode="HTML",
            )
            sent += 1
        except Exception as e:
            failed += 1
            if "Forbidden" in str(e):
                await deactivate_user(user["user_id"])

    await message.answer(
        f"✅ Рассылка завершена\n\nОтправлено: {sent}\nНе доставлено: {failed}",
        reply_markup=main_menu_kb(),
    )


@router.message(AdminStates.waiting_give)
async def admin_do_give(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    await state.clear()
    try:
        parts = message.text.split()
        target_id = int(parts[0])
        amount = int(parts[1])
        await add_credits(target_id, amount)
        await message.answer(
            f"✅ Пользователю <code>{target_id}</code> добавлено <b>{amount}</b> кредитов.",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
    except Exception:
        await message.answer("❌ Неверный формат. Пример: <code>123456789 10</code>", parse_mode="HTML")


@router.callback_query(F.data == "admin_back")
async def cb_admin_back(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    await state.clear()
    from database import get_active_monitors
    monitors = await get_active_monitors()
    users = await get_all_users()

    kb = InlineKeyboardBuilder()
    kb.button(text="👥 Пользователи",           callback_data="admin_users")
    kb.button(text="📊 Статистика",             callback_data="admin_stats")
    kb.button(text="📢 Рассылка",               callback_data="admin_broadcast")
    kb.button(text="💳 Выдать кредиты",         callback_data="admin_give")
    kb.button(text="🔍 Активные мониторинги",   callback_data="admin_monitors")
    kb.adjust(2)

    await callback.message.answer(
        f"⚙️ <b>Админ панель</b>\n\n"
        f"👥 Пользователей: <b>{len(users)}</b>\n"
        f"🔍 Активных мониторингов: <b>{len(monitors)}</b>",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()    
