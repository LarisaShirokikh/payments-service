import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app


def make_payment(**overrides):
    data = dict(
        id=uuid.uuid4(),
        amount=Decimal("199.90"),
        currency="EUR",
        description="Subscription",
        payment_metadata={"order_id": 1},
        status="pending",
        idempotency_key="order-1",
        webhook_url=None,
        created_at=datetime.now(timezone.utc),
        processed_at=None,
    )
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.fixture
def client():
    async def _no_session():
        yield None

    app.dependency_overrides[get_session] = _no_session
    yield TestClient(app)  # no context manager -> app lifespan (broker/outbox) is not started
    app.dependency_overrides.clear()
