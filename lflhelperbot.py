import asyncio
import logging
import uuid
import smtplib
import re
from datetime import datetime, timedelta
from email.mime.text import MIMEText

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from yookassa import Configuration, Payment
from unidecode import unidecode

import config
import lflparser
import database as db

# --- Конфигурация ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Инициализация YooKassa
Configuration.account_id = config.SHOP_ID
Configuration.secret_key = config.YK_API_KEY

# Инициализация бота и диспетчера
bot = Bot(token=config.TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- Состояния (FSM) ---
class BotStates(StatesGroup):
    waiting_for_team = State()
    waiting_for_feedback = State()
    waiting_for_email = State()

# --- Клавиатуры ---
def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📅 Расписание игр")
    builder.button(text="💳 Подписка")
    builder.button(text="📮 Отзывы и предложения")
    builder.adjust(1) # Кнопки в столбик
    return builder.as_markup(resize_keyboard=True)

def get_sub_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Купить подписку', callback_data='buy_subscription')]
    ])
    return keyboard

# --- Вспомогательные функции ---

async def send_email_async(subject, body):
    """Асинхронная обертка для отправки почты"""
    def _send():
        try:
            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = config.SMTP_USER
            msg['To'] = config.TARGET_EMAIL

            with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
                server.starttls()
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                server.send_message(msg)
            return True
        except Exception as e:
            logger.error(f"Email error: {e}")
            return False

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _send)

async def check_payment_task(user_id, payment_id, chat_id):
    """Фоновая задача проверки оплаты. Не блокирует бота."""
    retries = 0
    max_retries = 60  # 60 попыток по 2-5 секунд = ~3-5 минут ожидания
    delay = 2

    while retries < max_retries:
        try:
            # Получаем статус платежа (синхронный вызов ЮКассы оборачиваем в поток, если нужно, но он быстрый)
            # Для идеальной асинхронности лучше использовать HTTP клиент, но пока оставим SDK
            payment = Payment.find_one(payment_id)

            if payment.status == 'succeeded':
                # Активация
                start, end = await db.activate_subscription(str(user_id))

                await bot.send_message(
                    chat_id,
                    f"✅ <b>Подписка успешно активирована!</b>\n"
                    f"📅 Дата начала: {start.strftime('%d.%m.%Y %H:%M')}\n"
                    f"⏳ Длительность: до {end.strftime('%d.%m.%Y %H:%M')}\n"
                    f"Теперь вы можете использовать все функции бота!",
                    parse_mode='html',
                    reply_markup=get_main_keyboard()
                )
                return

            elif payment.status == 'canceled':
                await bot.send_message(chat_id, "❌ Оплата была отменена.")
                return

        except Exception as e:
            logger.error(f"Payment check error: {e}")

        await asyncio.sleep(delay)
        # Небольшое увеличение интервала (backoff)
        if delay < 10:
            delay += 1
        retries += 1

    await bot.send_message(chat_id, "⚠️ Мы не получили подтверждение оплаты. Если деньги списались, напишите администратору.")

# --- Хендлеры ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = str(message.from_user.id)
    await db.add_user(user_id)

    is_active = await db.check_subscription(user_id)

    if is_active:
        await message.answer(
            f"Добро пожаловать, {message.from_user.first_name}!\nВыберите опцию в меню.",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer(
            f"Добро пожаловать, {message.from_user.first_name}!\n"
            "🚀 <b>Запускаемся! Доступ к боту на месяц всего за 1 рубль!</b>\n\n"
            "Нажмите «Купить подписку», чтобы начать! ⚽",
            parse_mode='html',
            reply_markup=get_sub_keyboard()
        )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer('Список команд:\n- /schedule (или кнопка)\n- /subscription (или кнопка)\n- /feedback (или кнопка)')

@dp.message(Command("admin_db"))
async def admin_view_db(message: types.Message):
    # Тут лучше добавить проверку на ID администратора
    # if message.from_user.id != ADMIN_ID: return
    try:
        users = await db.get_all_users()
        if not users:
            await message.answer("База пуста.")
            return

        response = "<b>БД:</b>\n\n"
        for user in users:
            line = f"ID: {user['username']} | Sub: {user['subscription_active']} | Until: {user['subscription_duration']}\n"
            if len(response) + len(line) > 4000:
                await message.answer(response, parse_mode='html')
                response = ""
            response += line

        await message.answer(response, parse_mode='html')
    except Exception as e:
        await message.answer(f"Error: {e}")

# -- Обработка текстовых кнопок меню (только для подписчиков) --

@dp.message(F.text == "📅 Расписание игр")
@dp.message(Command("schedule"))
async def schedule_handler(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    if not await db.check_subscription(user_id):
        await message.answer("У вас нет активной подписки.", reply_markup=get_sub_keyboard())
        return

    await message.answer("Напишите название вашей команды (как на сайте ЛФЛ):")
    await state.set_state(BotStates.waiting_for_team)

@dp.message(F.text == "💳 Подписка")
@dp.message(Command("subscription"))
async def subscription_handler(message: types.Message):
    user_id = str(message.from_user.id)
    user_data = await db.get_user_data(user_id)

    if not user_data:
        await message.answer("Ошибка пользователя.")
        return

    is_active = await db.check_subscription(user_id)
    status_text = "✅ Активна" if is_active else "❌ Не активна"

    # Красивое форматирование дат
    try:
        start_d = datetime.strptime(user_data['subscription_start_datetime'], "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y") if user_data['subscription_start_datetime'] else "-"
        end_d = datetime.strptime(user_data['subscription_duration'], "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y") if user_data['subscription_duration'] else "-"
    except:
        start_d, end_d = "-", "-"

    text = (f"<b>Информация о подписке:</b>\n"
            f"Статус: {status_text}\n"
            f"Начало: {start_d}\n"
            f"Окончание: {end_d}")

    keyboard = None if is_active else get_sub_keyboard()
    await message.answer(text, parse_mode='html', reply_markup=keyboard)

@dp.message(F.text == "📮 Отзывы и предложения")
@dp.message(Command("feedback"))
async def feedback_handler(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    if not await db.check_subscription(user_id):
        await message.answer("Функция доступна только подписчикам.", reply_markup=get_sub_keyboard())
        return

    await message.answer("Напишите ваш отзыв или предложение:")
    await state.set_state(BotStates.waiting_for_feedback)

# -- Машина состояний (обработка ввода) --

@dp.message(BotStates.waiting_for_team)
async def process_team_name(message: types.Message, state: FSMContext):
    team_name = message.text
    await message.answer(f"Ищу расписание для команды: <b>{team_name}</b>...", parse_mode='html')

    # Вызов асинхронного парсера
    teams, schedules = await lflparser.get_schedule(team_name)

    if not teams:
        await message.answer("Команды не найдены или ошибка соединения с сайтом ЛФЛ.")
    else:
        await message.answer(f"Найдено команд: {len(teams)}")
        for i, team_found in enumerate(teams):
            match_info = schedules[i]
            if isinstance(match_info, str): # "На сайте расписания нет"
                await message.answer(f"<b>{team_found}</b>\n\n{match_info}", parse_mode='html')
            else:
                msg_text = f"<b>{team_found}</b>\n\n"
                for match in match_info:
                    try:
                        dt = datetime.strptime(match['match_date_time'], "%Y-%m-%dT%H:%M:%S.%fZ") + timedelta(hours=3)
                        fmt_dt = dt.strftime("%d.%m.%Y, %H:%M")
                    except:
                        fmt_dt = match['match_date_time']

                    msg_text += (f"📅 {fmt_dt}\n"
                                 f"🏟 {match['stadium_name']} ({match['stadium_address']})\n"
                                 f"⚽ <b>{match['home_club_name']} 🆚 {match['away_club_name']}</b>\n\n")

                await message.answer(msg_text, parse_mode='html')

    await state.clear()

@dp.message(BotStates.waiting_for_feedback)
async def process_feedback(message: types.Message, state: FSMContext):
    feedback = message.text
    username = message.from_user.username or message.from_user.first_name

    # Транслитерация для безопасности email заголовков
    clean_feedback = unidecode(feedback) if not re.match(r'^[\x00-\x7F]+$', feedback) else feedback

    await send_email_async(
        f"Feedback from {username}",
        f"User ID: {message.from_user.id}\nOriginal: {feedback}\nTranslit: {clean_feedback}"
    )

    await message.answer("Спасибо! Мы получили ваш отзыв.")
    await state.clear()

# -- Оплата --

@dp.callback_query(F.data == "buy_subscription")
async def start_payment(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Пожалуйста, введите ваш Email для чека:")
    await state.set_state(BotStates.waiting_for_email)
    await call.answer()

@dp.message(BotStates.waiting_for_email)
async def process_email(message: types.Message, state: FSMContext):
    email = message.text
    user_id = str(message.from_user.id)

    msg = await message.answer("Формируем счет на оплату...")

    try:
        # Создание платежа (синхронное, но быстрое действие SDK)
        payment = Payment.create({
            "amount": {"value": "1.00", "currency": "RUB"},
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": "https://t.me/football_amateur_bot"
            },
            "description": f"Подписка для {user_id}",
            "receipt": {
                "customer": {"email": email},
                "items": [{
                    "description": "Доступ к боту",
                    "quantity": 1,
                    "amount": {"value": "1.00", "currency": "RUB"},
                    "vat_code": 1
                }]
            }
        }, uuid.uuid4())

        await db.update_payment_id(user_id, payment.id)

        await msg.edit_text(
            f"Ссылка на оплату: {payment.confirmation.confirmation_url}\n\n"
            f"После оплаты бот <b>автоматически</b> активирует подписку в течение 1-2 минут.\n"
            f"Ничего нажимать не нужно.",
            parse_mode='html'
        )

        # ЗАПУСК ФОНОВОЙ ЗАДАЧИ ПРОВЕРКИ
        asyncio.create_task(check_payment_task(user_id, payment.id, message.chat.id))

    except Exception as e:
        logger.error(f"Payment error: {e}")
        await message.answer("Ошибка при создании платежа. Попробуйте позже.")

    await state.clear()

# -- Запуск --
async def main():
    # Создаем таблицы при старте
    await db.init_db()

    # Удаляем вебхук и запускаем поллинг
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot started...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")