import telebot
import config
import lflparser
from telebot import types

bot = telebot.TeleBot(config.TOKEN)

user_states = {}

@bot.message_handler(commands=['start'])
def welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = types.KeyboardButton("Расписание игр")
    item2 = types.KeyboardButton("Подписка")
    item3 = types.KeyboardButton("Отзывы и предложения")
    markup.add(item1, item2, item3)

    bot.send_message(
        message.chat.id,
        f"Добро пожаловать, {message.from_user.first_name}!\n"
        "🚀 <b>Запускаемся! Доступ к боту всего за 1 рубль до 31 августа 2025!</b>\n"
        "Я бот-помощник, позволяющий вам быстро и удобно найти нужную информацию с сайта Любительской Футбольной Лиги.\n"
        "Выберите одну из опций.",
        parse_mode='html',
        reply_markup=markup
    )

@bot.message_handler(commands=['help'])
def help_handler(message):
    bot.send_message(message.chat.id, 'Список команд:\n- Расписание игр\n- Желтые карточки игрока\n- Предложения и пожелания\n\nПросто отправьте одно из этих сообщений мне.')

@bot.message_handler(content_types=['text'])
def commands_handler(message):
    if message.chat.type == 'private':
        if message.text == 'Расписание игр' or message.text == '/schedule':
            bot.send_message(message.chat.id, 'Напишите название вашей команды так, как оно приведено на сайте ЛФЛ (если возникают ошибки, попробуйте скопировать название с сайта).')
            user_states[message.chat.id] = 'waiting_for_team'

        elif message.text == 'Подписка' or message.text == '/subscription':
            subscription_markup = types.InlineKeyboardMarkup(row_width=1)
            buy_subscription = types.InlineKeyboardButton('Купить подписку', callback_data='buy_subscription')
            subscription_markup.add(buy_subscription)
            bot.send_message(message.chat.id, '<b>Успейте протестировать всего за 1 рубль!</b>\n\n<b>Что будет дальше?</b>\n31 августа стартует годовая подписка за 899 руб. или 100 руб. в месяц.\n\nНажмите «Купить подписку», чтобы начать тестировать! ⚽', parse_mode='html', reply_markup=subscription_markup)

        elif message.text == 'Отзывы и предложения' or message.text == '/feedback':
            bot.send_message(message.chat.id, 'Отзывы и предложения')

        elif user_states.get(message.chat.id) == 'waiting_for_team':
            team = message.text
            bot.send_message(message.chat.id, f'Найдено {len(lflparser.get_team_code(team))} команд.')
            schedules = lflparser.get_schedule(team)[1]
            teams_found = lflparser.get_schedule(team)[0]
            for i in range(len(teams_found)):
                if schedules[i] == 'На сайте расписания нет.':
                    bot.send_message(message.chat.id, f'<b>{teams_found[i]}</b>\n\nНа сайте расписания нет.', parse_mode='html')

                elif schedules[i] != 'На сайте расписания нет.' and len(schedules[i]) == 1:
                    bot.send_message(message.chat.id, f'<b>{teams_found[i]}</b>\n\nДата: {schedules[i][0]['match_date_time']}\nСтадион: {schedules[i][0]['stadium_name']}\nАдрес: {schedules[i][0]['stadium_address']}\n<b>{schedules[i][0]['home_club_name']} VS {schedules[i][0]['away_club_name']}</b>', parse_mode='html')

                elif schedules[i] != 'На сайте расписания нет.' and len(schedules[i]) == 2:
                    bot.send_message(message.chat.id, f'<b>{teams_found[i]}</b>\n\nДата: {schedules[i][0]['match_date_time']}\nСтадион: {schedules[i][0]['stadium_name']}\nАдрес: {schedules[i][0]['stadium_address']}\n<b>{schedules[i][0]['home_club_name']} VS {schedules[i][0]['away_club_name']}</b>\n\nДата: {schedules[i][1]['match_date_time']}\nСтадион: {schedules[i][1]['stadium_name']}\nАдрес: {schedules[i][1]['stadium_address']}\n<b>{schedules[i][1]['home_club_name']} VS {schedules[i][1]['away_club_name']}</b>', parse_mode='html')

            del user_states[message.chat.id]

        else:
            if message.text.lower() == 'привет':
                bot.send_message(message.chat.id, f'Привет, {message.from_user.first_name}!', parse_mode='html')
            elif message.text.lower() == 'пока':
                bot.send_message(message.chat.id, f'Пока, {message.from_user.first_name}!', parse_mode='html')
            elif message.text.lower() == 'как дела?':
                bot.send_message(message.chat.id, 'Отлично!', parse_mode='html')
            else:
                bot.send_message(message.chat.id, 'Я вас не понимаю. Напишите /help.')

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    try:
        if call.message:
            if call.data == 'buy_subscription':
                bot.send_message(call.message.chat.id, 'Купить подписку')

    except Exception as e:
        print(repr(e))

bot.polling(non_stop=True)