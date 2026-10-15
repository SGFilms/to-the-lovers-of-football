FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

# Для резервных копий: pg_dump из репозитория PostgreSQL и openssl для шифрования копий.
# pg_dump умеет снимать копии с баз своей и более старых версий, поэтому версия клиента
# не ниже базы: postgres:16 в docker-compose.yml и управляемой базы в Amvera.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates openssl postgresql-common \
    && /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y \
    && apt-get install -y --no-install-recommends postgresql-client-18 \
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
