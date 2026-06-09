# Testing guide

## Running tests

```bash
pip install -e ".[dev]"
pytest          # all tests
pytest -v       # verbose
pytest tests/store/   # one subdirectory
```

---

## Layout

Tests mirror the source tree under `tests/`:

```
tests/
├── test_exceptions.py
├── store/
│   └── test_memory_store.py
├── webhook/
│   └── test_handler.py        # (upcoming)
├── reconciliation/
│   └── test_loop.py           # (upcoming)
└── processor/
    └── test_processor.py      # (upcoming)
```

Every new module in `src/sync_engine/<package>/` gets a matching test file
in `tests/<package>/`. No test file = the feature is not done.

---

## Naming

```
test_<what_is_tested>_<condition>_<expected_behavior>
```

One test per behavior, not per function. Examples:

```python
def test_get_last_sync_at_before_any_write_returns_none(): ...
def test_dequeue_unacknowledged_excludes_processed_events(): ...
def test_webhook_signature_error_caught_as_sync_error(): ...
```

---

## Fixtures

Define fixtures at the test-file level unless shared across multiple files, in
which case add them to a `conftest.py` in the relevant directory.

`InMemoryStore` is the canonical fixture for any test that touches the store:

```python
import pytest
from sync_engine.store.memory import InMemoryStore

@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()
```

---

## Mocking rules

### Webhook signature verification

Never depend on real secrets in tests. Patch the verification call:

```python
from unittest.mock import patch

def test_valid_webhook_is_queued(store):
    with patch("sync_engine.webhook.handler.verify_signature", return_value=True):
        ...
```

### REST API (reconciliation)

No network calls in CI. Patch `httpx.Client` or inject a fake transport:

```python
import httpx

def test_reconciliation_fetches_since_last_sync(store):
    def handler(request):
        return httpx.Response(200, json={"items": []})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    ...
```

---

## What to test

For each new module, cover at minimum:

| Scenario | Example |
|---|---|
| Happy path | event processed end-to-end |
| Idempotency | same `event_id` processed twice, second is a no-op |
| Pre-condition violated | invalid signature → `WebhookSignatureError` raised |
| State after failure | crash mid-processing → event still in `dequeue_unacknowledged` |

---

## What not to test

- Internal implementation details (private methods, internal dict structure).
- The abstract `SyncStore` interface directly — test it through `InMemoryStore`.
- Framework behavior (FastAPI routing, httpx serialization).
