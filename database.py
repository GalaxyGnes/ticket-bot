"""
БАЗА ДАННЫХ
Хранит: пользователей, их подписки, задачи мониторинга
Используем aiosqlite — асинхронная работа с SQLite
"""

import aiosqlite
import logging

DB_PATH = "bot_database.db"

async def init_db():
    """Создаёт таблицы при первом запуске"""
    async with aiosqlite.connect(DB_PATH) as db:

        # Таблица пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                full_name   TEXT,
                credits     INTEGER DEFAULT 0,   -- количество мониторингов
                is_active   INTEGER DEFAULT 1,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Таблица задач мониторинга (что конкретно отслеживать)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS monitors (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                train_num   TEXT,       -- номер поезда, например "748Б"
                from_city   TEXT,       -- откуда, например "Минск"
                to_city     TEXT,       -- куда, например "Брест"
                date        TEXT,       -- дата отправления "2025-06-15"
                wagon_type  TEXT,       -- тип вагона: "К" купе, "П" плацкарт и т.д.
                is_active   INTEGER DEFAULT 1,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        await db.commit()
        logging.info("База данных инициализирована")


# ─── ПОЛЬЗОВАТЕЛИ ────────────────────────────────────────────

async def get_or_create_user(user_id: int, username: str, full_name: str):
    """Получает пользователя или создаёт нового"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            user = await cursor.fetchone()

        if not user:
            await db.execute(
                "INSERT INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
                (user_id, username, full_name)
            )
            await db.commit()
            logging.info(f"Новый пользователь: {full_name} ({user_id})")

        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            return await cursor.fetchone()


async def get_user_credits(user_id: int) -> int:
    """Возвращает количество доступных мониторингов у пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT credits FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def add_credits(user_id: int, amount: int):
    """Добавляет кредиты пользователю (вызывается тобой как админом)"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET credits = credits + ? WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()


async def deduct_credit(user_id: int):
    """Списывает 1 кредит при создании мониторинга"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET credits = credits - 1 WHERE user_id = ? AND credits > 0",
            (user_id,)
        )
        await db.commit()


# ─── МОНИТОРИНГИ ────────────────────────────────────────────

async def create_monitor(user_id, train_num, from_city, to_city, date, wagon_type):
    """Создаёт новую задачу мониторинга"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO monitors (user_id, train_num, from_city, to_city, date, wagon_type)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, train_num, from_city, to_city, date, wagon_type))
        await db.commit()


async def get_active_monitors():
    """Возвращает все активные мониторинги (для планировщика)"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM monitors WHERE is_active = 1"
        ) as cursor:
            return await cursor.fetchall()


async def get_user_monitors(user_id: int):
    """Возвращает мониторинги конкретного пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM monitors WHERE user_id = ? AND is_active = 1",
            (user_id,)
        ) as cursor:
            return await cursor.fetchall()


async def deactivate_monitor(monitor_id: int):
    """Останавливает мониторинг (когда билет найден или пользователь отменил)"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE monitors SET is_active = 0 WHERE id = ?",
            (monitor_id,)
        )
        await db.commit()
