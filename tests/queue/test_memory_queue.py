import pytest

from sync_engine.queue.memory import InMemoryQueue


@pytest.fixture
def queue() -> InMemoryQueue:
    return InMemoryQueue()


def test_pull_before_any_push_returns_empty(queue):
    assert queue.pull(10) == []


def test_push_then_pull_returns_message(queue):
    queue.push("msg-1", {"event_id": "evt-1"})
    assert queue.pull(10) == [("msg-1", {"event_id": "evt-1"})]


def test_pull_respects_max_messages(queue):
    queue.push("msg-1", {"a": 1})
    queue.push("msg-2", {"a": 2})
    assert len(queue.pull(1)) == 1


def test_pull_does_not_remove_messages(queue):
    queue.push("msg-1", {"a": 1})
    queue.pull(10)
    assert queue.pull(10) == [("msg-1", {"a": 1})]


def test_delete_removes_message_from_subsequent_pull(queue):
    queue.push("msg-1", {"a": 1})
    queue.delete("msg-1")
    assert queue.pull(10) == []


def test_delete_unknown_message_id_is_noop(queue):
    queue.delete("does-not-exist")  # must not raise
