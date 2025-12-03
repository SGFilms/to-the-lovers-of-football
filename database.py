import aiosqlite
import config
from datetime import datetime, timedelta

async def init_db():
    async with aiosqlite.connect(config.DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS Users (
                username TEXT PRIMARY KEY,
                subscription_active INTEGER DEFAULT 0,
                subscription_start_datetime TIMESTAMP,
                subscription_duration TEXT,
                last_payment_id TEXT DEFAULT NULL
            )
        ''')
        await db.commit()

async def add_user(username):
    async with aiosqlite.connect(config.DB_NAME) as db:
        async with db.execute('SELECT username FROM Users WHERE username = ?', (username,)) as cursor:
            if not await cursor.fetchone():
                await db.execute('''
                    INSERT INTO Users (username, subscription_active, subscription_start_datetime, subscription_duration)
                    VALUES (?, 0, NULL, '')
                ''', (username,))
                await db.commit()

async def get_user_data(username):
    async with aiosqlite.connect(config.DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM Users WHERE username = ?', (username,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

async def update_payment_id(username, payment_id):
    async with aiosqlite.connect(config.DB_NAME) as db:
        await db.execute('UPDATE Users SET last_payment_id = ? WHERE username = ?', (payment_id, username))
        await db.commit()

async def activate_subscription(username, duration_days=30):
    now = datetime.now()
    end_date = now + timedelta(days=duration_days)
    # Хардкод даты из твоего старого кода (до 15 сент 2025), можно заменить на динамику
    fixed_end_date = datetime(2025, 9, 15, 0, 0, 0)

    # Используем фиксированную дату как в оригинале, или динамическую, если нужно
    final_end_date = fixed_end_date # Или end_date, если хочешь честные 30 дней

    async with aiosqlite.connect(config.DB_NAME) as db:
        await db.execute('''
            UPDATE Users 
            SET subscription_active = 1,
                subscription_start_datetime = ?,
                subscription_duration = ?
            WHERE username = ?
        ''', (now.strftime('%Y-%m-%d %H:%M:%S'), final_end_date.strftime('%Y-%m-%d %H:%M:%S'), username))
        await db.commit()
    return now, final_end_date

async def check_subscription(username):
    """Возвращает True, если подписка активна, иначе False. Также обновляет статус если истекла."""
    data = await get_user_data(username)
    if not data:
        return False

    # Логика с "вечной" подпиской до 2025 года из твоего кода
    # Если была оплата и дата меньше 30 сент 2025 - обновляем (логика сохранена)
    if data['last_payment_id']:
        limit_date = datetime(2025, 9, 30)
        try:
            current_duration = datetime.strptime(data['subscription_duration'], '%Y-%m-%d %H:%M:%S')
            if current_duration < limit_date:
                async with aiosqlite.connect(config.DB_NAME) as db:
                    await db.execute('UPDATE Users SET subscription_active = 1, subscription_duration = ? WHERE username = ?',
                                     (limit_date.strftime('%Y-%m-%d %H:%M:%S'), username))
                    await db.commit()
                return True
        except (ValueError, TypeError):
            pass

    if not data['subscription_active']:
        return False

    if not data['subscription_duration']:
        return False

    try:
        duration_dt = datetime.strptime(data['subscription_duration'], "%Y-%m-%d %H:%M:%S")
        if datetime.now() >= duration_dt:
            async with aiosqlite.connect(config.DB_NAME) as db:
                await db.execute("UPDATE Users SET subscription_active = 0 WHERE username = ?", (username,))
                await db.commit()
            return False
        return True
    except ValueError:
        return False

async def get_all_users():
    async with aiosqlite.connect(config.DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM Users") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]