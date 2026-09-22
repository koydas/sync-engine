import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sync_engine.exceptions import SyncError
from sync_engine.models import Change
from sync_engine.store.base import SyncStore
from sync_engine.target.base import SyncTarget

logger = logging.getLogger(__name__)

PayloadParser = Callable[[dict[str, Any]], Change]


@dataclass
class ReplayResult:
    processed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


class SyncProcessor:
    """Apply queued webhook events to the target, exactly once per event_id."""

    def __init__(
        self,
        store: SyncStore,
        target: SyncTarget,
        parse: PayloadParser = Change.from_dict,
    ) -> None:
        self._store = store
        self._target = target
        self._parse = parse

    def process(self, event_id: str, payload: dict[str, Any]) -> bool:
        """Apply one queued event and acknowledge it after commit.

        Returns False if event_id was already processed (no-op), True otherwise.

        Raises:
            InvalidPayloadError: payload cannot be parsed; the event stays queued.
            TargetWriteError: the target write failed; the event stays queued.
        """
        if self._store.is_event_processed(event_id):
            logger.debug("Event already processed, skipping: %s", event_id)
            return False

        change = self._parse(payload)
        applied = self._target.apply(change)
        # Acknowledge only after the target write has returned (invariant #2).
        self._store.mark_event_processed(event_id)
        logger.info(
            "Processed event %s for resource %s (applied=%s)",
            event_id,
            change.resource_id,
            applied,
        )
        return True

    def replay_unacknowledged(self) -> ReplayResult:
        """Replay every queued event not yet acknowledged (crash recovery).

        A failing event is logged and left in the queue; it does not block the
        others, since the target's version guard makes their order irrelevant.
        """
        result = ReplayResult()
        for event_id, payload in self._store.dequeue_unacknowledged():
            try:
                self.process(event_id, payload)
            except SyncError:
                logger.exception(
                    "Replay failed for event %s; left unacknowledged", event_id
                )
                result.failed.append(event_id)
            else:
                result.processed.append(event_id)
        logger.info(
            "Replay finished: %d processed, %d failed",
            len(result.processed),
            len(result.failed),
        )
        return result
