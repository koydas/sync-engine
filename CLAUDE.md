# CLAUDE.md — sync-engine

Project conventions for Claude Code sessions.

---

## Architecture

This project follows a hybrid REST/webhook architecture documented in [ADR-001](docs/adr/ADR-001-hybrid-rest-webhook.md).

**Before implementing anything**, read the relevant ADR. If an implementation decision contradicts an existing ADR, create a new ADR rather than silently modifying the code.

---

## Package structure

```
src/sync_engine/
├── webhook/        # Reception, HMAC verification, queuing
├── reconciliation/ # REST loop, delta computation, gap fill
├── processor/      # Idempotent processing, deduplication by event_id
└── store/          # Persistence: last_successful_sync_at, event queue
```

Each package has a single responsibility. Do not let reconciliation logic bleed into the webhook handler and vice versa.

---

## Invariants — never violate

1. **Idempotency**: every sync operation must be replayable without side effects. Use `event_id` as the deduplication key.
2. **Acknowledge after commit**: mark a webhook as processed only after the target state has been written.
3. **`last_successful_sync_at`**: updated only after a complete, error-free sync. Never at the start of a cycle.
4. **Webhook signature required**: reject any webhook without a valid signature before inserting it into the queue.

---

## Code conventions

- Python 3.11+, type hints everywhere.
- `ruff` for linting, `black` for formatting — no custom configuration.
- No `print()` in application code — use `logging` with explicit levels.
- Business exceptions inherit from a `SyncError` base class (to be defined in `src/sync_engine/exceptions.py`).
- No silent `try/except Exception` — always log or re-raise.

---

## Tests

**Every new module must ship with tests. A feature without a test file is not done.**

Full guide: [docs/testing.md](docs/testing.md).

- Framework: `pytest` — run with `pytest` from the repo root.
- Test files mirror the source tree: `src/sync_engine/store/base.py` → `tests/store/test_*.py`.
- One test per behavior, not per function.
- Naming: `test_<what_is_tested>_<condition>_<expected_behavior>`.
- Webhook tests mock signature verification (never depend on secrets).
- Reconciliation tests mock the REST API (no network calls in CI).
- Use `InMemoryStore` as the store fixture — never a real backend.

---

## ADRs

- Directory: `docs/adr/`
- Format: `ADR-NNN-short-title.md`
- Sequential numbering, no reuse.
- Valid statuses: `Proposed` | `Accepted` | `Deprecated` | `Superseded by ADR-NNN`
- An ADR is not modified after acceptance — create a superseding ADR instead.

### When to write a new ADR

After every implementation session, ask: *did this introduce an architectural decision not covered by an existing ADR?*

Write a new ADR when the decision:
- Chooses between two or more structurally different approaches (e.g. abstract interface vs. concrete dependency, REST vs. event-driven).
- Has cross-cutting consequences — it constrains how multiple packages or future implementations must behave.
- Would be non-obvious to reverse without touching many files.

Do **not** write an ADR for:
- Code conventions already documented in this file (exception hierarchy, naming, formatting).
- Single-file implementation choices with no downstream constraints.
- Bug fixes or adjustments to existing decisions.

If a new implementation *contradicts* an existing ADR, the new ADR must reference it with status `Superseded by ADR-NNN`.

### Current ADR index

| ADR | Title | Status |
|---|---|---|
| [ADR-001](docs/adr/ADR-001-hybrid-rest-webhook.md) | Hybrid REST/webhook architecture | Accepted |
| [ADR-002](docs/adr/ADR-002-pluggable-store-interface.md) | Pluggable store interface via abstract base class | Accepted |

---

## Git

- Current development branch: `claude/sync-engine-bootstrap-wkdEx`
- Commit messages in English, imperative mood, no trailing period.
- Format: `<type>: <description>` — types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
- Do not commit secrets, `.env` files, or tokens.

---

## PR review workflow

After pushing a PR branch:

1. Read all open review threads (`get_review_comments`).
2. For each thread: apply the fix, reply with the commit SHA and a one-line explanation, then resolve the thread.
3. Once all threads are resolved, post `@codex review` as a top-level PR comment to trigger a follow-up automated review.
