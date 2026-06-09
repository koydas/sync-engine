import pytest

from sync_engine.exceptions import (
    DuplicateEventError,
    ReconciliationError,
    SyncError,
    WebhookSignatureError,
)


def test_webhook_signature_error_caught_as_sync_error():
    with pytest.raises(SyncError):
        raise WebhookSignatureError("invalid signature")


def test_duplicate_event_error_caught_as_sync_error():
    with pytest.raises(SyncError):
        raise DuplicateEventError("evt-123 already processed")


def test_reconciliation_error_caught_as_sync_error():
    with pytest.raises(SyncError):
        raise ReconciliationError("REST call failed")


def test_sync_error_caught_as_base_exception():
    with pytest.raises(Exception):
        raise SyncError("base error")
