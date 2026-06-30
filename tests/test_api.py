import uuid

from app import repository
from tests.conftest import make_payment

URL = "/api/v1/payments"
AUTH = {"X-API-Key": "secret-api-key"}
CREATE_HEADERS = {**AUTH, "Idempotency-Key": "order-1"}
BODY = {"amount": "199.90", "currency": "EUR", "description": "Subscription", "metadata": {"order_id": 1}}


def test_create_requires_api_key(client):
    resp = client.post(URL, json=BODY, headers={"Idempotency-Key": "order-1"})
    assert resp.status_code == 422


def test_create_rejects_wrong_api_key(client):
    resp = client.post(URL, json=BODY, headers={"X-API-Key": "wrong", "Idempotency-Key": "order-1"})
    assert resp.status_code == 401


def test_create_returns_202(client, monkeypatch):
    payment = make_payment()

    async def no_existing(session, key):
        return None

    async def create(session, data, key):
        return payment

    monkeypatch.setattr(repository, "get_by_idempotency_key", no_existing)
    monkeypatch.setattr(repository, "create_payment_with_outbox", create)

    resp = client.post(URL, json=BODY, headers=CREATE_HEADERS)
    assert resp.status_code == 202
    body = resp.json()
    assert body["payment_id"] == str(payment.id)
    assert body["status"] == "pending"


def test_same_idempotency_key_returns_existing(client, monkeypatch):
    payment = make_payment()
    create_called = False

    async def existing(session, key):
        return payment

    async def create(session, data, key):
        nonlocal create_called
        create_called = True
        return payment

    monkeypatch.setattr(repository, "get_by_idempotency_key", existing)
    monkeypatch.setattr(repository, "create_payment_with_outbox", create)

    resp = client.post(URL, json=BODY, headers=CREATE_HEADERS)
    assert resp.status_code == 202
    assert resp.json()["payment_id"] == str(payment.id)
    assert create_called is False


def test_create_validates_body(client):
    resp = client.post(URL, json={"amount": "-5", "currency": "EUR"}, headers=CREATE_HEADERS)
    assert resp.status_code == 422


def test_get_unknown_payment_404(client, monkeypatch):
    async def none(session, payment_id):
        return None

    monkeypatch.setattr(repository, "get_payment", none)
    resp = client.get(f"{URL}/{uuid.uuid4()}", headers=AUTH)
    assert resp.status_code == 404


def test_get_payment_returns_details(client, monkeypatch):
    payment = make_payment(status="succeeded")

    async def get(session, payment_id):
        return payment

    monkeypatch.setattr(repository, "get_payment", get)
    resp = client.get(f"{URL}/{payment.id}", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "succeeded"
    assert body["metadata"] == payment.payment_metadata
