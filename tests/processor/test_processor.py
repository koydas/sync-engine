import pytest

from sync_engine.exceptions import InvalidPayloadError, TargetWriteError
from sync_engine.models import Change
from sync_engine.processor.processor import SyncProcessor
from sync_engine.store.memory import InMemoryStore
from sync_engine.target.memory import InMemoryTarget

PAYLOAD = {"id": "r1", "updated_at": "2026-01-01T12:00:00Z", "data": {"v": 1}}


class FailingTarget(InMemoryTarget):
    """Fails for the listed resource ids, delegates to InMemoryTarget otherwise."""

    def __init__(self, failing_ids: set[str]) -> None:
        super().__init__()
        self.failing_ids = failing_ids

    def apply(self, change: Change) -> bool:
        if change.resource_id in self.failing_ids:
            raise TargetWriteError(f"write failed for {change.resource_id}")
        return super().apply(change)


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def target() -> InMemoryTarget:
    return InMemoryTarget()


@pytest.fixture
def processor(store: InMemoryStore, target: InMemoryTarget) -> SyncProcessor:
    return SyncProcessor(store, target)


def test_process_queued_event_applies_and_acknowledges(
    store: InMemoryStore, target: InMemoryTarget, processor: SyncProcessor
) -> None:
    store.enqueue_webhook("evt-1", PAYLOAD)

    assert processor.process("evt-1", PAYLOAD) is True

    assert target.get("r1") == {"v": 1}
    assert store.is_event_processed("evt-1")
    assert store.dequeue_unacknowledged() == []


def test_process_already_processed_event_is_noop(
    store: InMemoryStore, target: InMemoryTarget, processor: SyncProcessor
) -> None:
    store.mark_event_processed("evt-1")

    assert processor.process("evt-1", PAYLOAD) is False
    assert target.get("r1") is None


def test_process_target_failure_leaves_event_unacknowledged(
    store: InMemoryStore,
) -> None:
    processor = SyncProcessor(store, FailingTarget({"r1"}))
    store.enqueue_webhook("evt-1", PAYLOAD)

    with pytest.raises(TargetWriteError):
        processor.process("evt-1", PAYLOAD)

    assert not store.is_event_processed("evt-1")
    assert store.dequeue_unacknowledged() == [("evt-1", PAYLOAD)]


def test_process_invalid_payload_leaves_event_unacknowledged(
    store: InMemoryStore, processor: SyncProcessor
) -> None:
    store.enqueue_webhook("evt-1", {"action": "opened"})

    with pytest.raises(InvalidPayloadError):
        processor.process("evt-1", {"action": "opened"})

    assert not store.is_event_processed("evt-1")


def test_process_stale_event_is_acknowledged_without_regressing_target(
    store: InMemoryStore, target: InMemoryTarget, processor: SyncProcessor
) -> None:
    newer = {**PAYLOAD, "updated_at": "2026-01-01T13:00:00Z", "data": {"v": 2}}
    processor.process("evt-2", newer)

    assert processor.process("evt-1", PAYLOAD) is True

    assert target.get("r1") == {"v": 2}
    assert store.is_event_processed("evt-1")


def test_process_custom_parser_is_used(
    store: InMemoryStore, target: InMemoryTarget
) -> None:
    def parse(payload: dict) -> Change:
        return Change.from_dict(payload["resource"])

    processor = SyncProcessor(store, target, parse=parse)

    processor.process("evt-1", {"resource": PAYLOAD})

    assert target.get("r1") == {"v": 1}


def test_replay_unacknowledged_processes_every_queued_event(
    store: InMemoryStore, target: InMemoryTarget, processor: SyncProcessor
) -> None:
    store.enqueue_webhook("evt-1", PAYLOAD)
    store.enqueue_webhook("evt-2", {**PAYLOAD, "id": "r2"})

    result = processor.replay_unacknowledged()

    assert result.processed == ["evt-1", "evt-2"]
    assert result.failed == []
    assert store.dequeue_unacknowledged() == []
    assert target.get("r2") == {"v": 1}


def test_replay_unacknowledged_failure_does_not_block_other_events(
    store: InMemoryStore,
) -> None:
    target = FailingTarget({"r1"})
    processor = SyncProcessor(store, target)
    store.enqueue_webhook("evt-1", PAYLOAD)
    store.enqueue_webhook("evt-2", {**PAYLOAD, "id": "r2"})

    result = processor.replay_unacknowledged()

    assert result.processed == ["evt-2"]
    assert result.failed == ["evt-1"]
    assert store.dequeue_unacknowledged() == [("evt-1", PAYLOAD)]
    assert target.get("r2") == {"v": 1}


def test_replay_unacknowledged_empty_queue_returns_empty_result(
    processor: SyncProcessor,
) -> None:
    result = processor.replay_unacknowledged()

    assert result.processed == []
    assert result.failed == []
