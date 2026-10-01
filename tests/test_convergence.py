"""Property-based convergence test across both channels.

Every other test exercises one failure mode in isolation. This one interleaves
them under random schedules — dropped, duplicated and reordered webhooks,
late-committed source rows, target write failures and process restarts — and
asserts the property the README headline claims: once the faults stop and a
final cycle runs, the target equals the source.
"""

import hashlib
import hmac
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from sync_engine.engine import SyncEngine
from sync_engine.exceptions import (
    DuplicateEventError,
    EngineNotReadyError,
    ReconciliationError,
    TargetWriteError,
)
from sync_engine.models import Change
from sync_engine.processor.processor import SyncProcessor
from sync_engine.reconciliation.loop import Reconciler
from sync_engine.reconciliation.source import ChangeSource
from sync_engine.store.memory import InMemoryStore
from sync_engine.target.memory import InMemoryTarget
from sync_engine.webhook.handler import WebhookHandler

SECRET = "convergence-secret"
EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
OVERLAP = timedelta(seconds=60)
RESOURCE_IDS = ["r1", "r2", "r3"]


def _sign(raw: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()


class Clock:
    def __init__(self) -> None:
        self.now = EPOCH

    def __call__(self) -> datetime:
        return self.now


class SourceOfTruth(ChangeSource):
    """REST side: returns the current state of every resource changed since."""

    def __init__(self) -> None:
        self.state: dict[str, Change] = {}
        self.fail = False

    def fetch_changes(self, since: datetime | None) -> Iterator[Change]:
        if self.fail:
            raise ReconciliationError("injected REST failure")
        for change in list(self.state.values()):
            if since is None or change.updated_at >= since:
                yield change


class FlakyTarget(InMemoryTarget):
    """InMemoryTarget whose writes fail while ``fail`` is set."""

    def __init__(self) -> None:
        super().__init__()
        self.fail = False

    def apply(self, change: Change) -> bool:
        if self.fail:
            raise TargetWriteError("injected target failure")
        return super().apply(change)


@dataclass
class World:
    clock: Clock = field(default_factory=Clock)
    source: SourceOfTruth = field(default_factory=SourceOfTruth)
    store: InMemoryStore = field(default_factory=InMemoryStore)
    target: FlakyTarget = field(default_factory=FlakyTarget)
    in_flight: list[tuple[str, dict]] = field(default_factory=list)
    next_event: int = 0
    engine: SyncEngine | None = None

    def build_engine(self) -> SyncEngine:
        """A fresh process over the same durable store and target."""
        return SyncEngine(
            WebhookHandler(self.store, secret=SECRET),
            SyncProcessor(self.store, self.target),
            Reconciler(
                self.store, self.source, self.target, overlap=OVERLAP, clock=self.clock
            ),
        )


# One step of a schedule: (kind, resource index, lag seconds, flag).
step = st.tuples(
    st.sampled_from(
        ["update", "delete", "deliver", "duplicate", "drop", "reconcile", "restart"]
    ),
    st.integers(min_value=0, max_value=len(RESOURCE_IDS) - 1),
    st.integers(min_value=0, max_value=int(OVERLAP.total_seconds())),
    st.booleans(),
)


def _mutate(world: World, resource_id: str, lag_s: int, deleted: bool) -> None:
    """Commit a new version on the source and emit its webhook.

    ``lag_s`` models a row committed late with an earlier ``updated_at`` (a
    long transaction), bounded by the reconciler's overlap margin.
    """
    world.clock.now += timedelta(seconds=30)
    previous = world.source.state.get(resource_id)
    updated_at = world.clock.now - timedelta(seconds=lag_s)
    if previous is not None and updated_at <= previous.updated_at:
        updated_at = previous.updated_at + timedelta(microseconds=1)
    world.next_event += 1
    version = {"v": world.next_event}
    world.source.state[resource_id] = Change(
        resource_id=resource_id,
        updated_at=updated_at,
        deleted=deleted,
        data={} if deleted else version,
        authoritative=True,
    )
    payload = {
        "id": resource_id,
        "updated_at": updated_at.isoformat(),
        "deleted": deleted,
        "data": {} if deleted else version,
    }
    world.in_flight.append((f"evt-{world.next_event}", payload))


def _deliver(world: World, index: int, keep: bool, faulty: bool) -> None:
    """Deliver an in-flight webhook, in any order, possibly while the target fails."""
    if not world.in_flight or world.engine is None:
        return
    event_id, payload = world.in_flight[index % len(world.in_flight)]
    if not keep:
        world.in_flight.remove((event_id, payload))
    raw = json.dumps(payload).encode()
    world.target.fail = faulty
    try:
        world.engine.receive(event_id, payload, raw, _sign(raw))
    except (DuplicateEventError, EngineNotReadyError):
        pass
    finally:
        world.target.fail = False


def _reconcile(world: World, faulty: bool) -> None:
    if world.engine is None:
        return
    world.clock.now += timedelta(seconds=1)
    world.source.fail = faulty
    try:
        world.engine.run_cycle()
    except ReconciliationError:
        pass
    finally:
        world.source.fail = False


def _restart(world: World, faulty: bool) -> None:
    """Crash the process and start a new one; startup may fail and stay closed."""
    world.engine = world.build_engine()
    world.clock.now += timedelta(seconds=1)
    world.target.fail = faulty
    try:
        world.engine.start()
    except ReconciliationError:
        pass
    finally:
        world.target.fail = False


@settings(
    max_examples=300,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(schedule=st.lists(step, max_size=60))
# Found by review: an older webhook delivered after reconciliation has moved the watermark
# past the resource. Too coordinated for uniform random search to hit reliably.
@example(
    schedule=[
        ("update", 0, 0, False),
        ("update", 0, 0, False),
        ("deliver", 1, 0, False),
        ("update", 1, 0, False),
        ("update", 2, 0, False),
        ("update", 1, 0, False),
        ("reconcile", 0, 0, False),
        ("deliver", 0, 0, False),
    ]
)
def test_target_after_random_faults_and_final_cycle_converges_to_source(schedule):
    world = World()
    world.engine = world.build_engine()
    world.engine.start()

    for kind, index, lag_s, flag in schedule:
        resource_id = RESOURCE_IDS[index]
        if kind == "update":
            _mutate(world, resource_id, lag_s, deleted=False)
        elif kind == "delete":
            _mutate(world, resource_id, lag_s, deleted=True)
        elif kind == "deliver":
            _deliver(world, index, keep=False, faulty=flag)
        elif kind == "duplicate":
            _deliver(world, index, keep=True, faulty=flag)
        elif kind == "drop":
            if world.in_flight:
                world.in_flight.pop(index % len(world.in_flight))
        elif kind == "reconcile":
            _reconcile(world, faulty=flag)
        elif kind == "restart":
            _restart(world, faulty=flag)

    # Faults stop: a healthy process runs one cycle past every source commit.
    world.engine = world.build_engine()
    world.clock.now += timedelta(seconds=1)
    world.engine.start()

    for resource_id in RESOURCE_IDS:
        expected = world.source.state.get(resource_id)
        expected_data = None if expected is None or expected.deleted else expected.data
        assert world.target.get(resource_id) == expected_data, resource_id
    assert world.store.dequeue_unacknowledged() == []


@settings(max_examples=300, deadline=None)
@given(
    data=st.data(),
    mutations=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=len(RESOURCE_IDS) - 1), st.booleans()
        ),
        min_size=1,
        max_size=30,
    ),
)
def test_target_after_all_webhooks_in_any_order_without_reconcile_matches_source(
    data, mutations
):
    """Webhook channel alone: no drops, no faults, no reconciliation after startup.

    The final reconcile in the property above re-reads recent changes from the
    source and can hide a bug confined to the webhook path (processor, dedup,
    last-writer-wins). Here every event is delivered in a random order with
    duplicates, and nothing else writes to the target.
    """
    world = World()
    world.engine = world.build_engine()
    world.engine.start()  # source is still empty: nothing to reconcile

    for index, deleted in mutations:
        _mutate(world, RESOURCE_IDS[index], lag_s=0, deleted=deleted)

    duplicates = data.draw(st.lists(st.sampled_from(world.in_flight), max_size=10))
    deliveries = data.draw(st.permutations(world.in_flight + duplicates))
    for event_id, payload in deliveries:
        raw = json.dumps(payload).encode()
        try:
            world.engine.receive(event_id, payload, raw, _sign(raw))
        except DuplicateEventError:
            pass

    for resource_id in RESOURCE_IDS:
        expected = world.source.state.get(resource_id)
        expected_data = None if expected is None or expected.deleted else expected.data
        assert world.target.get(resource_id) == expected_data, resource_id
    assert world.store.dequeue_unacknowledged() == []
