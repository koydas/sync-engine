# ADR-002 — Pluggable store interface via abstract base class

**Status**: Accepted  
**Date**: 2026-06-09  
**Deciders**: fullstack-pilot team

---

## Context

ADR-001 establishes that a persistent store is required for two things:

1. `last_successful_sync_at` — used by the reconciliation loop to compute the missed-event window after an outage.
2. The webhook queue — at-least-once delivery buffer that survives a crash between reception and processing.

ADR-001 does not specify the implementation technology or how the rest of the engine should depend on the store. Two options were considered:

1. **Concrete dependency** — engine components import and instantiate a specific backend directly (e.g. SQLite helper, Redis client).
2. **Abstract interface** — engine components depend on a Python ABC; the concrete backend is injected at startup.

---

## Decision

We define `SyncStore` as a Python abstract base class (`abc.ABC`) in `src/sync_engine/store/base.py`. All engine components — webhook handler, reconciliation loop, processor — interact exclusively with this interface. No engine code imports a concrete backend.

The interface surface is intentionally minimal (six methods):

| Method | Purpose |
|---|---|
| `get_last_sync_at()` | Read the recovery timestamp |
| `set_last_sync_at(dt)` | Write it after a confirmed commit |
| `is_event_processed(event_id)` | Idempotency check before processing |
| `mark_event_processed(event_id)` | Acknowledge after commit |
| `enqueue_webhook(event_id, payload)` | Persist before processing begins |
| `dequeue_unacknowledged()` | Replay buffer on recovery |

`dequeue_unacknowledged` returns `list[tuple[str, dict]]` — event_id is always returned alongside the payload so callers can acknowledge without the payload embedding its own ID.

---

## Why not a concrete dependency

- **Test coupling**: any concrete backend (SQLite, Redis) requires setup, teardown, and I/O in tests. An in-memory implementation behind the same interface eliminates all of that.
- **Migration cost**: coupling engine logic to a specific backend turns a backend swap into a cross-cutting refactor. With an interface, only a new implementation file is needed.
- **Invariant enforcement**: the interface is the right place to document the commit-before-acknowledge invariants (see CLAUDE.md §Invariants). Concrete classes are not readable enough for this.

---

## Consequences

**Positive:**
- `InMemoryStore` (`store/memory.py`) satisfies the interface for all tests — no I/O, no fixtures, no external process.
- Production backends (SQLite, Redis, Postgres) are drop-in replacements — they implement the ABC and are injected at startup.
- Engine invariants (acknowledge-after-commit, last_sync_at write-only-after-success) are enforced at the call site by convention documented on the interface, not scattered across backends.

**Negative / accepted costs:**
- Dependency injection must be wired at startup — the concrete backend is not self-instantiated.
- Adding a new persistence operation requires updating the ABC and every implementation, not just one file.

---

## Rejected alternatives

| Alternative | Reason for rejection |
|---|---|
| Hardcoded SQLite backend | Tight coupling; tests require a real file; migration is cross-cutting |
| Dataclass / TypedDict (no ABC) | No enforcement of the interface contract; silent drift between implementations |
| Repository pattern with separate read/write interfaces | Over-engineering for current scope; a single interface covers all six operations cleanly |
