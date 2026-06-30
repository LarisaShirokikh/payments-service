import uuid

from app import outbox


class _FakeBegin:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def begin(self):
        return _FakeBegin()


class _Msg:
    def __init__(self, payload):
        self.id = uuid.uuid4()
        self.payload = payload


async def test_relay_publishes_and_marks(monkeypatch):
    messages = [_Msg({"payment_id": "a"}), _Msg({"payment_id": "b"})]
    published, marked = [], []

    async def fetch(session, limit):
        return messages

    async def mark(session, ids):
        marked.extend(ids)

    async def publish(payload):
        published.append(payload)

    monkeypatch.setattr(outbox, "session_factory", lambda: _FakeSession())
    monkeypatch.setattr(outbox.repository, "fetch_unpublished_outbox", fetch)
    monkeypatch.setattr(outbox.repository, "mark_outbox_published", mark)
    monkeypatch.setattr(outbox, "publish_new_payment", publish)

    count = await outbox.relay_once()

    assert count == 2
    assert published == [{"payment_id": "a"}, {"payment_id": "b"}]
    assert marked == [m.id for m in messages]


async def test_relay_does_nothing_when_empty(monkeypatch):
    published = []

    async def fetch(session, limit):
        return []

    async def mark(session, ids):
        raise AssertionError("mark should not be called when there is nothing to publish")

    async def publish(payload):
        published.append(payload)

    monkeypatch.setattr(outbox, "session_factory", lambda: _FakeSession())
    monkeypatch.setattr(outbox.repository, "fetch_unpublished_outbox", fetch)
    monkeypatch.setattr(outbox.repository, "mark_outbox_published", mark)
    monkeypatch.setattr(outbox, "publish_new_payment", publish)

    count = await outbox.relay_once()

    assert count == 0
    assert published == []
