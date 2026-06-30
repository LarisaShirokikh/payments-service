import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.auth import require_api_key
from app.db import get_session
from app.schemas import PaymentAccepted, PaymentCreate, PaymentResponse

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])


@router.post("/payments", status_code=status.HTTP_202_ACCEPTED, response_model=PaymentAccepted)
async def create_payment(
    data: PaymentCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
) -> PaymentAccepted:
    existing = await repository.get_by_idempotency_key(session, idempotency_key)
    if existing is not None:
        return PaymentAccepted(payment_id=existing.id, status=existing.status, created_at=existing.created_at)
    payment = await repository.create_payment_with_outbox(session, data, idempotency_key)
    return PaymentAccepted(payment_id=payment.id, status=payment.status, created_at=payment.created_at)


@router.get("/payments/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> PaymentResponse:
    payment = await repository.get_payment(session, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return payment
