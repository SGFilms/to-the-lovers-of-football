#!/usr/bin/env bash
# Восстановление базы из копии: scripts/restore.sh backups/lflbot-YYYYMMDD-HHMMSS.sql.gz
# Внимание: текущие данные в базе будут заменены данными из копии.
set -euo pipefail

cd "$(dirname "$0")/.."
file="${1:?Укажите файл копии}"

read -r -p "Заменить текущую базу данными из $file? [y/N] " answer
[[ "$answer" == "y" ]] || exit 1

docker compose stop bot
docker compose exec -T db sh -c \
  'psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\"" -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\""'
gunzip -c "$file" | docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q'
docker compose start bot
echo "База восстановлена из $file"
