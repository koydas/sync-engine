class SyncError(Exception):
    """Base class for all sync-engine business exceptions."""


class WebhookSignatureError(SyncError):
    """Raised when a webhook payload fails HMAC signature verification."""


class DuplicateEventError(SyncError):
    """Raised when an event_id has already been processed (idempotency guard)."""


class ReconciliationError(SyncError):
    """Raised when the REST reconciliation loop encounters an unrecoverable error."""


class InvalidPayloadError(SyncError):
    """Raised when a webhook payload or REST item cannot be parsed into a Change."""


class TargetWriteError(SyncError):
    """Raised by a SyncTarget when a change cannot be committed to the target state."""


class EngineNotReadyError(SyncError):
    """Raised when a webhook arrives before startup recovery has completed."""
