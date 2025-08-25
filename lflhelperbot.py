import telebot
import config
import lflparser
import smtplib
import re
import sqlite3
import uuid
from datetime import datetime
from unidecode import unidecode
from telebot import types
from yookassa import Configuration, Payment

bot = telebot.TeleBot(config.TOKEN)

Configuration.account_id = config.SHOP_ID
Configuration.secret_key = config.YK_API_KEY

user_states = {}
users_waiting_for_payment = {}

def is_subscription_active(username):
    """
    Проверяет, активна ли подписка пользователя, и при необходимости деактивирует её, если срок истёк.

    :param username: Имя пользователя (Telegram username)
    :return: True, если подписка активна, иначе False
    """
    connection = sqlite3.connect('users.db')
    cursor = connection.cursor()

    # Получаем статус подписки и дату окончания
    cursor.execute("SELECT subscription_active, subscription_duration FROM Users WHERE username = ?", (username,))
    result = cursor.fetchone()
    connection.close()

    if result is None:
        return False  # Пользователь не найден

    active, duration_str = result

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

    # Обновление поля subscription_duration
    cursor.execute('''
            UPDATE Users 
            SET subscription_duration = ?
            WHERE username = ?
        ''', ('', 'stanislausvonscheinfein'))

    # Проверка, сколько строк было обновлено
    rows_affected = cursor.rowcount
    connection.commit()
    connection.close()

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

    if message.from_user.username:
        # Проверяем, существует ли пользователь с таким username
        cursor.execute('SELECT * FROM Users WHERE username = ?', (message.from_user.username,))
        existing_user = cursor.fetchone()

        if existing_user is None:
            # Добавляем нового пользователя с начальными значениями
            cursor.execute('''
            INSERT INTO Users (username, subscription_active, subscription_start_datetime, subscription_duration)
            VALUES (?, ?, ?, ?)
            ''', (message.from_user.username, 0, None, ''))

    connection.commit()
    connection.close()

    if is_subscription_active(message.from_user.username):
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
            "🚀 <b>Запускаемся! Доступ к боту всего за 1 рубль до 15 сентября 2025!</b>\n"
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

            response += f"""
        <b>Пользователь:</b> {username}
        <b>Статус подписки:</b> {active}
        <b>Дата начала:</b> {start_date}
        <b>Длительность:</b> {duration}
        {'-'*30}
            """

        # Ограничиваем длину сообщения (Telegram имеет лимит)
        if len(response) > 4096:
            response = response[:4091] + "..."

        bot.send_message(message.chat.id, response, parse_mode='html')

    except Exception as e:
        bot.reply_to(message, f"Ошибка при чтении базы данных: {str(e)}")
    finally:
        if 'connection' in locals():
            connection.close()

@bot.message_handler(commands=['help'])
def help_handler(message):
    bot.send_message(message.chat.id, 'Список команд:\n- Расписание игр\n- Желтые карточки игрока\n- Предложения и пожелания\n\nПросто отправьте одно из этих сообщений мне.')

@bot.message_handler(content_types=['text'])
def commands_handler(message):
    if message.chat.type == 'private':
        if is_subscription_active(message.from_user.username):
            if message.text == '📅 Расписание игр' or message.text == '/schedule':
                bot.send_message(message.chat.id, 'Напишите название вашей команды так, как оно приведено на сайте ЛФЛ (если возникают ошибки, попробуйте скопировать название с сайта).')
                user_states[message.chat.id] = 'waiting_for_team'

            elif message.text == '💳 Подписка' or message.text == '/subscription':
                try:
                    username = message.from_user.username
                    if not username:
                        bot.send_message(message.chat.id, "Не удалось определить ваш username в Telegram.")
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

                    response = f"<b>Информация о подписке:</b>\n<b>Пользователь:</b> {user_data[0]}\n<b>Статус:</b> {status}\n<b>Дата начала:</b> {start_date}\n<b>Дата окончания:</b> {duration}"

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
                        bot.send_message(message.chat.id, f'<b>{teams_found[i]}</b>\n\nДата: {datetime.strptime(schedules[i][0]['match_date_time'], "%Y-%m-%dT%H:%M:%S.%fZ").strftime("%d.%m.%Y, %H:%M")}\nСтадион: {schedules[i][0]['stadium_name']}\nАдрес: {schedules[i][0]['stadium_address']}\n<b>{schedules[i][0]['home_club_name']} VS {schedules[i][0]['away_club_name']}</b>', parse_mode='html')

                    elif schedules[i] != 'На сайте расписания нет.' and len(schedules[i]) == 2:
                        bot.send_message(message.chat.id, f'<b>{teams_found[i]}</b>\n\nДата: {datetime.strptime(schedules[i][0]['match_date_time'], "%Y-%m-%dT%H:%M:%S.%fZ").strftime("%d.%m.%Y, %H:%M")}\nСтадион: {schedules[i][0]['stadium_name']}\nАдрес: {schedules[i][0]['stadium_address']}\n<b>{schedules[i][0]['home_club_name']} VS {schedules[i][0]['away_club_name']}</b>\n\nДата: {datetime.strptime(schedules[i][1]['match_date_time'], "%Y-%m-%dT%H:%M:%S.%fZ").strftime("%d.%m.%Y, %H:%M")}\nСтадион: {schedules[i][1]['stadium_name']}\nАдрес: {schedules[i][1]['stadium_address']}\n<b>{schedules[i][1]['home_club_name']} VS {schedules[i][1]['away_club_name']}</b>', parse_mode='html')

                del user_states[message.chat.id]

            elif user_states.get(message.chat.id) == 'waiting_for_feedback':
                feedback = message.text
                username = message.from_user.username

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

                del user_states[message.chat.id]
                del username, feedback

            else:
                if message.text.lower() == 'привет':
                    bot.send_message(message.chat.id, f'Привет, {message.from_user.first_name}!', parse_mode='html')
                elif message.text.lower() == 'пока':
                    bot.send_message(message.chat.id, f'Пока, {message.from_user.first_name}!', parse_mode='html')
                elif message.text.lower() == 'как дела?':
                    bot.send_message(message.chat.id, 'Отлично!', parse_mode='html')
                else:
                    bot.send_message(message.chat.id, 'Я вас не понимаю. Напишите /help.')

        if not is_subscription_active(message.from_user.username):
            if message.text == '💳 Подписка' or message.text == '/subscription':
                subscription_markup = types.InlineKeyboardMarkup(row_width=1)
                buy_subscription = types.InlineKeyboardButton('Купить подписку', callback_data='buy_subscription')
                subscription_markup.add(buy_subscription)
                bot.send_message(message.chat.id, '<b>Успейте протестировать всего за 1 рубль!</b>\n\n<b>Что будет дальше?</b>\n15 сентября 2025 года стартует подписка за 899 руб. в год и 100 руб. в месяц.\n\nНажмите «Купить подписку», чтобы начать тестировать за 1 рубль! ⚽', parse_mode='html', reply_markup=subscription_markup)
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
                username = call.message.chat.username
                bot.send_message(call.message.chat.id, 'Формируем заказ...')
                payment = Payment.create({
                    "amount": {
                        "value": "1.00",
                        "currency": "RUB"
                    },
                    "confirmation": {
                        "type": "redirect",
                        "return_url": "https://t.me/footballhelperbot",
                    },
                    "capture": True,
                    "description": "Доступ за 1 рубль до 15 сентября 2025",
                }, uuid.uuid4())
                users_waiting_for_payment[call.message.chat.username] = payment.id
                bot.send_message(call.message.chat.id, f'Оплата: {payment.confirmation.confirmation_url}', parse_mode='html')
                bot.send_message(call.message.chat.id, 'Ожидание оплаты обычно занимает до 2 минут. Вам придет уведомление о том, что оплата прошла успешно.')
                print(users_waiting_for_payment[call.message.chat.username])
                while Payment.find_one(users_waiting_for_payment[call.message.chat.username]).status != 'succeeded':
                    print(Payment.find_one(users_waiting_for_payment[call.message.chat.username]).status)

                if Payment.find_one(users_waiting_for_payment[call.message.chat.username]).status == 'succeeded':
                    users_waiting_for_payment.pop(call.message.chat.username)
                    print(users_waiting_for_payment)
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
                            ''', (now, datetime.strptime("15.09.2025 00:00:00", "%d.%m.%Y %H:%M:%S").strftime('%Y-%m-%d %H:%M:%S'), username))

                        connection.commit()
                        connection.close()

                        # Уведомление пользователя об успешной активации подписки
                        bot.send_message(
                            call.message.chat.id,
                            f"✅ Подписка активирована!\n"
                            f"📅 Дата начала: {now}\n"
                            f"⏳ Длительность: до 15 сентября 2025 года 00:00\n"
                            f"Теперь вы можете использовать все функции бота!",
                            parse_mode='html'
                        )
                    except Exception as e:
                        bot.send_message(
                            call.message.chat.id,
                            f"❌ Ошибка при активации подписки: {str(e)}"
                        )

                elif payment.status == "canceled":
                    bot.send_message(call.message.chat.id, 'Оплата не удалась. Попробуйте сначала.')

    except Exception as e:
        print(repr(e))

bot.polling(non_stop=True)