#!/bin/sh
# Запуск бота в контейнере. Папка базы (/data) — постоянное хранилище хостинга: в Amvera
# и в docker compose она подключается при запуске и может принадлежать root. Поэтому
# контейнер стартует от root, отдаёт папку пользователю bot и дальше работает от его имени.
set -e

data_dir="$(dirname "${DATABASE_PATH:-/data/lflbot.db}")"
if [ "$(id -u)" = "0" ]; then
  mkdir -p "$data_dir"
  chown -R bot:bot "$data_dir"
  exec setpriv --reuid=bot --regid=bot --init-groups "$0" "$@"
fi

# Перед запуском бота база приводится к последней версии схемы.
alembic upgrade head
exec python -m lflbot
