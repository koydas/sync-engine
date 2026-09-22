# sync-engine

[![CI](https://github.com/koydas/sync-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/koydas/sync-engine/actions/workflows/ci.yml)

Hybrid REST/webhook sync engine — push/pull coordination, idempotent processing, and failure recovery. Extracted from production integration patterns (queue-based POS ingestion, ERP ↔ SaaS synchronization).

---

## Blueprint

```
Source (REST API / Webhook)
        │
        ▼
┌───────────────────┐
│   Webhook Handler │  ◄── primary channel (real-time)
│   (verify + queue)│
└────────┬──────────┘
         │
         ▼
┌───────────────────┐     ┌─────────────────────┐
│  Sync Processor   │◄────│  Reconciliation Loop │  ◄── recovery channel
│  (idempotent)     │     │  (REST delta poll)   │
└────────┬──────────┘     └─────────────────────┘
         │
         ▼
┌───────────────────┐
│   Target Store    │
│   (local state)   │
└───────────────────┘
```

**Core principle**: webhooks propagate changes in real time; REST fills the gaps. See [ADR-001](docs/adr/ADR-001-hybrid-rest-webhook.md).

---

## Structure

```
sync-engine/
├── docs/
│   └── adr/                    # Architecture Decision Records (ADR-001 → ADR-005)
├── src/
│   └── sync_engine/
│       ├── webhook/            # HMAC verification, dedup guard, enqueue
│       ├── processor/          # exactly-once apply per event_id, crash replay
│       ├── reconciliation/     # REST source (cursor pagination) + watermark loop
│       ├── target/             # versioned last-writer-wins writes, tombstones
│       ├── store/              # sync bookkeeping: watermark, queue, processed ids
│       ├── models.py           # Change — channel-neutral unit
│       └── engine.py           # startup order: replay → gap fill → open webhooks
├── tests/
├── CLAUDE.md
└── README.md
```

---

## Architecture decisions

| ADR | Decision | Status |
|-----|----------|--------|
| [ADR-001](docs/adr/ADR-001-hybrid-rest-webhook.md) | Hybrid REST/webhook architecture | Accepted |
| [ADR-002](docs/adr/ADR-002-pluggable-store-interface.md) | Pluggable store interface via abstract base class | Accepted |
| [ADR-003](docs/adr/ADR-003-webhook-hmac-sha256-signature-verification.md) | HMAC-SHA256 webhook signature verification | Accepted |
| [ADR-004](docs/adr/ADR-004-versioned-target-write-contract.md) | Versioned, idempotent write contract for the sync target | Accepted |
| [ADR-005](docs/adr/ADR-005-reconciliation-watermark-and-startup-order.md) | Reconciliation watermark and startup recovery order | Accepted |

---

## Design invariants

- **Idempotency everywhere**: the same data can arrive twice (webhook + reconciliation). Every operation must be safe to replay.
- **Webhook assumed unreliable**: reconciliation is not optional — it is the primary safety net.
- **At-least-once delivery**: webhooks are acknowledged after commit, never before.
- **`last_successful_sync_at` is sacred**: this value is what allows any gap to be recomputed. Never overwrite it without completing the sync.

---

## Wiring

```python
store, target = MyStore(), MyTarget()          # implement SyncStore / SyncTarget
engine = SyncEngine(
    WebhookHandler(store, secret=WEBHOOK_SECRET),
    SyncProcessor(store, target),
    Reconciler(store, RestChangeSource(httpx.Client(base_url=API), "/resources"), target),
)
engine.start()                                  # replay queue, gap fill, then accept webhooks
engine.receive(event_id, payload, raw_body, signature_header)   # from the HTTP layer
engine.run_periodic(timedelta(minutes=5), stop_event)           # replay + reconcile each tick
```

The HTTP layer (FastAPI route) and production `SyncStore`/`SyncTarget` backends are not part of this package yet.

---

## Development

```bash
# setup (upcoming)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# tests
pytest

# linting
ruff check src/ tests/
```
