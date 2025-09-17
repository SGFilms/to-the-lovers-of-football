import telebot
import config
import lflparser
import smtplib
import re
import sqlite3
import uuid
import time
import random
from datetime import datetime, timedelta
from unidecode import unidecode
from telebot import types
from yookassa import Configuration, Payment

bot = telebot.TeleBot(config.TOKEN)

Configuration.account_id = config.SHOP_ID
Configuration.secret_key = config.YK_API_KEY

user_states = {}

def get_user_column(username, column_name):
    """
    Возвращает значение указанного столбца для пользователя из таблицы Users.

    :param username: Имя пользователя (Telegram username)
    :param column_name: Название столбца в таблице Users
    :return: Значение столбца или None, если пользователь не найден или произошла ошибка
    """
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    try:
        # Выполняем запрос к базе данных
        cursor.execute(f"SELECT {column_name} FROM Users WHERE username = ?", (username,))
        result = cursor.fetchone()

        # Если пользователь существует и столбец содержит значение
        if result and result[0] is not None:
            return result[0]
        else:
            return None  # Пользователь не найден или значение равно NULL

    except sqlite3.Error as e:
        print(f"Ошибка при получении значения столбца '{column_name}': {e}")
        return None

    finally:
        conn.close()

def ensure_last_payment_id_column():
    """
    Проверяет наличие столбца 'last_payment_id' в таблице 'Users'.
    Если столбца нет, добавляет его с типом TEXT и значением по умолчанию NULL.
    """
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    try:
        # Шаг 1: Проверка наличия столбца
        cursor.execute("PRAGMA table_info(Users)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'last_payment_id' not in columns:
            print("Столбец 'last_payment_id' не найден. Добавление...")

            # Шаг 2: Добавление столбца
            cursor.execute("ALTER TABLE Users ADD COLUMN last_payment_id TEXT DEFAULT NULL")
            conn.commit()
            print("Столбец 'last_payment_id' успешно добавлен.")
        else:
            print("Столбец 'last_payment_id' уже существует.")

    except sqlite3.Error as e:
        print(f"Ошибка при работе с базой данных: {e}")
    finally:
        conn.close()

def wait_for_payment_success(username, max_retries=100, initial_delay=1, max_delay=60):
    """
    Polls for payment success with exponential backoff.

    Args:
        username (str): The username to query.
        max_retries (int): Maximum number of retry attempts.
        initial_delay (int): Initial delay in seconds.
        max_delay (int): Maximum delay allowed in seconds.

    Returns:
        bool: True if payment succeeded, False if max retries reached.
    """
    retry_count = 0
    delay = initial_delay

    while retry_count < max_retries:
        try:
            payment = Payment.find_one(get_user_column(username, 'last_payment_id'))
            if payment.status == 'succeeded':
                return True
        except Exception as e:
            print(f"Error checking payment status for {username}: {e}")

        # Add jitter to avoid synchronized retries
        jitter = random.uniform(0, delay / 2)
        sleep_time = delay + jitter
        print(f"Retrying in {sleep_time:.2f} seconds...")
        time.sleep(sleep_time)

        # Exponentially increase delay, capped at max_delay
        delay = min(delay * 2, max_delay)
        retry_count += 1

    print(f"Max retries reached for {username}. Payment status not confirmed.")
    return False

def is_subscription_active(username):
    """
    Проверяет, активна ли подписка пользователя, и при необходимости деактивирует её, если срок истёк.

    :param username: Имя пользователя (Telegram username)
    :return: True, если подписка активна, иначе False
    """
    connection = sqlite3.connect('users.db')
    cursor = connection.cursor()

    # Получаем статус подписки и дату окончания
    cursor.execute("SELECT subscription_active, subscription_start_datetime, subscription_duration, last_payment_id FROM Users WHERE username = ?", (username,))
    result = cursor.fetchone()
    connection.close()

    if result is None:
        return False  # Пользователь не найден

    active, start_datetime, duration_str, last_payment_id = result

    if last_payment_id != '' or last_payment_id is not None:
        if datetime.strptime(duration_str, '%Y-%m-%d %H:%M:%S') < datetime.strptime('2025-09-30 00:00:00', '%Y-%m-%d %H:%M:%S'):
            connection = sqlite3.connect('users.db')
            cursor = connection.cursor()

            # Обновление данных пользователя
            cursor.execute('''
                                    UPDATE Users 
                                    SET 
                                        subscription_active = 1,
                                        subscription_duration = ?
                                    WHERE username = ?
                                ''', (datetime.strptime('2025-09-30 00:00:00', '%Y-%m-%d %H:%M:%S'), username))

            connection.commit()
            connection.close()
            return True


    if active != 1:
        return False  # Подписка уже неактивна

    if not duration_str:
        connection = sqlite3.connect('users.db')
        cursor = connection.cursor()
        cursor.execute("UPDATE Users SET subscription_active = 0 WHERE username = ?", (username,))
        connection.commit()
        connection.close()
        return False  # Дата окончания не указана

    try:
        # Парсим строку даты в объект datetime
        duration_dt = datetime.strptime(duration_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False  # Неверный формат даты

    current_dt = datetime.now()

    if current_dt >= duration_dt:
        # Срок действия подписки истёк
        connection = sqlite3.connect('users.db')
        cursor = connection.cursor()
        cursor.execute("UPDATE Users SET subscription_active = 0 WHERE username = ?", (username,))
        connection.commit()
        connection.close()
        return False
    else:
        return True  # Подписка всё ещё активна

@bot.message_handler(commands=['start'])
def welcome(message):
    connection = sqlite3.connect('users.db')
    cursor = connection.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Users (
    username TEXT NOT NULL,
    subscription_active INTEGER,
    subscription_start_datetime TIMESTAMP,
    subscription_duration TEXT NOT NULL
    )
    ''')

    if message.from_user.id:
        # Проверяем, существует ли пользователь с таким username
        cursor.execute('SELECT * FROM Users WHERE username = ?', (message.from_user.id,))
        existing_user = cursor.fetchone()

        if existing_user is None:
            # Добавляем нового пользователя с начальными значениями
            cursor.execute('''
            INSERT INTO Users (username, subscription_active, subscription_start_datetime, subscription_duration)
            VALUES (?, ?, ?, ?)
            ''', (message.from_user.id, 0, None, ''))

    connection.commit()
    connection.close()

    if is_subscription_active(message.from_user.id):
        connection = sqlite3.connect('users.db')
        cursor = connection.cursor()
        cursor.execute("SELECT subscription_start_datetime, subscription_duration FROM Users WHERE username = ?", (message.from_user.id,))
        result = cursor.fetchone()

        sub_start, sub_duration = result

        duration_dt = datetime.strptime(sub_duration, "%Y-%m-%d %H:%M:%S")
        start_dt = datetime.strptime(sub_start, "%Y-%m-%d %H:%M:%S")

        if duration_dt - start_dt < timedelta(days=30):
            cursor.execute(f"UPDATE Users SET subscription_duration = ? WHERE username = ?", ((start_dt + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S'), message.from_user.id,))
            connection.commit()
            connection.close()
        else:
            connection.close()


    if is_subscription_active(message.from_user.id):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        item1 = types.KeyboardButton("📅 Расписание игр")
        item2 = types.KeyboardButton("💳 Подписка")
        item3 = types.KeyboardButton("📮 Отзывы и предложения")
        markup.add(item1, item2, item3)

        bot.send_message(
            message.chat.id,
            f"Добро пожаловать, {message.from_user.first_name}!\n"
            "Выберите одну из опций меню.",
            parse_mode='html',
            reply_markup=markup
        )

    else:
        subscription_markup = types.InlineKeyboardMarkup(row_width=1)
        buy_subscription = types.InlineKeyboardButton('Купить подписку', callback_data='buy_subscription')
        subscription_markup.add(buy_subscription)
        bot.send_message(
            message.chat.id,
            f"Добро пожаловать, {message.from_user.first_name}!\n"
            "🚀 <b>Запускаемся! Доступ к боту на месяц всего за 1 рубль до 30 сентября 2025!</b>\n"
            "Я бот-помощник, позволяющий вам быстро и удобно найти нужную информацию с сайта Любительской Футбольной Лиги.\n"
            "Похоже, что у вас еще нет подписки. Нажмите «Купить подписку», чтобы начать тестировать! ⚽\n",
            parse_mode='html',
            reply_markup=subscription_markup
        )

@bot.message_handler(commands=['admin_feature_view_users_database'])
def view_users(message):
    try:
        connection = sqlite3.connect('users.db')
        cursor = connection.cursor()

        # Получаем все записи из таблицы
        cursor.execute("SELECT * FROM Users")
        users = cursor.fetchall()

        if not users:
            bot.reply_to(message, "База данных пуста")
            return

        # Формируем ответ в читаемом виде
        response = "<b>Содержимое базы данных:</b>\n\n"
        for user in users:
            username = user[0]
            active = user[1]
            start_date = user[2]
            duration = user[3]
            last_payment_id = user[4]

            response += f"""
        <b>Пользователь:</b> {username}
        <b>Статус подписки:</b> {active}
        <b>Дата начала:</b> {start_date}
        <b>Длительность:</b> {duration}
        <b>Последний ID платежа:</b> {last_payment_id}
        {'-'*30}
            """

        # Ограничиваем длину сообщения (Telegram имеет лимит)
        if len(response) > 4096:
            response = response[:4091] + "..."

        bot.send_message(message.chat.id, response, parse_mode='html')
        connection.close()
    except Exception as e:
        bot.reply_to(message, f"Ошибка при чтении базы данных: {str(e)}")

@bot.message_handler(commands=['help'])
def help_handler(message):
    bot.send_message(message.chat.id, 'Список команд:\n- Расписание игр\n- Желтые карточки игрока\n- Предложения и пожелания\n\nПросто отправьте одно из этих сообщений мне.')

@bot.message_handler(content_types=['text'])
def commands_handler(message):
    if message.chat.type == 'private':
        if is_subscription_active(message.from_user.id):
            if message.text == '📅 Расписание игр' or message.text == '/schedule':
                bot.send_message(message.chat.id, 'Напишите название вашей команды так, как оно приведено на сайте ЛФЛ (если возникают ошибки, попробуйте скопировать название с сайта).')
                user_states[message.chat.id] = 'waiting_for_team'

            elif message.text == '💳 Подписка' or message.text == '/subscription':
                try:
                    username = message.from_user.id
                    if not username:
                        bot.send_message(message.chat.id, "Не удалось определить ваш id в Telegram.")
                        return

                    connection = sqlite3.connect('users.db')
                    cursor = connection.cursor()

                    # Получаем данные пользователя
                    cursor.execute('''
                    SELECT 
                        username,
                        subscription_active,
                        subscription_start_datetime,
                        subscription_duration
                    FROM Users 
                    WHERE username = ?
                    ''', (username,))

                    user_data = cursor.fetchone()
                    connection.close()

                    if not user_data:
                        bot.reply_to(message, "Ваша запись в базе данных не найдена")
                        return

                    # Формируем ответ
                    status = "✅ Активна" if user_data[1] else "❌ Не активна"
                    start_date = user_data[2] if user_data[2] else "Не задана"
                    duration = user_data[3] if user_data[3] else "Не указана"

                    response = f"<b>Информация о подписке:</b>\n<b>Пользователь:</b> {user_data[0]}\n<b>Статус:</b> {status}\n<b>Дата начала:</b> {datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M:%S")}\n<b>Дата окончания:</b> {datetime.strptime(duration, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M:%S")}"

                    bot.send_message(message.chat.id, response, parse_mode='html')

                except Exception as e:
                    bot.reply_to(message, f"Ошибка при получении информации: {str(e)}")

            elif message.text == '📮 Отзывы и предложения' or message.text == '/feedback':
                bot.send_message(message.chat.id, 'Спасибо, что хотите помочь нам стать лучше! 😊 Пожалуйста, опишите ваши впечатления, идею или проблему. Мы читаем каждое сообщение.')
                user_states[message.chat.id] = 'waiting_for_feedback'

            elif user_states.get(message.chat.id) == 'waiting_for_team':
                team = message.text
                bot.send_message(message.chat.id, f'Найдено {len(lflparser.get_team_code(team))} команд. Ищу расписания...', parse_mode='html')
                schedules = lflparser.get_schedule(team)[1]
                teams_found = lflparser.get_schedule(team)[0]
                for i in range(len(teams_found)):
                    if schedules[i] == 'На сайте расписания нет.':
                        bot.send_message(message.chat.id, f'<b>{teams_found[i]}</b>\n\nНа сайте расписания нет.', parse_mode='html')

                    elif schedules[i] != 'На сайте расписания нет.' and len(schedules[i]) == 1:
                        bot.send_message(message.chat.id, f'<b>{teams_found[i]}</b>\n\nДата: {(datetime.strptime(schedules[i][0]['match_date_time'], "%Y-%m-%dT%H:%M:%S.%fZ") + timedelta(hours=3)).strftime("%d.%m.%Y, %H:%M")}\nСтадион: {schedules[i][0]['stadium_name']}\nАдрес: {schedules[i][0]['stadium_address']}\n<b>{schedules[i][0]['home_club_name']} VS {schedules[i][0]['away_club_name']}</b>', parse_mode='html')

                    elif schedules[i] != 'На сайте расписания нет.' and len(schedules[i]) == 2:
                        bot.send_message(message.chat.id, f'<b>{teams_found[i]}</b>\n\nДата: {(datetime.strptime(schedules[i][0]['match_date_time'], "%Y-%m-%dT%H:%M:%S.%fZ") + timedelta(hours=3)).strftime("%d.%m.%Y, %H:%M")}\nСтадион: {schedules[i][0]['stadium_name']}\nАдрес: {schedules[i][0]['stadium_address']}\n<b>{schedules[i][0]['home_club_name']} VS {schedules[i][0]['away_club_name']}</b>\n\nДата: {(datetime.strptime(schedules[i][1]['match_date_time'], "%Y-%m-%dT%H:%M:%S.%fZ") + timedelta(hours=3)).strftime("%d.%m.%Y, %H:%M")}\nСтадион: {schedules[i][1]['stadium_name']}\nАдрес: {schedules[i][1]['stadium_address']}\n<b>{schedules[i][1]['home_club_name']} VS {schedules[i][1]['away_club_name']}</b>', parse_mode='html')
                try:
                    del user_states[message.chat.id]
                except Exception as e:
                    pass

            elif user_states.get(message.chat.id) == 'waiting_for_feedback':
                feedback = message.text
                username = message.from_user.id

                def transliterate(feedback, username):
                    username_result = username
                    feedback_result = feedback
                    if re.search(r'[^\x00-\x7F]', feedback):
                        feedback_result = unidecode(feedback)
                    if re.search(r'[^\x00-\x7F]', username):
                        username_result = unidecode(username)
                    return username_result, feedback_result

                smtp_obj = smtplib.SMTP('smtp.mail.ru', 587)
                smtp_obj.starttls()
                smtp_obj.login('stas.golovanov.07@mail.ru','M1qvmiFTuBM7n1Yr3dJg')
                smtp_obj.sendmail("stas.golovanov.07@mail.ru","tothefootballers@gmail.com",f"From user:\n{transliterate(feedback, username)[0]}\n\nMessage:\n{transliterate(feedback, username)[1]}")
                smtp_obj.quit()

                bot.send_message(message.chat.id, 'Спасибо за ваш отзыв! Мы его получили 😊')
                try:
                    del user_states[username]
                    del username, feedback
                except Exception as e:
                    pass

            else:
                if message.text.lower() == 'привет':
                    bot.send_message(message.chat.id, f'Привет, {message.from_user.first_name}!', parse_mode='html')
                elif message.text.lower() == 'пока':
                    bot.send_message(message.chat.id, f'Пока, {message.from_user.first_name}!', parse_mode='html')
                elif message.text.lower() == 'как дела?':
                    bot.send_message(message.chat.id, 'Отлично!', parse_mode='html')
                else:
                    bot.send_message(message.chat.id, 'Я вас не понимаю. Напишите /help.')

        if not is_subscription_active(message.from_user.id):
            if message.text == '💳 Подписка' or message.text == '/subscription':
                subscription_markup = types.InlineKeyboardMarkup(row_width=1)
                buy_subscription = types.InlineKeyboardButton('Купить подписку', callback_data='buy_subscription')
                subscription_markup.add(buy_subscription)
                bot.send_message(message.chat.id, '<b>Успейте протестировать всего за 1 рубль!</b>\n\n<b>Что будет дальше?</b>\n30 сентября 2025 года стартует подписка за 899 руб. в год и 100 руб. в месяц.\n\nНажмите «Купить подписку», чтобы получить доступ на месяц за 1 рубль! ⚽', parse_mode='html', reply_markup=subscription_markup)

            elif user_states.get(message.chat.id) == 'waiting_for_email':
                email = message.text
                username = message.from_user.id
                bot.send_message(message.chat.id, 'Формируем заказ...')
                payment = Payment.create({
                    "amount": {
                        "value": "1.00",
                        "currency": "RUB"
                    },
                    "capture": True,
                    "confirmation": {
                        "type": "redirect",
                        "return_url": "https://t.me/football_amateur_bot"
                    },
                    "description": "Подписка на бота",
                    "receipt": {
                        "customer": {
                            "email": f"{email}",
                        },
                        "items": [
                            {
                                "description": "Доступ к боту за 1 рубль до 15 сентября 2025 года",
                                "quantity": 1,
                                "amount": {
                                    "value": "1.00",
                                    "currency": "RUB"
                                },
                                "vat_code": 1
                            }
                        ]
                    }
                }, uuid.uuid4())

                ensure_last_payment_id_column()

                conn = sqlite3.connect('users.db')
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE Users 
                    SET last_payment_id = ? 
                    WHERE username = ?
                """, (payment.id, username))

                conn.commit()
                conn.close() # Сохраняем ID платежа для дальнейшего использования В БАЗУ ДАННЫХ

                bot.send_message(message.chat.id, f'Оплата: {payment.confirmation.confirmation_url}', parse_mode='html')
                bot.send_message(message.chat.id, 'Ожидание оплаты обычно занимает до 2 минут. Вам придет уведомление о том, что оплата прошла успешно. Если ничего не произойдет, введите команду /start.')

                if wait_for_payment_success(message.from_user.id):
                    try:
                        # Подключение к базе данных
                        connection = sqlite3.connect('users.db')
                        cursor = connection.cursor()

                        # Получение текущей даты и времени в формате ISO
                        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                        # Обновление данных пользователя
                        cursor.execute('''
                                UPDATE Users 
                                SET 
                                    subscription_active = 1,
                                    subscription_start_datetime = ?,
                                    subscription_duration = ?
                                WHERE username = ?
                            ''', (now, (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S'), username))

                        connection.commit()
                        connection.close()

                        # Уведомление пользователя об успешной активации подписки
                        bot.send_message(
                            message.chat.id,
                            f"✅ Подписка активирована!\n"
                            f"📅 Дата начала: {datetime.strptime(now, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M:%S")}\n"
                            f"⏳ Длительность: до 15 сентября 2025 года 00:00\n"
                            f"Теперь вы можете использовать все функции бота!",
                            parse_mode='html'
                        )
                    except Exception as e:
                        bot.send_message(
                            message.chat.id,
                            f"❌ Ошибка при активации подписки: {str(e)}"
                        )

                elif Payment.find_one(get_user_column(message.from_user.id, 'last_payment_id')).status == "canceled":
                    bot.send_message(message.chat.id, 'Оплата не удалась. Попробуйте сначала.')

            else:
                subscription_markup = types.InlineKeyboardMarkup(row_width=1)
                buy_subscription = types.InlineKeyboardButton('Купить подписку', callback_data='buy_subscription')
                subscription_markup.add(buy_subscription)
                bot.send_message(
                    message.chat.id,
                    f"Похоже, что у вас еще нет подписки. Нажмите «Купить подписку», чтобы начать тестировать! ⚽\n",
                    parse_mode='html',
                    reply_markup=subscription_markup
                )

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    try:
        if call.message:
            if call.data == 'buy_subscription':
                bot.send_message(call.message.chat.id, 'Пожалуйста, напишите вашу электронную почту (мы ее не храним, она нужна только для проведения платежа).')
                user_states[call.message.chat.id] = 'waiting_for_email'

    except Exception as e:
        print(repr(e))

bot.polling(non_stop=True)