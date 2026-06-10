"""
БАЗА ДАННЫХ
Хранит: пользователей, их подписки, задачи мониторинга
Используем aiosqlite — асинхронная работа с SQLite
"""

import aiosqlite
import logging

import os
DB_PATH = os.getenv("DB_PATH", "/data/bot_database.db")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                full_name   TEXT,
                credits     INTEGER DEFAULT 0,
                is_active   INTEGER DEFAULT 1,
                referred_by INTEGER DEFAULT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS monitors (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                train_num   TEXT,
                from_city   TEXT,
                to_city     TEXT,
                date        TEXT,
                wagon_type  TEXT,
                is_active   INTEGER DEFAULT 1,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        # Добавляем колонку если её ещё нет (для старых баз данных)
        try:
            await db.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER DEFAULT NULL")
        except Exception:
            pass  # колонка уже есть
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

async def deactivate_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (user_id,))
        await db.commit()
        logging.info(f"Пользователь {user_id} деактивирован")

async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, full_name, username, credits FROM users WHERE is_active = 1 ORDER BY created_at DESC"
        ) as cursor:
            return await cursor.fetchall()


async def deactivate_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (user_id,))
        await db.commit()
        logging.info(f"Пользователь {user_id} деактивирован")

async def get_user_by_ref(ref_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (ref_id,)
        ) as cursor:
            return await cursor.fetchone()


async def get_user_referrals(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0        
