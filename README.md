# Payments service

Сервис принимает платежи по HTTP, обрабатывает их асинхронно через очередь и шлёт клиенту
webhook с результатом.

## Стек
Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async) + asyncpg, PostgreSQL, RabbitMQ
(FastStream), Alembic, Poetry, Docker Compose.

## Как поднять

```bash
cp .env.example .env
docker compose up --build
```

Поднимаются postgres, rabbitmq, api (порт 8000) и consumer. Миграции применяются автоматически
при старте api.

- Swagger: http://localhost:8000/docs
- RabbitMQ UI: http://localhost:15672 (guest / guest)

## API

Все запросы требуют заголовок `X-API-Key` (значение из `API_KEY`, по умолчанию `secret-api-key`).

Создать платёж — `POST /api/v1/payments`, заголовок `Idempotency-Key` обязателен:

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: secret-api-key" \
  -H "Idempotency-Key: order-123" \
  -H "Content-Type: application/json" \
  -d '{"amount": "199.90", "currency": "EUR", "description": "Subscription", "metadata": {"order_id": 123}, "webhook_url": "https://webhook.site/<id>"}'
```

Ответ `202`:
```json
{"payment_id": "...", "status": "pending", "created_at": "..."}
```

Получить платёж:
```bash
curl http://localhost:8000/api/v1/payments/<payment_id> -H "X-API-Key: secret-api-key"
```

## Как это работает

При создании платежа в одной транзакции пишутся строка в `payments` и строка в `outbox`.
Фоновый воркер в api читает неотправленные записи outbox и публикует их в очередь `payments.new`
(паттерн outbox: событие уйдёт, только если платёж реально сохранён).

Consumer берёт сообщение, эмулирует обработку (2–5 секунд, ~90% успех), проставляет статус
`succeeded`/`failed` и отправляет webhook. Доставка webhook повторяется до 3 раз с экспоненциальной
задержкой (1, 2, 4 сек); если так и не получилось, сообщение уходит в `payments.dlq`.

Идемпотентность: `Idempotency-Key` уникален, повторный запрос с тем же ключом вернёт уже созданный
платёж. Consumer тоже идемпотентен — повторная доставка сообщения не приводит к повторной оплате,
статус меняется только из `pending`.

Чтобы посмотреть retry и DLQ в действии, укажи в `webhook_url` недоступный адрес и загляни в
очередь `payments.dlq` в RabbitMQ UI.

## Конфигурация
Все параметры в `.env` (см. `.env.example`): ключ API, доступы к postgres/rabbitmq, параметры
эмуляции, число попыток webhook и интервал outbox-воркера.
