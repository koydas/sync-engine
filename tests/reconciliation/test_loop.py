from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from sync_engine.exceptions import ReconciliationError, TargetWriteError
from sync_engine.models import Change
from sync_engine.reconciliation.loop import Reconciler
from sync_engine.reconciliation.source import ChangeSource
from sync_engine.store.memory import InMemoryStore
from sync_engine.target.memory import InMemoryTarget

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
OVERLAP = timedelta(seconds=60)


def _change(resource_id: str = "r1", v: int = 1) -> Change:
    return Change(
        resource_id=resource_id,
        updated_at=NOW - timedelta(minutes=1),
        data={"v": v},
        authoritative=True,
    )


class FakeSource(ChangeSource):
    def __init__(self, changes: list[Change], fail_after: int | None = None) -> None:
        self.changes = changes
        self.fail_after = fail_after
        self.calls: list[datetime | None] = []

    def fetch_changes(self, since: datetime | None) -> Iterator[Change]:
        self.calls.append(since)
        for i, change in enumerate(self.changes):
            if self.fail_after is not None and i == self.fail_after:
                raise ReconciliationError("REST fetch failed mid-page")
            yield change


class FailingTarget(InMemoryTarget):
    def apply(self, change: Change) -> bool:
        raise TargetWriteError("disk full")


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def target() -> InMemoryTarget:
    return InMemoryTarget()


def _reconciler(store, source, target, clock=lambda: NOW) -> Reconciler:
    return Reconciler(store, source, target, overlap=OVERLAP, clock=clock)


def test_run_once_without_watermark_requests_full_snapshot(
    store: InMemoryStore, target: InMemoryTarget
) -> None:
    source = FakeSource([_change()])

    applied = _reconciler(store, source, target).run_once()

    assert source.calls == [None]
    assert applied == 1
    assert target.get("r1") == {"v": 1}


def test_run_once_with_watermark_queries_since_watermark_minus_overlap(
    store: InMemoryStore, target: InMemoryTarget
) -> None:
    watermark = NOW - timedelta(minutes=10)
    store.set_last_sync_at(watermark)
    source = FakeSource([])

    _reconciler(store, source, target).run_once()

    assert source.calls == [watermark - OVERLAP]


def test_run_once_success_advances_watermark_to_cycle_start(
    store: InMemoryStore, target: InMemoryTarget
) -> None:
    ticks = iter([NOW, NOW + timedelta(minutes=5)])

    _reconciler(store, FakeSource([_change()]), target, lambda: next(ticks)).run_once()

    assert store.get_last_sync_at() == NOW


def test_run_once_fetch_failure_keeps_watermark_and_raises(
    store: InMemoryStore, target: InMemoryTarget
) -> None:
    watermark = NOW - timedelta(minutes=10)
    store.set_last_sync_at(watermark)
    source = FakeSource([_change("r1"), _change("r2")], fail_after=1)

    with pytest.raises(ReconciliationError):
        _reconciler(store, source, target).run_once()

    assert store.get_last_sync_at() == watermark


def test_run_once_target_failure_wraps_error_and_keeps_watermark(
    store: InMemoryStore,
) -> None:
    with pytest.raises(ReconciliationError, match="Target write failed"):
        _reconciler(store, FakeSource([_change()]), FailingTarget()).run_once()

    assert store.get_last_sync_at() is None


def test_run_once_replayed_window_is_idempotent(
    store: InMemoryStore, target: InMemoryTarget
) -> None:
    source = FakeSource([_change()])
    reconciler = _reconciler(store, source, target)

    assert reconciler.run_once() == 1
    assert reconciler.run_once() == 0
    assert target.get("r1") == {"v": 1}


def test_run_once_clock_behind_watermark_does_not_move_it_backwards(
    store: InMemoryStore, target: InMemoryTarget
) -> None:
    watermark = NOW + timedelta(hours=1)
    store.set_last_sync_at(watermark)

    _reconciler(store, FakeSource([]), target).run_once()

    assert store.get_last_sync_at() == watermark


def test_reconciler_negative_overlap_raises_value_error(
    store: InMemoryStore, target: InMemoryTarget
) -> None:
    with pytest.raises(ValueError):
        Reconciler(store, FakeSource([]), target, overlap=timedelta(seconds=-1))
