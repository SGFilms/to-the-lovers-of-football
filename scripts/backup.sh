#!/usr/bin/env bash
# Резервная копия базы на самом сервере, в дополнение к копиям, которые бот каждый день
# сам отправляет администраторам (README, «Резервные копии»). Запускается из папки проекта,
# обычно по cron. Копии кладутся в ./backups и хранятся KEEP_DAYS дней.
# Если задан BACKUP_REMOTE (имя удалённого хранилища rclone, например "yadisk:lflbot-backups"),
# копия дополнительно отправляется туда, за пределы сервера.
set -euo pipefail

cd "$(dirname "$0")/.."
KEEP_DAYS="${KEEP_DAYS:-14}"
mkdir -p backups
file="backups/lflbot-$(date +%Y%m%d-%H%M%S).db.gz"

# Копию файла базы снимает сам контейнер бота, тем же способом, что и ежедневные копии.
docker compose exec -T bot python -c '
import sys
from sqlalchemy import make_url
from lflbot.backup import copy_database
from lflbot.config import DatabaseSettings
sys.stdout.buffer.write(copy_database(make_url(DatabaseSettings().db_url()).database))
' | gzip > "$file"
echo "Копия сохранена: $file"

if [[ -n "${BACKUP_REMOTE:-}" ]]; then
  rclone copy "$file" "$BACKUP_REMOTE"
  echo "Копия отправлена в $BACKUP_REMOTE"
fi

find backups -name 'lflbot-*.gz' -mtime +"$KEEP_DAYS" -delete
