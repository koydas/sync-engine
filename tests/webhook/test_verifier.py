import hashlib
import hmac

import pytest

from sync_engine.exceptions import WebhookSignatureError
from sync_engine.webhook.verifier import verify_hmac_sha256

SECRET = "test-secret"
PAYLOAD = b'{"event": "push"}'


def _make_sig(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def test_valid_signature_raises_nothing() -> None:
    sig = _make_sig(PAYLOAD, SECRET)
    verify_hmac_sha256(PAYLOAD, sig, SECRET)


def test_valid_signature_with_prefix_raises_nothing() -> None:
    sig = "sha256=" + _make_sig(PAYLOAD, SECRET)
    verify_hmac_sha256(PAYLOAD, sig, SECRET)


def test_tampered_payload_raises_signature_error() -> None:
    sig = _make_sig(PAYLOAD, SECRET)
    tampered = b'{"event": "delete"}'
    with pytest.raises(WebhookSignatureError):
        verify_hmac_sha256(tampered, sig, SECRET)


def test_missing_header_raises_signature_error() -> None:
    with pytest.raises(WebhookSignatureError):
        verify_hmac_sha256(PAYLOAD, "", SECRET)
