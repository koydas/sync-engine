from sync_engine.models import Change
from sync_engine.target.base import SyncTarget


class InMemoryTarget(SyncTarget):
    """In-memory SyncTarget implementation — for tests only, no persistence."""

    def __init__(self) -> None:
        self._records: dict[str, Change] = {}

    def apply(self, change: Change) -> bool:
        current = self._records.get(change.resource_id)
        if current is not None:
            if change.updated_at < current.updated_at:
                return False
            if change.updated_at == current.updated_at and not (
                change.authoritative and change != current
            ):
                return False
        self._records[change.resource_id] = change
        return True

    def get(self, resource_id: str) -> dict | None:
        """Return the live data for resource_id, or None if absent or deleted."""
        record = self._records.get(resource_id)
        if record is None or record.deleted:
            return None
        return record.data
