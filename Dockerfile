FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_CREATE=false

RUN pip install --no-cache-dir "poetry==1.8.5"

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only main --no-interaction

COPY . .
