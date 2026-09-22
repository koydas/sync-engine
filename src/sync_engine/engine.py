import logging
import threading
from datetime import timedelta
from typing import Any

from sync_engine.exceptions import EngineNotReadyError, ReconciliationError, SyncError
from sync_engine.processor.processor import ReplayResult, SyncProcessor
from sync_engine.reconciliation.loop import Reconciler
from sync_engine.webhook.handler import WebhookHandler

logger = logging.getLogger(__name__)


class SyncEngine:
    """Wire both channels together and enforce the startup order of ADR-001.

    ``start()`` replays the unacknowledged queue (crash mid-processing), then
    runs a gap-fill reconciliation (extended outage). Only after both succeed
    does ``receive()`` accept webhooks.
    """

    def __init__(
        self,
        handler: WebhookHandler,
        processor: SyncProcessor,
        reconciler: Reconciler,
    ) -> None:
        self._handler = handler
        self._processor = processor
        self._reconciler = reconciler
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    def start(self) -> ReplayResult:
        """Recover state, then open the webhook channel.

        Raises:
            ReconciliationError: gap fill failed; the engine stays not ready.
        """
        replay = self.run_cycle()
        self._ready = True
        logger.info("Sync engine ready; webhook channel open")
        return replay

    def run_cycle(self) -> ReplayResult:
        """Replay unacknowledged events, then reconcile against REST.

        Raises:
            ReconciliationError: the reconciliation step failed.
        """
        replay = self._processor.replay_unacknowledged()
        self._reconciler.run_once()
        return replay

    def run_periodic(self, interval: timedelta, stop: threading.Event) -> None:
        """Run a cycle every interval until stop is set; a failed cycle is retried next tick."""
        while not stop.wait(interval.total_seconds()):
            try:
                self.run_cycle()
            except ReconciliationError:
                logger.warning("Sync cycle failed; retrying in %s", interval)

    def receive(
        self,
        event_id: str,
        payload: dict[str, Any],
        raw_bytes: bytes,
        signature_header: str,
    ) -> bool:
        """Nominal path: verify + enqueue, then process immediately.

        Returns True if the event was applied now, False if it was queued but
        processing failed — it stays unacknowledged for the next replay.

        Raises:
            EngineNotReadyError: startup recovery has not completed; the sender
                should retry (reconciliation covers it regardless).
            WebhookSignatureError: invalid signature; nothing was queued.
            DuplicateEventError: event already processed or queued.
        """
        if not self._ready:
            raise EngineNotReadyError(
                "Webhook received before startup recovery completed"
            )

        self._handler.handle(event_id, payload, raw_bytes, signature_header)
        try:
            self._processor.process(event_id, payload)
        except SyncError:
            logger.exception(
                "Processing failed for event %s; queued for replay", event_id
            )
            return False
        return True
