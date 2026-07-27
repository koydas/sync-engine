import logging

from sync_engine.exceptions import DuplicateEventError
from sync_engine.store.base import SyncStore
from sync_engine.webhook.verifier import verify_hmac_sha256

logger = logging.getLogger(__name__)


class WebhookHandler:
    def __init__(self, store: SyncStore, secret: str) -> None:
        self._store = store
        self._secret = secret

    def handle(
        self,
        event_id: str,
        payload: dict,
        raw_bytes: bytes,
        signature_header: str,
    ) -> None:
        """Verify, deduplicate, and enqueue an incoming webhook event.

        Raises:
            WebhookSignatureError: signature missing or invalid (logged at WARNING).
            DuplicateEventError: event_id already processed (logged at DEBUG).
        """
        # verify_hmac_sha256 already logs at WARNING and raises WebhookSignatureError
        verify_hmac_sha256(raw_bytes, signature_header, self._secret)

        if self._store.is_event_processed(event_id):
            logger.debug("Duplicate event received, skipping: %s", event_id)
            raise DuplicateEventError(f"Event already processed: {event_id}")

        already_queued = any(
            queued_id == event_id
            for queued_id, _ in self._store.dequeue_unacknowledged()
        )
        if already_queued:
            logger.debug("Duplicate event already queued, skipping: %s", event_id)
            raise DuplicateEventError(f"Event already queued: {event_id}")

        self._store.enqueue_webhook(event_id, payload)
