from abc import ABC, abstractmethod
from datetime import datetime


class SyncStore(ABC):
    @abstractmethod
    def get_last_sync_at(self) -> datetime | None:
        """Return the timestamp of the last confirmed successful sync, or None."""

    @abstractmethod
    def set_last_sync_at(self, dt: datetime) -> None:
        """Persist dt as the last successful sync timestamp.

        Must only be called after the sync has been fully committed — never
        at the start of a cycle (see invariant #3 in CLAUDE.md).
        """

    @abstractmethod
    def is_event_processed(self, event_id: str) -> bool:
        """Return True if event_id has already been committed (idempotency check)."""

    @abstractmethod
    def mark_event_processed(self, event_id: str) -> None:
        """Record event_id as processed. Call only after the payload is committed."""

    @abstractmethod
    def enqueue_webhook(self, event_id: str, payload: dict) -> None:
        """Persist a webhook payload before processing begins (at-least-once delivery)."""

    @abstractmethod
    def dequeue_unacknowledged(self) -> list[dict]:
        """Return all enqueued webhooks that have not yet been marked processed."""
