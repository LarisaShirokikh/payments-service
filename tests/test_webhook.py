import pytest

from app import consumer
from app.config import settings


class _FakeResponse:
    def raise_for_status(self):
        return None


class _FakeClient:
    def __init__(self, fail_first: int):
        self.fail_first = fail_first
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None):
        self.calls += 1
        if self.calls <= self.fail_first:
            raise RuntimeError("network error")
        return _FakeResponse()


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    async def _sleep(*args, **kwargs):
        return None

    monkeypatch.setattr(consumer.asyncio, "sleep", _sleep)


async def test_webhook_succeeds_after_retries(monkeypatch):
    fake = _FakeClient(fail_first=2)
    monkeypatch.setattr(consumer.httpx, "AsyncClient", lambda *a, **k: fake)

    await consumer._deliver_webhook("http://example/hook", {"x": 1})

    assert fake.calls == 3  # two failures, third succeeds


async def test_webhook_gives_up_after_max_attempts(monkeypatch):
    fake = _FakeClient(fail_first=99)
    monkeypatch.setattr(consumer.httpx, "AsyncClient", lambda *a, **k: fake)

    with pytest.raises(Exception):
        await consumer._deliver_webhook("http://example/hook", {"x": 1})

    assert fake.calls == settings.webhook_max_attempts
