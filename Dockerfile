FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

# Для резервных копий: pg_dump той же версии, что и база (postgres:16 в docker-compose.yml),
# из репозитория PostgreSQL, и openssl для шифрования копий.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates openssl postgresql-common \
    && /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY src ./src

RUN useradd --create-home --uid 1000 bot
USER bot

EXPOSE 8080

# Перед запуском бота база приводится к последней версии схемы.
CMD ["sh", "-c", "alembic upgrade head && exec python -m lflbot"]
