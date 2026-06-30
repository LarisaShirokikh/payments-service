import asyncio
import logging
import random
import uuid

import httpx
from faststream import FastStream

from app import repository
from app.broker import NEW_QUEUE, broker, declare_topology, publish_to_dlq
from app.config import settings
from app.db import session_factory
from app.enums import PaymentStatus

log = logging.getLogger("consumer")
logging.basicConfig(level=logging.INFO)

app = FastStream(broker)


@app.after_startup
async def on_started() -> None:
    await declare_topology()


async def _emulate_processing() -> PaymentStatus:
    await asyncio.sleep(random.uniform(settings.process_min_seconds, settings.process_max_seconds))
    return PaymentStatus.SUCCEEDED if random.random() < settings.success_rate else PaymentStatus.FAILED


async def _deliver_webhook(url: str, payload: dict) -> None:
    """POST the webhook with up to N attempts and exponential backoff; raise on final failure."""
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds) as client:
        for attempt in range(1, settings.webhook_max_attempts + 1):
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                log.warning("webhook attempt %d/%d failed: %s", attempt, settings.webhook_max_attempts, exc)
                if attempt < settings.webhook_max_attempts:
                    await asyncio.sleep(settings.webhook_backoff_base_seconds * 2 ** (attempt - 1))
    raise last_exc  # type: ignore[misc]


@broker.subscriber(NEW_QUEUE)
async def process_payment(message: dict) -> None:
    payment_id = uuid.UUID(message["payment_id"])

    async with session_factory() as session:
        payment = await repository.get_payment(session, payment_id)
        if payment is None:
            log.warning("payment %s not found, dropping", payment_id)
            return
        # charge only once even if the message is redelivered
        if payment.status == PaymentStatus.PENDING.value:
            outcome = await _emulate_processing()
            payment = await repository.mark_payment_processed(session, payment_id, outcome)
            log.info("payment %s processed -> %s", payment_id, payment.status)
        else:
            log.info("payment %s already in status %s", payment_id, payment.status)

    if not payment.webhook_url:
        return

    webhook_payload = {
        "payment_id": str(payment_id),
        "status": payment.status,
        "amount": str(payment.amount),
        "currency": payment.currency,
    }
    try:
        await _deliver_webhook(payment.webhook_url, webhook_payload)
        log.info("webhook delivered for payment %s", payment_id)
    except Exception as exc:  # noqa: BLE001
        log.error("webhook for %s failed after %d attempts, routing to DLQ", payment_id, settings.webhook_max_attempts)
        await publish_to_dlq({**message, "status": payment.status, "reason": f"webhook delivery failed: {exc}"})
