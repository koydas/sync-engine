# ADR-004 — Versioned, idempotent write contract for the sync target

**Status**: Accepted  
**Date**: 2026-09-22  
**Deciders**: sync-engine maintainers

---

## Context

ADR-001 requires both channels — webhook processor and REST reconciliation — to write the same target state, and accepts that "the same change may arrive twice". It also states that webhooks carry no ordering guarantee (an `updated` may arrive before its `created`) and that REST arbitrates conflicts. ADR-002 abstracts the *sync bookkeeping* store (`last_successful_sync_at`, queue, processed ids) but says nothing about where synchronized data is written, nor how a write must behave under redelivery and reordering.

`event_id` deduplication (invariant #1) only covers exact webhook redelivery. It does not cover:

- the same resource change arriving once by webhook and once by REST (different channels, no shared `event_id`);
- two distinct events for the same resource arriving out of order;
- a reconciliation window re-read after a failed cycle or through the overlap margin (ADR-005).

Two options were considered:

1. **Order at the edges** — sequence events before applying them (per-resource queue, buffering until predecessors arrive).
2. **Make the write commutative** — each write carries the source-side version and the target keeps the newest one.

---

## Decision

We define `SyncTarget` as an ABC in `src/sync_engine/target/base.py` with a single method, `apply(change: Change) -> bool`, and a strict contract:

| Rule | Behavior |
|---|---|
| Version | `Change.updated_at` (source-side, timezone-aware) is the resource version |
| Last-writer-wins | A change older than the stored version is ignored |
| Tie-break | On equal `updated_at`, an `authoritative` (REST) change overwrites any differing stored state — webhook or earlier REST read; a webhook change never overwrites on a tie |
| Tombstones | Deletions are stored with their `updated_at`, so a late, older update cannot resurrect the resource |
| Idempotency | Re-applying a stored change is a no-op and returns `False` |
| Commit signal | `True` only once the change is durably committed; failures raise `TargetWriteError` |

`Change` (`src/sync_engine/models.py`) is the channel-neutral unit both paths produce. Naive `updated_at` values are rejected at parse time (`InvalidPayloadError`): they cannot be ordered against aware ones.

The processor acknowledges an event (`mark_event_processed`) after `apply()` returns, including when the change was ignored as stale — a stale event is *handled*, not failed.

---

## Why not ordering at the edges

- The two channels have no shared sequence number; ordering across them would require a global sequencer the sources do not provide.
- Buffering until predecessors arrive needs a timeout, after which the engine must guess — exactly the silent-loss mode ADR-001 exists to remove.
- A commutative write makes delivery order irrelevant, so replay, gap fill and overlap re-reads all become safe by construction.

---

## Consequences

**Positive:**
- Any interleaving of webhook, replay and reconciliation converges to the newest source state.
- The overlap window in ADR-005 and replay-after-crash need no extra deduplication logic.
- `InMemoryTarget` (`target/memory.py`) implements the contract for tests; production targets implement the same ABC.

**Negative / accepted costs:**
- Correctness depends on the source's `updated_at` being monotonic per resource. Sources that only expose second-level precision can produce ties; the REST tie-break resolves those in favor of the source of truth. Between two REST reads at the same version, the later read wins: reconciliation reads in time order, so keeping the first would freeze a value the source has since changed without bumping its timestamp.
- Tombstones are kept indefinitely; a compaction policy is out of scope.
- A production target must implement compare-and-set atomically (e.g. `UPDATE ... WHERE updated_at <= :new`), not read-then-write, once writers run concurrently.

---

## Rejected alternatives

| Alternative | Reason for rejection |
|---|---|
| Per-resource ordering queue | Needs a sequencer the sources do not provide; timeout-based guessing reintroduces silent loss |
| Deduplicate by `event_id` only | Does not cover cross-channel duplicates or reordering |
| Content hash comparison | Detects duplicates but cannot order two different versions |
