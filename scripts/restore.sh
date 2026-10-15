#!/usr/bin/env bash
# Готовит файл базы из резервной копии, которую бот прислал в Telegram или на почту:
#   scripts/restore.sh lflbot-ГГГГММДД-ЧЧММСС.db.gz
#   scripts/restore.sh lflbot-ГГГГММДД-ЧЧММСС.db.gz.enc   (зашифрованная, спросит пароль)
# Рядом с копией появится файл lflbot.db. Как подложить его боту — в README,
# раздел «Резервные копии».
#
# На своём сервере с docker compose можно сразу заменить базу бота (из папки проекта):
#   scripts/restore.sh lflbot-….db.gz.enc --compose
set -euo pipefail

file="${1:?Укажите файл копии}"
mode="${2:-}"
out="$(dirname "$file")/lflbot.db"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
if [[ "$file" == *.enc ]]; then
  # Параметры те же, что при шифровании в src/lflbot/backup.py (OPENSSL_ENC).
  # Пароль спросит openssl; чтобы не вводить, задайте переменную BACKUP_PASSWORD.
  pass_args=()
  [[ -n "${BACKUP_PASSWORD:-}" ]] && pass_args=(-pass env:BACKUP_PASSWORD)
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -salt ${pass_args[@]+"${pass_args[@]}"} -in "$file" \
    | gunzip > "$tmp"
else
  gunzip -c "$file" > "$tmp"
fi

# Проверка, что получилась целая база, а не обрывок файла.
python3 - "$tmp" <<'PY'
import sqlite3, sys
db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
try:
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "база повреждена"
    users = db.execute("SELECT count(*) FROM users").fetchone()[0]
    payments = db.execute("SELECT count(*) FROM payments").fetchone()[0]
finally:
    db.close()
print(f"Копия цела: пользователей {users}, платежей {payments}")
PY

if [[ "$mode" != "--compose" ]]; then
  mv "$tmp" "$out"
  trap - EXIT
  echo "Файл базы готов: $out"
  exit 0
fi

cd "$(dirname "$0")/.."
read -r -p "Заменить базу бота в docker compose копией $file? [y/N] " answer
[[ "$answer" == "y" ]] || exit 1
docker compose stop bot
docker compose cp "$tmp" bot:/data/lflbot.db
# Журнал прежней базы, если остался, к новой не подходит.
docker compose run --rm --no-deps --entrypoint rm bot -f /data/lflbot.db-journal
docker compose start bot
echo "База восстановлена из $file"
