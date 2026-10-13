# To the lovers of football

Telegram-бот для любителей футбола из ЛФЛ: показывает расписание матчей команды по подписке.

Бот работает в Docker: контейнер бота, база PostgreSQL и (на сервере) Caddy, который выдаёт HTTPS-сертификат для уведомлений ЮKassa.

## Запуск на своём компьютере

Нужен [Docker Desktop](https://www.docker.com/products/docker-desktop/) и **тестовый** бот, созданный в @BotFather, чтобы не мешать боевому.

1. Скопируйте `.env.example` в `.env` и заполните `BOT_TOKEN` (токен тестового бота), `ADMIN_IDS` и `POSTGRES_PASSWORD`. `DOMAIN` оставьте пустым.
2. Запустите в папке проекта:

   ```bash
   docker compose up --build
   ```

3. Напишите тестовому боту `/start`. Остановить бота: `Ctrl+C`.

Данные базы сохраняются между запусками. Чтобы начать с чистой базы: `docker compose down -v`.

## Сервер (Ubuntu)

### Первая установка

1. Направьте домен или поддомен (A-запись) на IP сервера.
2. Установите Docker по [официальной инструкции](https://docs.docker.com/engine/install/ubuntu/).
3. Склонируйте репозиторий и создайте `.env`:

   ```bash
   git clone https://github.com/SGFilms/to-the-lovers-of-football.git
   cd to-the-lovers-of-football
   cp .env.example .env
   nano .env   # токен боевого бота, ADMIN_IDS, POSTGRES_PASSWORD, DOMAIN
   ```

4. Запустите:

   ```bash
   docker compose --profile prod up -d --build
   ```

5. Проверьте, что всё работает: `curl https://ВАШ_ДОМЕН/health` должен вернуть `{"status": "ok"}`.

### Обновление

```bash
git pull
docker compose --profile prod up -d --build
```

Миграции базы применяются автоматически при старте бота.

### Логи

```bash
docker compose logs -f bot
```

### Резервные копии

`scripts/backup.sh` сохраняет копию базы в `backups/` и удаляет копии старше 14 дней. Чтобы копия делалась каждую ночь в 4:00, добавьте строку в `crontab -e`:

```
0 4 * * * cd /путь/к/to-the-lovers-of-football && scripts/backup.sh >> backups/backup.log 2>&1
```

Копии на том же сервере не спасут, если сервер пропадёт. Чтобы отправлять их ещё и в облако, настройте [rclone](https://rclone.org/) (например, на Яндекс Диск) и добавьте в начало строки cron `BACKUP_REMOTE=yadisk:lflbot-backups`.

Восстановление из копии (текущие данные будут заменены):

```bash
scripts/restore.sh backups/lflbot-ГГГГММДД-ЧЧММСС.sql.gz
```

## Для разработки

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check . && ruff format --check .
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/lflbot_test pytest
```

Тестам с базой нужен PostgreSQL. Без `TEST_DATABASE_URL` они пропускаются. В GitHub Actions всё это выполняется на каждый pull request.

Новая миграция после изменения моделей в `src/lflbot/db/models.py`:

```bash
alembic revision --autogenerate -m "что изменилось"
```

## Расписание с сайта ЛФЛ

Бот берёт данные со страниц page.lfl.ru: поиск команды и календарь её матчей. Данные читаются из JSON, который сайт кладёт в страницу (блок `__NEXT_DATA__`), а не из вёрстки.

- Ответы сайта кэшируются на 15 минут. Если сайт не отвечает, бот до 6 часов показывает последнее полученное расписание.
- Запросы идут не чаще одного раза в 3 секунды. Если сайт оборвал соединение, бот 5 минут к нему не обращается: при частых запросах сайт временно перестаёт отвечать.
- Время матчей сайт отдаёт в UTC, бот показывает его по Москве. Полночь по Москве означает, что время ещё не назначено, и бот пишет «время уточняется».

Проверить вручную: напишите боту `/schedule Монтана` с аккаунта из `ADMIN_IDS`.

Тесты разбирают сохранённые страницы сайта из `tests/fixtures/lfl`. Если сайт изменится и тесты на новых страницах упадут, замените файлы там свежими копиями.

## Что хранит бот

Только числовой Telegram ID пользователя, даты подписки и, позже, номера платежей ЮKassa. Имён, ников, телефонов и email бот не хранит.
