#!/usr/bin/env bash
# Восстановление базы из копии:
#   scripts/restore.sh backups/lflbot-ГГГГММДД-ЧЧММСС.sql.gz
#   scripts/restore.sh backups/lflbot-ГГГГММДД-ЧЧММСС.sql.gz.enc   (зашифрованная, спросит пароль)
# Внимание: текущие данные в базе будут заменены данными из копии.
set -euo pipefail

cd "$(dirname "$0")/.."
file="${1:?Укажите файл копии}"

# Сначала копия целиком распаковывается во временный файл: если пароль неверный или файл
# повреждён, скрипт остановится раньше, чем тронет текущую базу.
sql="$(mktemp)"
trap 'rm -f "$sql"' EXIT
if [[ "$file" == *.enc ]]; then
  # Параметры те же, что при шифровании в src/lflbot/backup.py (OPENSSL_ENC).
  # Пароль спросит openssl; чтобы не вводить, задайте переменную BACKUP_PASSWORD.
  pass_args=()
  [[ -n "${BACKUP_PASSWORD:-}" ]] && pass_args=(-pass env:BACKUP_PASSWORD)
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -salt "${pass_args[@]}" -in "$file" \
    | gunzip > "$sql"
else
  gunzip -c "$file" > "$sql"
fi
echo "Копия прочитана: $(wc -c < "$sql") байт SQL"

read -r -p "Заменить текущую базу данными из $file? [y/N] " answer
[[ "$answer" == "y" ]] || exit 1

docker compose stop bot
docker compose exec -T db sh -c \
  'psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\"" -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\""'
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q' < "$sql"
docker compose start bot
echo "База восстановлена из $file"
