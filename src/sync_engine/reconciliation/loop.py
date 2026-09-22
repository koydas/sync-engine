import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sync_engine.exceptions import ReconciliationError, SyncError
from sync_engine.reconciliation.source import ChangeSource
from sync_engine.store.base import SyncStore
from sync_engine.target.base import SyncTarget

logger = logging.getLogger(__name__)

DEFAULT_OVERLAP = timedelta(seconds=60)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Reconciler:
    """REST delta poll that fills whatever the webhook channel missed (ADR-005).

    Each cycle queries ``updated_since = last_successful_sync_at - overlap``
    and, only once every change is committed, advances the watermark to the
    instant the cycle *started*. Changes made while the cycle was running are
    therefore re-read next cycle; the target's version guard makes that safe.
    """

    def __init__(
        self,
        store: SyncStore,
        source: ChangeSource,
        target: SyncTarget,
        overlap: timedelta = DEFAULT_OVERLAP,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if overlap < timedelta(0):
            raise ValueError("overlap must be non-negative")
        self._store = store
        self._source = source
        self._target = target
        self._overlap = overlap
        self._clock = clock

    def run_once(self) -> int:
        """Run one reconciliation cycle; return the number of changes applied.

        Raises:
            ReconciliationError: the fetch or a target write failed. The
                watermark is left untouched, so the next cycle retries the
                same window (invariant #3).
        """
        started_at = self._clock()
        last_sync_at = self._store.get_last_sync_at()
        since = None if last_sync_at is None else last_sync_at - self._overlap
        logger.info(
            "Reconciliation started (since=%s)",
            since.isoformat() if since else "snapshot",
        )

        applied = 0
        try:
            for change in self._source.fetch_changes(since):
                if self._target.apply(change):
                    applied += 1
        except ReconciliationError:
            logger.error("Reconciliation aborted; watermark unchanged")
            raise
        except SyncError as exc:
            logger.error(
                "Reconciliation aborted on target write; watermark unchanged: %s", exc
            )
            raise ReconciliationError(
                f"Target write failed during reconciliation: {exc}"
            ) from exc

        # Never move the watermark backwards (e.g. host clock stepped back).
        if last_sync_at is None or started_at > last_sync_at:
            self._store.set_last_sync_at(started_at)
        logger.info("Reconciliation complete: %d change(s) applied", applied)
        return applied
