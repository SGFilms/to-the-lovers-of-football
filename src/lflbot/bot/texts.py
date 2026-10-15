"""Все тексты, которые видит пользователь, собраны здесь."""

# Профиль бота: видно в Telegram до первого сообщения.
BOT_SHORT_DESCRIPTION = (
    "Когда и где играет ваша команда ЛФЛ: дата, время по Москве и стадион. "
    "{price} ₽ за {days} дней."
)
BOT_DESCRIPTION = (
    "⚽ Расписание матчей любительских команд ЛФЛ.\n\n"
    "Напишите название команды, и бот покажет ближайшие матчи: дату, время по Москве, "
    "соперника и стадион со ссылкой на карту.\n\n"
    "Один поиск бесплатно, дальше подписка: {price} ₽ за {days} дней, без автопродления."
)

# Приветствие для тех, у кого нет подписки. Подпись к картинке: не длиннее 1024 символов.
WELCOME = (
    "⚽ <b>Расписание матчей ЛФЛ</b>\n\n"
    "📅 Ближайшие матчи вашей команды в одном сообщении\n"
    "🕒 Дата и время по Москве, соперник и турнир\n"
    "🏟 Стадион со ссылкой на карту\n\n"
    "Подписка: <b>{price} ₽ за {days} дней</b>, без автопродления."
)
WELCOME_PREVIEW = "\n\nОдин поиск бесплатно: нажмите «Посмотреть пример»."
WELCOME_SUBSCRIPTION_ENDED = (
    "\n\nПодписка закончилась {ends_at}. Продлите её, чтобы снова смотреть расписание."
)

MENU = "⚽ <b>Расписание матчей ЛФЛ</b>\n\n✅ Подписка активна до <b>{ends_at}</b>"

# Кнопки
EXAMPLE_BUTTON = "🔎 Посмотреть пример"
SUBSCRIBE_BUTTON = "💳 Оформить подписку · {price} ₽"
SCHEDULE_BUTTON = "📅 Расписание"
FAVORITE_BUTTON = "⭐ {team}"
MY_SUBSCRIPTION_BUTTON = "💳 Моя подписка"
HELP_BUTTON = "❓ Помощь"
MENU_BUTTON = "« Меню"
OTHER_TEAM_BUTTON = "🔎 Другая команда"
REFRESH_BUTTON = "🔄 Обновить"
FEEDBACK_BUTTON = "✍️ Написать отзыв"
OFFER_BUTTON = "📄 Оферта"
PRIVACY_BUTTON = "🔒 Конфиденциальность"
BACK_TO_HELP_BUTTON = "« Помощь"
CANCEL_BUTTON = "Отмена"

HELP = (
    "❓ <b>Как пользоваться ботом</b>\n\n"
    "1. Нажмите «Расписание» и напишите название команды, например <i>Монтана</i>. "
    "Можно просто отправить название в чат.\n"
    "2. Если команд с таким названием несколько, выберите свою по лиге.\n"
    "3. Бот покажет ближайшие матчи. Последняя команда запоминается, и в меню появится "
    "кнопка с её названием.\n\n"
    "Время показано по Москве. Данные берутся с сайта ЛФЛ и обновляются раз в 15 минут.\n\n"
    "<b>Подписка</b> стоит {price} ₽ за {days} дней и сама не продлевается. "
    "За 3 дня и за сутки до окончания бот напомнит.\n\n"
    "/start — меню\n"
    "/schedule — расписание команды\n"
    "/subscription — моя подписка\n"
    "/help — эта справка"
)

# Расписание
SCHEDULE_PROMPT = "📅 Напишите название команды, например: <i>Монтана</i>"
SEARCHING = "🔎 Ищу…"
LFL_UNAVAILABLE = (
    "😔 Сайт ЛФЛ сейчас не отвечает, поэтому расписание получить не удалось.\n"
    "Попробуйте ещё раз через несколько минут."
)
QUERY_TOO_SHORT = "Напишите название команды хотя бы из двух букв."
TEAM_NOT_FOUND = "Команда «{query}» на сайте ЛФЛ не найдена. Проверьте название."
CHOOSE_TEAM = "Нашлось несколько команд «{query}». Выберите нужную:"
CHOOSE_TEAM_MORE = (
    "На сайте ЛФЛ {total} команд «{query}», но в поиске сайт выдаёт только {shown}. "
    "Если нужной нет, уточните название, например добавьте город или район."
)
NO_UPCOMING = "У команды <b>{team}</b> пока нет запланированных матчей."
NO_UPCOMING_PREVIEW = "\n\nБесплатный пример не потрачен: попробуйте другую команду."
SCHEDULE_HEADER = "⚽ <b>{team}</b>\n{league}"
TIME_UNKNOWN = "время уточняется"
PREVIEW_USED = (
    "\n\n🎁 Это был бесплатный пример. Чтобы смотреть расписание любой команды, "
    "оформите подписку: {price} ₽ за {days} дней."
)
PAYWALL = (
    "🔒 <b>Расписание доступно по подписке</b>\n\n"
    "Бесплатный пример уже использован. Подписка стоит {price} ₽ за {days} дней "
    "и сама не продлевается."
)

# Подписка и оплата
SUBSCRIBE_OFFER = (
    "💳 <b>Подписка на {days} дней — {price} ₽</b>\n\n"
    "Нажмите «Оплатить», оплатите на странице ЮKassa и возвращайтесь в бот: "
    "подписка включится сама, обычно в течение минуты."
)
SUBSCRIBE_OFFER_ACTIVE = (
    "💳 <b>Продление на {days} дней — {price} ₽</b>\n\n"
    "Подписка активна до <b>{ends_at}</b>. Оплата добавит ещё {days} дней к этой дате."
)
SUBSCRIBE_OFFER_TERMS = "\n\n<i>Оплачивая, вы принимаете условия оферты.</i>"
PAY_BUTTON = "Оплатить {price} ₽"
CHECK_PAYMENT_BUTTON = "Я оплатил"
RENEW_BUTTON = "Продлить подписку"
RENEW_DAYS_BUTTON = "💳 Продлить на {days} дней"
PAYMENTS_DISABLED = "Оплата пока не подключена. Загляните чуть позже."
PAYMENT_CREATE_FAILED = (
    "😔 Не получилось создать платёж: платёжный сервис не ответил. "
    "Попробуйте ещё раз через пару минут."
)
PAYMENT_CHECK_FAILED = "Не получилось проверить оплату. Попробуйте через минуту."
PAYMENT_NOT_YET = "Оплата ещё не поступила. Если вы уже заплатили, подождите минуту."
PAYMENT_CANCELED = "Этот платёж отменён. Чтобы оплатить, оформите подписку заново."
PAYMENT_ALREADY_DONE = "Эта оплата уже получена ✅"
PAYMENT_DONE_MARK = "\n\n✅ Оплачено"

PAID = "✅ <b>Оплата получена!</b>\nПодписка активна до <b>{ends_at}</b>."
PAID_ASK_TEAM = (
    "\n\n⭐ <b>За какую команду болеете?</b> Напишите её название, например «Монтана». "
    "Я запомню её и буду заранее держать расписание наготове."
)
PAID_TEAM = (
    "\n\n⭐ Ваша команда: <b>{team}</b>, её расписание всегда наготове. "
    "Болеете за другую? Просто напишите её название."
)
REFUNDED_ACTIVE = "↩️ Деньги за оплату возвращены. Подписка активна до <b>{ends_at}</b>."
REFUNDED_ENDED = "↩️ Деньги за оплату возвращены, подписка отключена."

MY_SUBSCRIPTION_ACTIVE = "💳 <b>Моя подписка</b>\n\n✅ Активна до <b>{ends_at}</b>."
MY_SUBSCRIPTION_ENDED = "💳 <b>Моя подписка</b>\n\nЗакончилась {ends_at}."
MY_SUBSCRIPTION_NONE = (
    "💳 <b>Моя подписка</b>\n\nПодписки пока нет. Она стоит {price} ₽ за {days} дней."
)
PAYMENT_HISTORY = "\n\n<b>Оплаты</b>\n{lines}"
PAYMENT_HISTORY_LINE = "{date} — {amount} ₽"
PAYMENT_HISTORY_REFUNDED = "{date} — {amount} ₽, возвращено"

REMINDER_3 = "⏳ Подписка закончится через 3 дня, <b>{ends_at}</b>."
REMINDER_1 = "⏳ Подписка закончится меньше чем через сутки, <b>{ends_at}</b>."
REMINDER_0 = "Подписка закончилась. Продлите её, чтобы снова смотреть расписание."

# Отзывы
FEEDBACK_PROMPT = (
    "✍️ <b>Отзыв</b>\n\n"
    "Напишите одним сообщением, что понравилось, что не работает или чего не хватает. "
    "Сообщение получит автор бота."
)
FEEDBACK_THANKS = "Спасибо! Отзыв отправлен 🙌"
FEEDBACK_FAILED = "😔 Не получилось отправить отзыв. Попробуйте позже."
FEEDBACK_DISABLED = "Отзывы пока не принимаются. Загляните чуть позже."
FEEDBACK_CANCELED = "Хорошо, без отзыва."

UNKNOWN_COMMAND = "Такой команды нет. Список команд: /help"

# Администраторам
ADMIN_FEEDBACK = "✍️ <b>Отзыв</b> от Telegram ID <code>{user_id}</code>:"
# Данные для чека в «Мой налог».
ADMIN_PAID = (
    "💰 <b>Новая оплата: {amount} ₽</b>\n"
    "Дата: {date}\n"
    "Услуга: {service}\n"
    "Покупатель: физическое лицо (Telegram ID <code>{user_id}</code>)\n"
    "Платёж ЮKassa: <code>{payment_id}</code>\n\n"
    "Не забудьте пробить чек в «Мой налог»."
)
ADMIN_REFUNDED = (
    "↩️ <b>Возврат: {amount} ₽</b>\n"
    "Платёж ЮKassa: <code>{payment_id}</code> (Telegram ID <code>{user_id}</code>)\n\n"
    "Аннулируйте чек по этой оплате в «Мой налог»."
)

# Админка: команды видны и работают только у Telegram ID из ADMIN_IDS.
ADMIN_HELP = (
    "🛠 <b>Команды администратора</b>\n\n"
    "/stats — статистика и состояние бота\n"
    "/user <i>ID</i> — карточка пользователя\n"
    "/grant <i>ID</i> <i>дни</i> — добавить дни подписки, "
    "например <code>/grant 123456 30</code>\n"
    "/grant <i>ID</i> -<i>дни</i> — снять дни, например <code>/grant 123456 -5</code>\n"
    "/payment <i>номер</i> — платёж ЮKassa, заново проверяет его статус\n"
    "/check — готов ли бот принимать оплаты: ключи ЮKassa, адрес сервера, оферта\n"
    "/backup — сделать копию базы и отправить её сейчас\n\n"
    "Telegram ID пользователя есть в уведомлениях об оплатах и отзывах."
)
ADMIN_STATS = (
    "📊 <b>Статистика</b> · {now}\n\n"
    "👥 Пользователей: <b>{users}</b> (+{users_day} за сутки, +{users_week} за 7 дней)\n"
    "✅ Активных подписок: <b>{subscribers}</b>\n"
    "🎁 Потратили бесплатный пример: {previews_used}\n\n"
    "💰 Оплат за 30 дней: <b>{paid_month}</b> на {paid_month_sum} ₽\n"
    "💰 Оплат за всё время: {paid_total} на {paid_total_sum} ₽\n"
    "↩️ Возвратов за 30 дней: {refunds_month}\n"
    "⏳ Неоплаченных ссылок за сутки: {pending_day}\n\n"
    "<b>Состояние</b>\n"
    "🌐 Сайт ЛФЛ: {lfl}\n"
    "💳 ЮKassa: {yookassa}\n"
    "⏱ Бот запущен {started_at}"
)
ADMIN_LFL_NEVER = "запросов ещё не было"
ADMIN_LFL_OK = "✅ отвечает, последний ответ {at}"
ADMIN_LFL_FAILING = "⚠️ {failure} ({at})"
ADMIN_YOOKASSA_OFF = "не подключена"
ADMIN_YOOKASSA_TEST = "тестовый магазин"
ADMIN_YOOKASSA_LIVE = "боевой магазин"

CHECK_REPORT = "🔎 <b>Проверка перед приёмом оплат</b> · {now}\n\n{lines}\n\n{verdict}"
CHECK_YOOKASSA_OFF = (
    "<b>ЮKassa</b>: ключи не заданы, оплата отключена. "
    "Впишите YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY в переменные и перезапустите бота."
)
CHECK_YOOKASSA_BAD_KEYS = (
    "<b>ЮKassa</b>: ключи не подходят. Сверьте YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY "
    "в переменных с разделом «Интеграция» → «Ключи API» того же магазина."
)
CHECK_YOOKASSA_UNAVAILABLE = (
    "<b>ЮKassa</b>: не отвечает, проверить ключи не удалось. Повторите /check через минуту."
)
CHECK_YOOKASSA_DISABLED = (
    "<b>ЮKassa</b>: магазин {shop_id} отключён и не принимает платежи. "
    "Узнайте причину в личном кабинете или поддержке ЮKassa."
)
CHECK_YOOKASSA_TEST = (
    "<b>ЮKassa</b>: тестовый магазин {shop_id}. Ключи верные, но деньги не списываются."
)
CHECK_YOOKASSA_LIVE = "<b>ЮKassa</b>: боевой магазин {shop_id}, ключи верные."
CHECK_DOMAIN_EMPTY = (
    "<b>Адрес сервера</b>: DOMAIN не задан. Уведомления ЮKassa не придут, оплаты "
    "засчитываются фоновой сверкой раз в минуту. Для компьютера это нормально."
)
CHECK_DOMAIN_FAILED = (
    "<b>Адрес сервера</b>: {url} не открылся изнутри сервера ({problem}). "
    "Проверьте домен во вкладке «Домены» в Amvera и записи DNS у регистратора."
)
CHECK_DOMAIN_OK = "<b>Адрес сервера</b>: {url} отвечает, HTTPS работает."
CHECK_WEBHOOK_NONE = (
    "<b>Уведомления ЮKassa</b>: с запуска бота ещё не приходили. Если оплата уже была, "
    "проверьте в магазине «Интеграция» → «HTTP-уведомления»: адрес <code>{url}</code>, "
    "события payment.succeeded, payment.canceled, refund.succeeded."
)
CHECK_WEBHOOK_OK = "<b>Уведомления ЮKassa</b>: приходят, последнее {at}."
CHECK_SELLER_MISSING = (
    "<b>Оферта</b>: не заполнено {fields} в переменных, в оферте стоит «не указано»."
)
CHECK_SELLER_OK = "<b>Оферта</b>: данные исполнителя заполнены."
CHECK_LFL = "<b>Сайт ЛФЛ</b>: {state}"
CHECK_BACKUP_OFF = (
    "<b>Копии базы</b>: никуда не отправляются. Включите BACKUP_TELEGRAM или задайте "
    "BACKUP_EMAIL в переменных, иначе при поломке хостинга база пропадёт."
)
CHECK_BACKUP_MANUAL = "<b>Копии базы</b>: BACKUP_TIME пуст, копии только по команде /backup."
CHECK_BACKUP_DAILY = "<b>Копии базы</b>: каждый день в {at} — {channels}, {protection}."
CHECK_BACKUP_ENCRYPTED = "зашифрованы"
CHECK_BACKUP_PLAIN = "без шифрования"
CHECK_BACKUP_LAST_OK = " Последняя {at} дошла."
CHECK_BACKUP_LAST_FAILED = " Последняя {at} не дошла: {error}. Проверьте командой /backup."
CHECK_BACKUP_NEVER = " С запуска бота ещё не делались, проверить можно командой /backup."
CHECK_VERDICT_FAIL = "❌ <b>Есть проблемы.</b> Исправьте строки с ❌ и повторите /check."
CHECK_VERDICT_TEST = (
    "🧪 <b>Подключён тестовый магазин.</b> Проверьте оплату тестовой картой, "
    "потом переключите ключи на боевые."
)
CHECK_VERDICT_WARN = "⚠️ <b>Боевой магазин подключён</b>, но проверьте строки с ⚠️."
CHECK_VERDICT_OK = "✅ <b>Бот готов принимать оплаты.</b>"

BACKUP_TELEGRAM = "Telegram"
BACKUP_EMAIL = "почта {email}"
BACKUP_CAPTION = (
    "💾 <b>Копия базы</b> · {at}\n"
    "Пользователей: {users}, платежей: {payments}. {protection}\n\n"
    "Сохраните файл у себя. Как восстановить базу — в README, раздел «Резервные копии»."
)
BACKUP_CAPTION_ENCRYPTED = "🔒 Зашифрована паролем BACKUP_PASSWORD."
BACKUP_CAPTION_PLAIN = "Не зашифрована: не пересылайте её никому."
BACKUP_EMAIL_SUBJECT = "Копия базы бота ЛФЛ · {at}"
BACKUP_EMAIL_BODY = (
    "Копия базы бота от {at}.\n"
    "Пользователей: {users}, платежей: {payments}. {protection}\n\n"
    "Как восстановить базу — в README, раздел «Резервные копии».\n"
)
BACKUP_EMAIL_NOT_CONFIGURED = "не заданы переменные {fields}"
BACKUP_TOO_BIG = "файл {size} больше допустимых {limit}"
BACKUP_NO_ADMINS = "ADMIN_IDS пуст"
BACKUP_NOWHERE = "Копия никуда не отправляется: выключен BACKUP_TELEGRAM и не задан BACKUP_EMAIL."
BACKUP_STARTED = "⏳ Делаю копию базы…"
BACKUP_FAILED = "❌ Копию сделать не удалось:\n<code>{error}</code>"
BACKUP_REPORT = "💾 Копия базы {filename}, {size}:\n{lines}"
BACKUP_DELIVERED = "✅ {channel}"
BACKUP_NOT_DELIVERED = "❌ {channel}: {error}"

ADMIN_BAD_USER_ID = "Укажите Telegram ID числом, например <code>/user 123456</code>."
ADMIN_USER_NOT_FOUND = (
    "Пользователя <code>{user_id}</code> нет в базе: он ещё не писал боту. "
    "Дни ему всё равно можно выдать командой /grant."
)
ADMIN_USER_CARD = (
    "👤 <b>Пользователь</b> <code>{user_id}</code>\n\n"
    "Первый раз написал: {created_at}\n"
    "Подписка: {subscription}\n"
    "Бесплатный пример: {preview}\n"
    "Избранная команда: {favorite}"
)
ADMIN_SUB_ACTIVE = "✅ до {ends_at}"
ADMIN_SUB_ENDED = "закончилась {ends_at}"
ADMIN_SUB_NONE = "не было"
ADMIN_PREVIEW_USED = "потрачен {at}"
ADMIN_PREVIEW_FREE = "не потрачен"
ADMIN_NO_FAVORITE = "нет"
ADMIN_CARD_PAYMENTS = "\n\n<b>Платежи</b>\n{lines}"
ADMIN_CARD_PAYMENT = "{date} · {amount} ₽ · {status} · <code>{payment_id}</code>"
ADMIN_CARD_GRANTS = "\n\n<b>Выдано вручную</b>\n{lines}"
ADMIN_CARD_GRANT = "{date} · {days:+d} дн. (админ <code>{admin_id}</code>)"

PAYMENT_STATUS_PAID = "оплачен"
PAYMENT_STATUS_REFUNDED = "возвращён"
PAYMENT_STATUS_CANCELED = "отменён"
PAYMENT_STATUS_PENDING = "не оплачен"

ADMIN_GRANT_USAGE = (
    "Формат: <code>/grant ID дни</code>, например <code>/grant 123456 30</code>. "
    "Чтобы снять дни, укажите их со знаком минус: <code>/grant 123456 -5</code>. "
    "За раз не больше {max_days} дней."
)
ADMIN_GRANTED = "✅ Пользователю <code>{user_id}</code> добавлено {days} дн. Подписка до {ends_at}."
ADMIN_TAKEN = "✅ У пользователя <code>{user_id}</code> снято {days} дн. Подписка: {subscription}."
ADMIN_NOTHING_TO_TAKE = (
    "У пользователя <code>{user_id}</code> нет активной подписки, снимать нечего."
)
ADMIN_USER_NOTIFIED = "\nПользователь получил сообщение об этом."
ADMIN_USER_NOT_NOTIFIED = (
    "\nНаписать пользователю не удалось: он ещё не открывал бота или заблокировал его."
)
# Пользователю, которому администратор добавил дни.
GRANTED = "🎁 Вам добавлено {days} дн. подписки. Подписка активна до <b>{ends_at}</b>."

ADMIN_PAYMENT_USAGE = "Укажите номер платежа ЮKassa: <code>/payment номер</code>."
ADMIN_PAYMENT_NOT_FOUND = "Платежа <code>{payment_id}</code> нет в базе бота."
ADMIN_PAYMENT_CARD = (
    "💳 <b>Платёж</b> <code>{payment_id}</code>\n\n"
    "Пользователь: <code>{user_id}</code> (/user {user_id})\n"
    "Сумма: {amount} ₽ за {days} дн.\n"
    "Статус: {status}\n"
    "Создан: {created_at}"
)
ADMIN_PAYMENT_PAID_AT = "\nЗасчитан: {at}"
ADMIN_PAYMENT_REFUNDED_AT = "\nВозвращён: {at}"
ADMIN_PAYMENT_SYNCED = "\n\n🔄 Статус проверен в ЮKassa только что."
ADMIN_PAYMENT_SYNC_FAILED = "\n\n⚠️ ЮKassa не ответила, показан статус из базы."
ADMIN_PAYMENT_SYNC_OFF = "\n\nЮKassa не подключена, показан статус из базы."

# Сообщения о сбоях.
ALERT_LFL_UNAVAILABLE = (
    "⚠️ <b>Сайт ЛФЛ не отвечает</b> ({page})\n<code>{detail}</code>\n\n"
    "Пользователи видят «сайт не отвечает» или сохранённое ранее расписание. "
    "Бот сам попробует снова через несколько минут."
)
ALERT_LFL_LAYOUT = (
    "🚨 <b>Сайт ЛФЛ изменился</b> ({page}): бот не может разобрать страницу.\n"
    "<code>{detail}</code>\n\n"
    "Пока парсер не обновят, расписание не показывается. Нужен разработчик."
)
ALERT_LFL_RECOVERED = "✅ Сайт ЛФЛ снова отвечает ({page})."
ALERT_LFL_PAGES = {"search": "поиск команды", "calendar": "календарь матчей"}
ALERT_ERROR = (
    "🚨 <b>Ошибка в боте</b> при {where}\n<code>{error}</code>\n\nПодробности в логах бота."
)
ALERT_ERROR_UPDATE = "обработке сообщения"
ALERT_ERROR_JOB = "фоновой задаче «{name}»"
ALERT_LFL_UNAVAILABLE_SHORT = "не отвечает"
ALERT_LFL_LAYOUT_SHORT = "изменилась вёрстка, расписание не разбирается"
