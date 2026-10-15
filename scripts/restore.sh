#!/usr/bin/env bash
# Восстановление базы из копии.
#
# База в docker compose на этом сервере (запускать в папке проекта на сервере):
#   scripts/restore.sh backups/lflbot-ГГГГММДД-ЧЧММСС.sql.gz
#   scripts/restore.sh backups/lflbot-ГГГГММДД-ЧЧММСС.sql.gz.enc   (зашифрованная, спросит пароль)
#
# Внешняя база, например управляемый PostgreSQL в Amvera (запускать на своём компьютере,
# нужен Docker; пароль базы скрипт спросит сам):
#   scripts/restore.sh lflbot-….sql.gz.enc postgresql://ПОЛЬЗОВАТЕЛЬ@ХОСТ:5432/БАЗА
#
# Внимание: текущие данные в базе будут заменены данными из копии.
set -euo pipefail

cd "$(dirname "$0")/.."
file="${1:?Укажите файл копии}"
target="${2:-}"

# Сначала копия целиком распаковывается во временный файл: если пароль неверный или файл
# повреждён, скрипт остановится раньше, чем тронет текущую базу.
sql="$(mktemp)"
trap 'rm -f "$sql"' EXIT
if [[ "$file" == *.enc ]]; then
  # Параметры те же, что при шифровании в src/lflbot/backup.py (OPENSSL_ENC).
  # Пароль спросит openssl; чтобы не вводить, задайте переменную BACKUP_PASSWORD.
  pass_args=()
  [[ -n "${BACKUP_PASSWORD:-}" ]] && pass_args=(-pass env:BACKUP_PASSWORD)
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -salt ${pass_args[@]+"${pass_args[@]}"} -in "$file" \
    | gunzip > "$sql"
else
  gunzip -c "$file" > "$sql"
fi
echo "Копия прочитана: $(wc -c < "$sql") байт SQL"

if [[ -n "$target" ]]; then
  if [[ "$target" != postgresql://* && "$target" != postgres://* ]]; then
    echo "Адрес базы нужен в виде postgresql://ПОЛЬЗОВАТЕЛЬ@ХОСТ:5432/БАЗА" >&2
    exit 1
  fi
  echo "Перед восстановлением остановите бота (в Amvera: «Остановить» на странице проекта)."
  read -r -p "Заменить данные в базе $target данными из $file? [y/N] " answer
  [[ "$answer" == "y" ]] || exit 1
  if [[ -z "${PGPASSWORD:-}" ]]; then
    read -r -s -p "Пароль пользователя базы: " PGPASSWORD
    echo
  fi
  export PGPASSWORD
  # psql 16 из официального образа: внешний адрес базы Amvera не принимает клиентов
  # PostgreSQL 17 и новее. Пароль передаётся через окружение, а не в командной строке.
  psql=(docker run --rm -i -e PGPASSWORD -e PGSSLMODE=require postgres:16-alpine psql -q "$target")
  "${psql[@]}" -c "DROP SCHEMA public CASCADE" -c "CREATE SCHEMA public"
  "${psql[@]}" < "$sql"
  echo "База восстановлена из $file. Запустите бота."
  exit 0
fi

read -r -p "Заменить текущую базу данными из $file? [y/N] " answer
[[ "$answer" == "y" ]] || exit 1

docker compose stop bot
docker compose exec -T db sh -c \
  'psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\"" -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\""'
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q' < "$sql"
docker compose start bot
echo "База восстановлена из $file"
