class SyncError(Exception):
    """Base class for all sync-engine business exceptions."""


class WebhookSignatureError(SyncError):
    """Raised when a webhook payload fails HMAC signature verification."""


class DuplicateEventError(SyncError):
    """Raised when an event_id has already been processed (idempotency guard)."""


class ReconciliationError(SyncError):
    """Raised when the REST reconciliation loop encounters an unrecoverable error."""
