FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

# openssl шифрует резервные копии базы.
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY src ./src
COPY scripts/entrypoint.sh /usr/local/bin/entrypoint.sh

# Бот работает от пользователя bot: от root только entrypoint.sh отдаёт ему папку базы.
RUN useradd --create-home --uid 1000 bot && mkdir -p /data && chown bot:bot /data

EXPOSE 8080

CMD ["entrypoint.sh"]
