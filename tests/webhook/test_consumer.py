import hashlib
import hmac

import pytest

from sync_engine.queue.memory import InMemoryQueue
from sync_engine.store.memory import InMemoryStore
from sync_engine.webhook.consumer import QueueConsumer
from sync_engine.webhook.handler import WebhookHandler

SECRET = "consumer-secret"
EVENT_ID = "evt-001"
PAYLOAD = {"action": "opened"}
RAW = '{"action": "opened"}'


def _sig(raw: str = RAW, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()


def _envelope(
    event_id: str = EVENT_ID,
    payload: dict = PAYLOAD,
    raw: str = RAW,
    signature: str | None = None,
) -> dict:
    return {
        "event_id": event_id,
        "payload": payload,
        "raw": raw,
        "signature": signature if signature is not None else _sig(raw),
    }


@pytest.fixture()
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture()
def queue() -> InMemoryQueue:
    return InMemoryQueue()


@pytest.fixture()
def consumer(store: InMemoryStore, queue: InMemoryQueue) -> QueueConsumer:
    return QueueConsumer(queue, WebhookHandler(store, SECRET))


def test_valid_message_is_enqueued_locally_and_deleted_from_queue(
    store: InMemoryStore, queue: InMemoryQueue, consumer: QueueConsumer
) -> None:
    queue.push("msg-1", _envelope())

    consumer.poll_once()

    assert store.dequeue_unacknowledged() == [(EVENT_ID, PAYLOAD)]
    assert queue.pull(10) == []


def test_bad_signature_is_deleted_and_not_enqueued_locally(
    store: InMemoryStore, queue: InMemoryQueue, consumer: QueueConsumer
) -> None:
    queue.push("msg-1", _envelope(signature="bad-sig"))

    consumer.poll_once()

    assert store.dequeue_unacknowledged() == []
    assert queue.pull(10) == []


def test_duplicate_event_is_deleted_and_not_reenqueued(
    store: InMemoryStore, queue: InMemoryQueue, consumer: QueueConsumer
) -> None:
    store.mark_event_processed(EVENT_ID)
    queue.push("msg-1", _envelope())

    consumer.poll_once()

    assert store.dequeue_unacknowledged() == []
    assert queue.pull(10) == []


def test_unexpected_handler_failure_leaves_message_on_queue(
    queue: InMemoryQueue,
) -> None:
    class FailingStore(InMemoryStore):
        def enqueue_webhook(self, event_id: str, payload: dict) -> None:
            raise RuntimeError("store unavailable")

    consumer = QueueConsumer(queue, WebhookHandler(FailingStore(), SECRET))
    envelope = _envelope()
    queue.push("msg-1", envelope)

    with pytest.raises(RuntimeError):
        consumer.poll_once()

    assert queue.pull(10) == [("msg-1", envelope)]


def test_poll_once_processes_every_pulled_message(
    store: InMemoryStore, queue: InMemoryQueue, consumer: QueueConsumer
) -> None:
    queue.push("msg-1", _envelope(event_id="evt-1", payload={"a": 1}, raw='{"a": 1}'))
    queue.push("msg-2", _envelope(event_id="evt-2", payload={"a": 2}, raw='{"a": 2}'))

    consumer.poll_once()

    processed_ids = [event_id for event_id, _ in store.dequeue_unacknowledged()]
    assert processed_ids == ["evt-1", "evt-2"]
    assert queue.pull(10) == []
