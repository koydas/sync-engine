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

- Framework: `pytest`
- One test per behavior, not per function.
- Webhook tests mock signature verification (do not depend on secrets in tests).
- Reconciliation tests mock the REST API (no network calls in CI).
- Naming: `test_<what_is_tested>_<condition>_<expected_behavior>`.

---

## ADRs

- Directory: `docs/adr/`
- Format: `ADR-NNN-short-title.md`
- Sequential numbering, no reuse.
- Valid statuses: `Proposed` | `Accepted` | `Deprecated` | `Superseded by ADR-NNN`
- An ADR is not modified after acceptance — create a superseding ADR instead.

---

## Git

- Current development branch: `claude/sync-engine-bootstrap-wkdEx`
- Commit messages in English, imperative mood, no trailing period.
- Format: `<type>: <description>` — types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
- Do not commit secrets, `.env` files, or tokens.
