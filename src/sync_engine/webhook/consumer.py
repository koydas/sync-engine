import logging

from sync_engine.exceptions import DuplicateEventError, WebhookSignatureError
from sync_engine.queue.base import SyncQueue
from sync_engine.webhook.handler import WebhookHandler

logger = logging.getLogger(__name__)


class QueueConsumer:
    """Bridges queue-based ingestion (ADR-004) to WebhookHandler (ADR-001/003).

    Pulls event envelopes from a SyncQueue and hands each one to
    WebhookHandler.handle() unchanged — verification, deduplication, and
    local enqueueing keep working exactly as they do for a directly pushed
    webhook. Each envelope is a dict with the four values handle() expects:
    "event_id", "payload", "raw" (the exact bytes/string that were signed),
    and "signature".

    A message is deleted from the queue only once its outcome is final:
    WebhookHandler enqueued it locally, or rejected it for a reason
    redelivery cannot change (bad signature, duplicate event). Any other
    failure (e.g. the local store is unavailable) leaves the message on the
    queue for redelivery.
    """

    def __init__(self, queue: SyncQueue, handler: WebhookHandler) -> None:
        self._queue = queue
        self._handler = handler

    def poll_once(self, max_messages: int = 10) -> None:
        """Pull up to max_messages pending events and process each one."""
        for message_id, envelope in self._queue.pull(max_messages):
            self._consume(message_id, envelope)

    def _consume(self, message_id: str, envelope: dict) -> None:
        raw = envelope["raw"]
        raw_bytes = raw.encode() if isinstance(raw, str) else raw

        try:
            self._handler.handle(
                envelope["event_id"],
                envelope["payload"],
                raw_bytes,
                envelope["signature"],
            )
        except (WebhookSignatureError, DuplicateEventError):
            # Already logged by verify_hmac_sha256 / WebhookHandler. The
            # rejection is deterministic, so redelivery would not change the
            # outcome — acknowledge and move on.
            logger.debug("Dropping rejected message from queue: %s", message_id)
            self._queue.delete(message_id)
            return

        self._queue.delete(message_id)
