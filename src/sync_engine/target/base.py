from abc import ABC, abstractmethod

from sync_engine.models import Change


class SyncTarget(ABC):
    """Destination of synchronized state (see ADR-004).

    Both channels — webhook processor and reconciliation loop — write through
    this interface, so its contract is what makes redelivery safe.
    """

    @abstractmethod
    def apply(self, change: Change) -> bool:
        """Commit change if it is not older than the stored version.

        Contract:
        - Idempotent: applying the same change twice leaves the same state.
        - Last-writer-wins on ``updated_at``: a change older than the stored
          version is ignored, so out-of-order delivery cannot regress state.
        - On an ``updated_at`` tie, an authoritative (REST) change overwrites a
          non-authoritative one; otherwise the stored state is kept.
        - Deletions are stored as tombstones carrying their ``updated_at`` so
          a late, older update cannot resurrect the resource.
        - Returns True only once the change is durably committed; returns
          False when it was ignored as stale or redundant.

        Raises:
            TargetWriteError: the change could not be committed.
        """
