import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import PaymentStatus
from app.models import OutboxMessage, Payment
from app.schemas import PaymentCreate


async def get_payment(session: AsyncSession, payment_id: uuid.UUID) -> Payment | None:
    return await session.get(Payment, payment_id)


async def get_by_idempotency_key(session: AsyncSession, key: str) -> Payment | None:
    result = await session.execute(select(Payment).where(Payment.idempotency_key == key))
    return result.scalar_one_or_none()


async def create_payment_with_outbox(
    session: AsyncSession, data: PaymentCreate, idempotency_key: str
) -> Payment:
    payment = Payment(
        amount=data.amount,
        currency=data.currency.value,
        description=data.description,
        payment_metadata=data.metadata,
        idempotency_key=idempotency_key,
        webhook_url=str(data.webhook_url) if data.webhook_url else None,
        status=PaymentStatus.PENDING.value,
    )
    session.add(payment)
    await session.flush()
    session.add(
        OutboxMessage(
            aggregate_id=payment.id,
            event_type="payment.created",
            payload={"payment_id": str(payment.id)},
        )
    )
    await session.commit()
    await session.refresh(payment)
    return payment


async def fetch_unpublished_outbox(session: AsyncSession, limit: int) -> list[OutboxMessage]:
    result = await session.execute(
        select(OutboxMessage)
        .where(OutboxMessage.published_at.is_(None))
        .order_by(OutboxMessage.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(result.scalars().all())


async def mark_outbox_published(session: AsyncSession, ids: list[uuid.UUID]) -> None:
    await session.execute(
        update(OutboxMessage).where(OutboxMessage.id.in_(ids)).values(published_at=datetime.now(timezone.utc))
    )


async def mark_payment_processed(
    session: AsyncSession, payment_id: uuid.UUID, status: PaymentStatus
) -> Payment | None:
    payment = await session.get(Payment, payment_id)
    if payment is None or payment.status != PaymentStatus.PENDING.value:
        return payment
    payment.status = status.value
    payment.processed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(payment)
    return payment
