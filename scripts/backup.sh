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
file="backups/lflbot-$(date +%Y%m%d-%H%M%S).sql.gz"

docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' \
  | gzip > "$file"
echo "Копия сохранена: $file"

if [[ -n "${BACKUP_REMOTE:-}" ]]; then
  rclone copy "$file" "$BACKUP_REMOTE"
  echo "Копия отправлена в $BACKUP_REMOTE"
fi

find backups -name 'lflbot-*.sql.gz' -mtime +"$KEEP_DAYS" -delete
