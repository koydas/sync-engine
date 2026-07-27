import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient

from sync_engine.app import create_app
from sync_engine.store.memory import InMemoryStore

SECRET = "test-secret"


def _sig(payload: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def client(store: InMemoryStore) -> TestClient:
    return TestClient(create_app(store=store, secret=SECRET))


def test_health_before_any_sync_reports_no_last_sync_at(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "last_sync_at": None}


def test_webhook_valid_signature_is_enqueued(
    client: TestClient, store: InMemoryStore
) -> None:
    body = b'{"type": "created"}'
    response = client.post(
        "/webhooks",
        content=body,
        headers={"X-Event-Id": "evt-1", "X-Hub-Signature-256": _sig(body)},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert ("evt-1", {"type": "created"}) in store.dequeue_unacknowledged()


def test_webhook_invalid_signature_returns_401_and_not_enqueued(
    client: TestClient, store: InMemoryStore
) -> None:
    body = b'{"type": "created"}'
    response = client.post(
        "/webhooks",
        content=body,
        headers={
            "X-Event-Id": "evt-1",
            "X-Hub-Signature-256": _sig(body, secret="wrong-secret"),
        },
    )
    assert response.status_code == 401
    assert store.dequeue_unacknowledged() == []


def test_webhook_missing_event_id_header_returns_400(client: TestClient) -> None:
    body = b'{"type": "created"}'
    response = client.post(
        "/webhooks",
        content=body,
        headers={"X-Hub-Signature-256": _sig(body)},
    )
    assert response.status_code == 400


def test_webhook_already_processed_event_returns_duplicate_status(
    client: TestClient, store: InMemoryStore
) -> None:
    body = b'{"type": "created"}'
    headers = {"X-Event-Id": "evt-1", "X-Hub-Signature-256": _sig(body)}

    client.post("/webhooks", content=body, headers=headers)
    store.mark_event_processed("evt-1")

    response = client.post("/webhooks", content=body, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"status": "duplicate"}
