import hashlib
import hmac

import pytest

from sync_engine.exceptions import DuplicateEventError, WebhookSignatureError
from sync_engine.store.memory import InMemoryStore
from sync_engine.webhook.handler import WebhookHandler

SECRET = "handler-secret"
EVENT_ID = "evt-001"
PAYLOAD = {"action": "opened"}
RAW = b'{"action": "opened"}'


def _sig(payload: bytes = RAW, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


@pytest.fixture()
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture()
def handler(store: InMemoryStore) -> WebhookHandler:
    return WebhookHandler(store, SECRET)


def test_valid_event_is_enqueued(store: InMemoryStore, handler: WebhookHandler) -> None:
    handler.handle(EVENT_ID, PAYLOAD, RAW, _sig())

    unacked = store.dequeue_unacknowledged()
    assert len(unacked) == 1
    assert unacked[0] == (EVENT_ID, PAYLOAD)


def test_duplicate_event_raises_and_not_reenqueued(
    store: InMemoryStore, handler: WebhookHandler
) -> None:
    store.mark_event_processed(EVENT_ID)

    with pytest.raises(DuplicateEventError):
        handler.handle(EVENT_ID, PAYLOAD, RAW, _sig())

    assert store.dequeue_unacknowledged() == []


def test_bad_signature_raises_and_not_enqueued(
    store: InMemoryStore, handler: WebhookHandler
) -> None:
    with pytest.raises(WebhookSignatureError):
        handler.handle(EVENT_ID, PAYLOAD, RAW, "bad-sig")

    assert store.dequeue_unacknowledged() == []
