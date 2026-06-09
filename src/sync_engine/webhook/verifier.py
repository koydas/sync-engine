import hashlib
import hmac
import logging

from sync_engine.exceptions import WebhookSignatureError

logger = logging.getLogger(__name__)


def verify_hmac_sha256(payload_bytes: bytes, signature_header: str, secret: str) -> None:
    """Verify the HMAC-SHA256 signature of a webhook payload.

    Raises WebhookSignatureError if the header is missing or the signature does
    not match.  Uses hmac.compare_digest to prevent timing attacks.
    """
    if not signature_header:
        logger.warning("Webhook received with missing signature header")
        raise WebhookSignatureError("Missing signature header")

    expected = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()

    # Accept bare hex digest or "sha256=<hex>" prefix
    received = signature_header.removeprefix("sha256=")

    if not hmac.compare_digest(expected, received):
        logger.warning("Webhook signature mismatch")
        raise WebhookSignatureError("Signature mismatch")
