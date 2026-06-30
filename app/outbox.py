import asyncio
import logging

from app import repository
from app.broker import publish_new_payment
from app.config import settings
from app.db import session_factory

log = logging.getLogger("outbox")


async def relay_once() -> int:
    async with session_factory() as session:
        async with session.begin():
            messages = await repository.fetch_unpublished_outbox(session, settings.outbox_batch_size)
            for message in messages:
                await publish_new_payment(message.payload)
            if messages:
                await repository.mark_outbox_published(session, [m.id for m in messages])
            return len(messages)


async def outbox_relay_loop() -> None:
    log.info("outbox relay started")
    while True:
        try:
            published = await relay_once()
            if published:
                log.info("published %d outbox message(s)", published)
        except Exception:  # noqa: BLE001
            log.exception("outbox relay cycle failed")
        await asyncio.sleep(settings.outbox_poll_interval_seconds)
