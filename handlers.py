"""
ОБРАБОТЧИКИ КОМАНД БОТА
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_ID
from database import (
    get_or_create_user, get_user_credits, add_credits,
    deduct_credit, create_monitor, get_user_monitors, deactivate_monitor
)

router = Router()

class AddMonitor(StatesGroup):
    waiting_train  = State()
    waiting_from   = State()
    waiting_to     = State()
    waiting_date   = State()
    waiting_wagon  = State()


def main_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить мониторинг", callback_data="add_monitor")
    kb.button(text="📋 Мои мониторинги",     callback_data="my_monitors")
    kb.button(text="💳 Мой баланс",          callback_data="my_balance")
    kb.adjust(1)
    return kb.as_markup()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    # Сбрасываем любое незавершённое состояние при /start
    await state.clear()

    user = message.from_user
    await get_or_create_user(
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name,
    )
    credits = await get_user_credits(user.id)

    await message.answer(
        f"👋 Привет, <b>{user.first_name}</b>!\n\n"
        f"Я слежу за билетами на <b>rw.by</b> и сообщу когда появятся места.\n\n"
        f"💳 Доступно мониторингов: <b>{credits}</b>",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Как пользоваться ботом:</b>\n\n"
        "1️⃣ Нажми <b>Добавить мониторинг</b>\n"
        "2️⃣ Введи номер поезда, маршрут и дату\n"
        "3️⃣ Бот проверяет билеты каждую минуту\n"
        "4️⃣ Как только появятся — пришлю уведомление\n\n"
        "💳 Каждый мониторинг стоит 1 кредит.",
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

    await state.set_state(AddMonitor.waiting_train)
    await callback.message.answer(
        "🚂 <b>Шаг 1/5</b> — Введи <b>номер поезда</b>\n\n"
        "Например: <code>731Б</code> или <code>6</code>\n\n"
        "Отмена: /start",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddMonitor.waiting_train)
async def step_train(message: Message, state: FSMContext):
    await state.update_data(train_num=message.text.strip().upper())
    await state.set_state(AddMonitor.waiting_from)
    await message.answer(
        "📍 <b>Шаг 2/5</b> — Откуда едешь?\n\nНапример: <code>Минск</code>\n\nОтмена: /start",
        parse_mode="HTML",
    )


@router.message(AddMonitor.waiting_from)
async def step_from(message: Message, state: FSMContext):
    await state.update_data(from_city=message.text.strip())
    await state.set_state(AddMonitor.waiting_to)
    await message.answer(
        "📍 <b>Шаг 3/5</b> — Куда едешь?\n\nНапример: <code>Гродно</code>\n\nОтмена: /start",
        parse_mode="HTML",
    )


@router.message(AddMonitor.waiting_to)
async def step_to(message: Message, state: FSMContext):
    await state.update_data(to_city=message.text.strip())
    await state.set_state(AddMonitor.waiting_date)
    await message.answer(
        "📅 <b>Шаг 4/5</b> — Дата отправления?\n\nФормат: <code>ДД.ММ.ГГГГ</code>\nНапример: <code>15.06.2026</code>\n\nОтмена: /start",
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
    await state.set_state(AddMonitor.waiting_wagon)

    kb = InlineKeyboardBuilder()
    kb.button(text="🎯 Любое место",  callback_data="wagon_Любое")
    kb.button(text="СВ (люкс)",       callback_data="wagon_СВ")
    kb.button(text="К (купе)",        callback_data="wagon_К")
    kb.button(text="П (плацкарт)",    callback_data="wagon_П")
    kb.button(text="О (общий)",       callback_data="wagon_О")
    kb.button(text="С (сидячий)",     callback_data="wagon_С")
    kb.adjust(1, 2, 2, 2)

    await message.answer(
        "💺 <b>Шаг 5/5</b> — Тип вагона:",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("wagon_"), AddMonitor.waiting_wagon)
async def step_wagon(callback: CallbackQuery, state: FSMContext):
    wagon_type = callback.data.replace("wagon_", "")
    data = await state.get_data()

    if not data.get("train_num"):
        await state.clear()
        await callback.message.answer("⚠️ Что-то пошло не так. Нажми /start и попробуй снова.")
        await callback.answer()
        return

    # Сообщаем что проверяем
    await callback.message.answer("🔍 Проверяю поезд на rw.by, подожди...")
    await callback.answer()

    # Валидация — реально ли существует такой поезд
    from checker import check_tickets
    result = await check_tickets(
        train_num=data["train_num"],
        from_city=data["from_city"],
        to_city=data["to_city"],
        date=data["date"],
        wagon_type=wagon_type,
    )

    # Если поезд вообще не найден на странице — ошибка
    if result.get("error") == "not_found":
        await state.clear()
        await callback.message.answer(
            f"❌ <b>Поезд не найден</b>\n\n"
            f"Поезд <b>{data['train_num']}</b> по маршруту "
            f"{data['from_city']} → {data['to_city']} на {data['date']} не существует.\n\n"
            f"Проверь данные на rw.by и попробуй снова.",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
        return

    # Поезд найден — создаём мониторинг
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
    status = "🟡 Мест пока нет, слежу..." if not result.get("available") else "🟢 Уже есть места!"

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
    
    await callback.answer()


# ─── МОИ МОНИТОРИНГИ ─────────────────────────────────────────

@router.callback_query(F.data == "my_monitors")
async def cb_my_monitors(callback: CallbackQuery):
    monitors = await get_user_monitors(callback.from_user.id)

    if not monitors:
        await callback.message.answer(
            "📋 У тебя пока нет активных мониторингов.",
            reply_markup=main_menu_kb(),
        )
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
    await callback.message.answer(
        f"💳 <b>Твой баланс:</b> {credits} мониторингов\n\nЧтобы пополнить — напиши администратору.",
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
    await message.answer(
        f"📊 <b>Статистика:</b>\n\nАктивных мониторингов: <b>{len(monitors)}</b>",
        parse_mode="HTML",
    )
