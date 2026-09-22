import hashlib
import hmac
import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from sync_engine.engine import SyncEngine
from sync_engine.exceptions import (
    DuplicateEventError,
    EngineNotReadyError,
    ReconciliationError,
    TargetWriteError,
    WebhookSignatureError,
)
from sync_engine.models import Change
from sync_engine.processor.processor import SyncProcessor
from sync_engine.reconciliation.loop import Reconciler
from sync_engine.reconciliation.source import ChangeSource
from sync_engine.store.memory import InMemoryStore
from sync_engine.target.memory import InMemoryTarget
from sync_engine.webhook.handler import WebhookHandler

SECRET = "engine-secret"
NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
PAYLOAD = {"id": "r1", "updated_at": "2026-01-01T11:00:00Z", "data": {"v": 1}}
RAW = json.dumps(PAYLOAD).encode()


def _sig(raw: bytes = RAW) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()


class FakeSource(ChangeSource):
    def __init__(self, changes: list[Change] | None = None) -> None:
        self.changes = changes or []
        self.fail = False
        self.calls = 0

    def fetch_changes(self, since: datetime | None) -> Iterator[Change]:
        self.calls += 1
        if self.fail:
            raise ReconciliationError("REST down")
        yield from self.changes


class ToggleTarget(InMemoryTarget):
    def __init__(self) -> None:
        super().__init__()
        self.fail = False

    def apply(self, change: Change) -> bool:
        if self.fail:
            raise TargetWriteError("target down")
        return super().apply(change)


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def target() -> ToggleTarget:
    return ToggleTarget()


@pytest.fixture
def source() -> FakeSource:
    return FakeSource()


@pytest.fixture
def engine(
    store: InMemoryStore, target: ToggleTarget, source: FakeSource
) -> SyncEngine:
    return SyncEngine(
        WebhookHandler(store, SECRET),
        SyncProcessor(store, target),
        Reconciler(store, source, target, clock=lambda: NOW),
    )


def test_receive_before_start_raises_not_ready(
    engine: SyncEngine, store: InMemoryStore
) -> None:
    with pytest.raises(EngineNotReadyError):
        engine.receive("evt-1", PAYLOAD, RAW, _sig())

    assert store.dequeue_unacknowledged() == []


def test_start_replays_queue_then_reconciles_then_opens_channel(
    engine: SyncEngine,
    store: InMemoryStore,
    target: ToggleTarget,
    source: FakeSource,
) -> None:
    store.enqueue_webhook("evt-0", PAYLOAD)
    source.changes = [
        Change("r2", NOW - timedelta(minutes=1), data={"v": 2}, authoritative=True)
    ]

    replay = engine.start()

    assert replay.processed == ["evt-0"]
    assert target.get("r1") == {"v": 1}
    assert target.get("r2") == {"v": 2}
    assert store.get_last_sync_at() == NOW
    assert engine.ready is True


def test_start_gap_fill_failure_keeps_channel_closed(
    engine: SyncEngine, source: FakeSource
) -> None:
    source.fail = True

    with pytest.raises(ReconciliationError):
        engine.start()

    assert engine.ready is False


def test_receive_valid_webhook_applies_and_acknowledges(
    engine: SyncEngine, store: InMemoryStore, target: ToggleTarget
) -> None:
    engine.start()

    assert engine.receive("evt-1", PAYLOAD, RAW, _sig()) is True

    assert target.get("r1") == {"v": 1}
    assert store.is_event_processed("evt-1")


def test_receive_redelivered_webhook_raises_duplicate(engine: SyncEngine) -> None:
    engine.start()
    engine.receive("evt-1", PAYLOAD, RAW, _sig())

    with pytest.raises(DuplicateEventError):
        engine.receive("evt-1", PAYLOAD, RAW, _sig())


def test_receive_bad_signature_raises_and_queues_nothing(
    engine: SyncEngine, store: InMemoryStore
) -> None:
    engine.start()

    with pytest.raises(WebhookSignatureError):
        engine.receive("evt-1", PAYLOAD, RAW, "sha256=deadbeef")

    assert store.dequeue_unacknowledged() == []


def test_receive_processing_failure_keeps_event_for_next_cycle(
    engine: SyncEngine, store: InMemoryStore, target: ToggleTarget
) -> None:
    engine.start()
    target.fail = True

    assert engine.receive("evt-1", PAYLOAD, RAW, _sig()) is False
    assert store.dequeue_unacknowledged() == [("evt-1", PAYLOAD)]

    target.fail = False
    replay = engine.run_cycle()

    assert replay.processed == ["evt-1"]
    assert target.get("r1") == {"v": 1}


def test_run_periodic_failed_cycle_is_retried_until_stopped(
    store: InMemoryStore, target: ToggleTarget, source: FakeSource
) -> None:
    source.fail = True
    stop = threading.Event()
    cycles = 0

    def clock() -> datetime:
        nonlocal cycles
        cycles += 1
        if cycles == 2:
            stop.set()
        return NOW

    engine = SyncEngine(
        WebhookHandler(store, SECRET),
        SyncProcessor(store, target),
        Reconciler(store, source, target, clock=clock),
    )

    engine.run_periodic(timedelta(0), stop)

    assert source.calls == 2
