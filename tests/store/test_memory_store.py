from datetime import datetime, timezone

import pytest

from sync_engine.store.memory import InMemoryStore


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


def test_get_last_sync_at_before_any_write_returns_none(store):
    assert store.get_last_sync_at() is None


def test_set_last_sync_at_get_returns_same_value(store):
    dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    store.set_last_sync_at(dt)
    assert store.get_last_sync_at() == dt


def test_set_last_sync_at_overwrites_previous_value(store):
    first = datetime(2026, 1, 1, tzinfo=timezone.utc)
    second = datetime(2026, 6, 1, tzinfo=timezone.utc)
    store.set_last_sync_at(first)
    store.set_last_sync_at(second)
    assert store.get_last_sync_at() == second


def test_is_event_processed_unknown_event_returns_false(store):
    assert store.is_event_processed("evt-123") is False


def test_is_event_processed_after_mark_returns_true(store):
    store.mark_event_processed("evt-123")
    assert store.is_event_processed("evt-123") is True


def test_mark_event_processed_called_twice_is_idempotent(store):
    store.mark_event_processed("evt-123")
    store.mark_event_processed("evt-123")
    assert store.is_event_processed("evt-123") is True


def test_enqueue_webhook_appears_in_dequeue_unacknowledged(store):
    store.enqueue_webhook("evt-1", {"type": "created"})
    assert ("evt-1", {"type": "created"}) in store.dequeue_unacknowledged()


def test_dequeue_unacknowledged_returns_event_id_alongside_payload(store):
    store.enqueue_webhook("evt-1", {"type": "created"})
    event_id, payload = store.dequeue_unacknowledged()[0]
    assert event_id == "evt-1"
    assert payload == {"type": "created"}


def test_dequeue_unacknowledged_empty_before_any_enqueue(store):
    assert store.dequeue_unacknowledged() == []


def test_dequeue_unacknowledged_excludes_processed_events(store):
    store.enqueue_webhook("evt-1", {"type": "created"})
    store.mark_event_processed("evt-1")
    assert store.dequeue_unacknowledged() == []


def test_dequeue_unacknowledged_returns_only_unprocessed_from_mixed_queue(store):
    store.enqueue_webhook("evt-1", {"type": "created"})
    store.enqueue_webhook("evt-2", {"type": "updated"})
    store.mark_event_processed("evt-1")
    event_ids = [eid for eid, _ in store.dequeue_unacknowledged()]
    assert "evt-1" not in event_ids
    assert "evt-2" in event_ids
