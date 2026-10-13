FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

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
