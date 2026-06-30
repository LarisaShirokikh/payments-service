# Async Payments Processing Service

Микросервис асинхронной обработки платежей: принимает запрос на оплату, обрабатывает его
асинхронно через эмулируемый платёжный шлюз и уведомляет клиента через webhook.

## Стек
FastAPI + Pydantic v2 · SQLAlchemy 2.0 (async) + asyncpg · PostgreSQL · RabbitMQ (FastStream) ·
Alembic · Docker / docker-compose.

## Архитектура

```
POST /payments ──► [payments] + [outbox]  (одна транзакция)
                         │
                 outbox relay (фоновый таск в API) ──► RabbitMQ: payments.new
                                                              │
                                                          consumer
                                                  эмуляция 2–5с (90% succeeded / 10% failed)
                                                  обновляет статус в БД (идемпотентно)
                                                  webhook: 3 попытки, экспон. задержка
                                                  при исчерпании ──► payments.dlq
```

### Как закрыты требования
- **Outbox pattern.** При создании платежа в одной транзакции пишутся строка `payments` и
  строка `outbox`. Фоновый relay (`app/outbox.py`, запускается в lifespan API) выбирает
  неопубликованные события `SELECT … FOR UPDATE SKIP LOCKED`, публикует в `payments.new` и
  проставляет `published_at`. Событие уйдёт тогда и только тогда, когда платёж закоммичен.
- **Идемпотентность.** Заголовок `Idempotency-Key` → уникальный индекс на `payments.idempotency_key`.
  Повторный запрос с тем же ключом возвращает уже созданный платёж (не создаёт дубль). Consumer
  обрабатывает идемпотентно: эмуляция/смена статуса выполняется только если статус ещё `pending`,
  поэтому повторная доставка сообщения не приводит к повторной «оплате».
- **Retry (3 попытки, экспоненциальная задержка).** Доставка webhook повторяется до
  `WEBHOOK_MAX_ATTEMPTS` раз с задержкой `base * 2^(n-1)` (1с, 2с, 4с).
- **Dead Letter Queue.** Очередь `payments.new` объявлена с `x-dead-letter-*` → `payments.dlq`.
  Если webhook не доставлен после всех попыток, сообщение с причиной отправляется в `payments.dlq`
  (а необработанные исключения уходят туда же через dead-letter). Сообщения в DLQ видны в
  RabbitMQ Management UI: http://localhost:15672 (guest/guest).
- **Аутентификация.** Все эндпоинты требуют заголовок `X-API-Key` (значение из `API_KEY`).

## Запуск

```bash
cp .env.example .env
docker compose up --build
```

Поднимутся: `postgres`, `rabbitmq` (+UI :15672), `api` (:8099 на хосте, прогоняет миграции), `consumer`.
Swagger: http://localhost:8099/docs

## Примеры

Создание платежа (202 Accepted):
```bash
curl -X POST http://localhost:8099/api/v1/payments \
  -H "X-API-Key: secret-api-key" \
  -H "Idempotency-Key: order-123" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "199.90",
    "currency": "EUR",
    "description": "Subscription",
    "metadata": {"order_id": 123},
    "webhook_url": "https://webhook.site/your-uuid"
  }'
```
Ответ:
```json
{"payment_id": "…", "status": "pending", "created_at": "…"}
```

Получение платежа:
```bash
curl http://localhost:8099/api/v1/payments/<payment_id> -H "X-API-Key: secret-api-key"
```

Проверка идемпотентности — повтори тот же запрос с `Idempotency-Key: order-123`: вернётся тот же
`payment_id`, второй платёж не создаётся.

Webhook: укажи в `webhook_url` адрес из https://webhook.site — увидишь POST с телом
`{"payment_id", "status", "amount", "currency"}`. Чтобы увидеть работу retry/DLQ — укажи заведомо
недоступный URL: после 3 неудачных попыток сообщение окажется в `payments.dlq`.

## Структура
```
app/
  main.py        FastAPI + lifespan (брокер, топология, запуск outbox relay)
  api.py         POST /payments, GET /payments/{id}
  auth.py        X-API-Key
  config.py      настройки (pydantic-settings)
  db.py          async engine / session / Base
  models.py      Payment, OutboxMessage
  schemas.py     Pydantic v2
  repository.py  доступ к БД (в т.ч. create payment+outbox в одной транзакции)
  broker.py      RabbitMQ: payments.new (+DLQ), хелперы публикации
  outbox.py      relay: publish unsent → mark published
  consumer.py    FastStream consumer: эмуляция, статус, webhook+retry, DLQ
migrations/      Alembic (payments, outbox)
```

## Заметки по решениям
- Лид-фактор «3 попытки» относится к доставке webhook (основная точка отказа); webhook-исчерпание
  трактуется как «сообщение не обработано» и направляется в DLQ.
- Outbox relay живёт в процессе API (производитель событий); consumer — отдельный сервис.
- Поле `metadata` в модели смаплено как `payment_metadata` (имя `metadata` зарезервировано в SQLAlchemy).
