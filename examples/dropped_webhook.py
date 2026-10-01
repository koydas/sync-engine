"""A webhook is lost; the next reconciliation cycle fills the gap.

Run from the repo root after ``pip install -e .``:

    python examples/dropped_webhook.py

Everything is in memory: the "remote API" is a dict, so no network is needed.
"""

import hashlib
import hmac
import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from sync_engine.engine import SyncEngine
from sync_engine.models import Change
from sync_engine.processor.processor import SyncProcessor
from sync_engine.reconciliation.loop import Reconciler
from sync_engine.reconciliation.source import ChangeSource
from sync_engine.store.memory import InMemoryStore
from sync_engine.target.memory import InMemoryTarget
from sync_engine.webhook.handler import WebhookHandler

SECRET = "demo-secret"


class RemoteApi(ChangeSource):
    """Stands in for the provider's REST API: the source of truth."""

    def __init__(self) -> None:
        self.records: dict[str, Change] = {}

    def commit(self, resource_id: str, data: dict, at: datetime) -> dict:
        """Change a record on the provider side; return the webhook payload it emits."""
        self.records[resource_id] = Change(
            resource_id=resource_id, updated_at=at, data=data, authoritative=True
        )
        return {"id": resource_id, "updated_at": at.isoformat(), "data": data}

    def fetch_changes(self, since: datetime | None) -> Iterator[Change]:
        for change in self.records.values():
            if since is None or change.updated_at >= since:
                yield change


def send_webhook(engine: SyncEngine, event_id: str, payload: dict) -> None:
    raw = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    engine.receive(event_id, payload, raw, signature)


def main() -> InMemoryTarget:
    now = datetime(2026, 1, 1, 12, tzinfo=UTC)
    api, store, target = RemoteApi(), InMemoryStore(), InMemoryTarget()
    engine = SyncEngine(
        WebhookHandler(store, secret=SECRET),
        SyncProcessor(store, target),
        Reconciler(store, api, target, clock=lambda: now),
    )
    engine.start()

    # 1. Order 42 is created: the webhook arrives and is applied in real time.
    send_webhook(engine, "evt-1", api.commit("order-42", {"status": "paid"}, now))
    print("after webhook 1:  ", target.get("order-42"))

    # 2. Order 42 ships, but the provider's webhook never arrives.
    now += timedelta(minutes=1)
    api.commit("order-42", {"status": "shipped"}, now)
    print("webhook 2 dropped:", target.get("order-42"))

    # 3. The periodic reconciliation cycle reads the REST delta and catches up.
    now += timedelta(minutes=4)
    engine.run_cycle()
    print("after reconcile:  ", target.get("order-42"))
    return target


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    main()
