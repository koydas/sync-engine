# sync-engine

[![CI](https://github.com/koydas/sync-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/koydas/sync-engine/actions/workflows/ci.yml)

**Webhooks drop events. Polling is late. This engine assumes both and still converges.**

A Python sync engine for keeping a local copy of a remote system's state: webhooks for real time, REST reconciliation for everything they miss, and a write contract that makes the two channels safe to overlap. Patterns extracted from production integrations (queue-based POS ingestion, ERP ↔ SaaS synchronization).

## The failure modes it's built around

Every integration eventually hits these. Each row is a decision record and a test, not a promise.

| What goes wrong | What the engine does | Decided in | Proven by |
|---|---|---|---|
| The provider delivers the same webhook twice | Dedup by `event_id` before enqueue; a processed id is never applied again | [ADR-001](docs/adr/ADR-001-hybrid-rest-webhook.md) | `test_receive_redelivered_webhook_raises_duplicate` |
| A webhook never arrives | Periodic REST reconciliation from a watermark fills the gap | [ADR-005](docs/adr/ADR-005-reconciliation-watermark-and-startup-order.md) | `test_run_once_with_watermark_queries_since_watermark_minus_overlap` |
| An older update arrives after a newer one | Versioned last-writer-wins on the source's `updated_at` | [ADR-004](docs/adr/ADR-004-versioned-target-write-contract.md) | `test_apply_older_change_after_newer_is_ignored` |
| A late update resurrects a deleted record | Deletions are tombstones carrying their version | [ADR-004](docs/adr/ADR-004-versioned-target-write-contract.md) | `test_apply_older_update_after_delete_does_not_resurrect` |
| Webhook and REST disagree at the same timestamp | Deterministic tie-break: the REST read is authoritative, a webhook never overwrites on a tie | [ADR-004](docs/adr/ADR-004-versioned-target-write-contract.md) | `test_apply_tie_*` (4 tests) |
| Rows committed during a reconciliation cycle are skipped forever | Watermark = cycle **start**, re-queried with an overlap margin; safe because writes are idempotent | [ADR-005](docs/adr/ADR-005-reconciliation-watermark-and-startup-order.md) | `test_run_once_success_advances_watermark_to_cycle_start`, `test_run_once_replayed_window_is_idempotent` |
| A cycle fails halfway and the watermark moves anyway | The watermark only advances after every page and every write succeed; it never moves backwards | [ADR-005](docs/adr/ADR-005-reconciliation-watermark-and-startup-order.md) | `test_run_once_fetch_failure_keeps_watermark_and_raises`, `test_run_once_clock_behind_watermark_does_not_move_it_backwards` |
| The process crashes between write and acknowledgement | Ack after commit only; unacknowledged events are replayed at startup and on every tick | [ADR-005](docs/adr/ADR-005-reconciliation-watermark-and-startup-order.md) | `test_receive_processing_failure_keeps_event_for_next_cycle` |
| Webhooks are processed before the target has caught up after downtime | Startup order: replay queue → gap-fill → only then open the webhook channel | [ADR-005](docs/adr/ADR-005-reconciliation-watermark-and-startup-order.md) | `test_start_replays_queue_then_reconciles_then_opens_channel` |
| A paginated API loops on the same cursor | A repeated cursor aborts the cycle instead of spinning | — | `test_fetch_changes_repeated_cursor_raises_reconciliation_error` |
| Someone forges a webhook | HMAC-SHA256, constant-time comparison, rejected before anything is queued | [ADR-003](docs/adr/ADR-003-webhook-hmac-sha256-signature-verification.md) | `test_receive_bad_signature_raises_and_queues_nothing` |

87 tests, no network, in-memory store and target. Scope today: the engine core. The HTTP route and production `SyncStore` / `SyncTarget` backends are not part of the package yet (see [Wiring](#wiring)).

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
# setup
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# tests
pytest

# linting
ruff check src/ tests/
```
