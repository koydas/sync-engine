from datetime import datetime

from sync_engine.store.base import SyncStore


class InMemoryStore(SyncStore):
    """In-memory SyncStore implementation — for tests only, no persistence."""

    def __init__(self) -> None:
        self._last_sync_at: datetime | None = None
        self._processed: set[str] = set()
        self._queue: dict[str, dict] = {}

    def get_last_sync_at(self) -> datetime | None:
        return self._last_sync_at

    def set_last_sync_at(self, dt: datetime) -> None:
        self._last_sync_at = dt

    def is_event_processed(self, event_id: str) -> bool:
        return event_id in self._processed

    def mark_event_processed(self, event_id: str) -> None:
        self._processed.add(event_id)

    def enqueue_webhook(self, event_id: str, payload: dict) -> None:
        self._queue[event_id] = payload

    def dequeue_unacknowledged(self) -> list[tuple[str, dict]]:
        return [
            (event_id, payload)
            for event_id, payload in self._queue.items()
            if event_id not in self._processed
        ]
