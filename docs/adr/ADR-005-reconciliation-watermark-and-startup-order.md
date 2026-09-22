# ADR-005 — Reconciliation watermark and startup recovery order

**Status**: Accepted  
**Date**: 2026-09-22  
**Deciders**: sync-engine maintainers

---

## Context

ADR-001 defines the reconciliation loop as a light poll on `updated_since = last_sync_at` and a gap fill on restart, and invariant #3 forbids advancing `last_successful_sync_at` before a sync fully succeeds. It does not specify:

1. **Which instant becomes the new watermark** after a successful cycle.
2. **How clock skew** between the engine and the source is absorbed.
3. **In which order** the replay worker (scenario 3), the gap fill (scenario 2) and the webhook channel start.

Getting (1) or (2) wrong loses changes silently — the exact failure ADR-001 exists to prevent.

---

## Decision

### Watermark = cycle start, queried with an overlap margin

`Reconciler.run_once()` (`src/sync_engine/reconciliation/loop.py`):

1. Captures `started_at` from the engine clock **before** fetching.
2. Queries `updated_since = last_successful_sync_at - overlap` (default 60 s), or a full snapshot when no watermark exists.
3. Applies every change through `SyncTarget.apply()`.
4. Only if every page and every write succeeded, sets `last_successful_sync_at = started_at`. It never moves the watermark backwards.

Any failure raises `ReconciliationError` and leaves the watermark untouched, so the next cycle retries the same window.

### Startup and periodic cycle order

`SyncEngine` (`src/sync_engine/engine.py`):

1. `start()` → replay unacknowledged queue → gap-fill reconciliation → open the webhook channel (`ready = True`).
2. `receive()` before `ready` raises `EngineNotReadyError`; the sender retries and reconciliation covers the change regardless.
3. `run_periodic()` repeats *replay + reconcile* on every tick, so an event whose nominal processing failed is retried without a restart.

---

## Why cycle start and not the alternatives

| Candidate watermark | Failure mode |
|---|---|
| Cycle end (`now()` after the fetch) | Changes written on the source while the cycle ran are skipped forever |
| Max `updated_at` seen | An empty window never advances; a source that commits out of `updated_at` order (long transactions) loses rows committed late with an earlier timestamp |
| Cycle start, no overlap | Engine/source clock skew or late-committed rows fall between two windows |
| **Cycle start − overlap** | Re-reads up to `overlap` of data every cycle — safe because writes are idempotent and versioned (ADR-004) |

Replay runs before gap fill because queued events are older than the REST state; with ADR-004 both orders converge, but this order avoids applying a stale event that REST would then immediately overwrite. The webhook channel opens last so no nominal event is processed against a target that has not yet caught up.

---

## Consequences

**Positive:**
- No change can fall between two windows as long as clock skew plus commit latency stays under `overlap`.
- A failed cycle is self-healing: same window, next tick.
- Crash recovery, outage recovery and nominal retries share one code path (`run_cycle()`).

**Negative / accepted costs:**
- Every cycle re-reads `overlap` worth of changes. Cost is bounded and traded for correctness.
- Skew larger than `overlap` can still lose changes; `overlap` must be tuned per source.
- Webhooks are rejected during startup recovery; senders without retry depend on the next reconciliation window.
- A persistently invalid queued event is retried every cycle; dead-lettering is out of scope and left to a future ADR.
