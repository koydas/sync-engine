---
name: add-sync-module
description: Checklist for adding or changing a module under src/sync_engine — package placement, invariants, exceptions, mirrored tests with InMemoryStore and real HMAC, local checks matching CI.
---

1. **Placement**: one responsibility per package (`webhook/`, `reconciliation/`, `processor/`, `store/`, `target/`). No reconciliation logic in the webhook handler, nor the reverse. Read the governing ADR first (index in `CLAUDE.md`).
2. **Invariants** (`CLAUDE.md`): replayable by `event_id`; acknowledge only after the target write; `last_successful_sync_at` moves only after a fully error-free cycle; signature verified before queue insertion.
3. **Code**: Python 3.11+, full type hints, `logging` (no `print`), errors inherit `SyncError` (`src/sync_engine/exceptions.py`), no silent `except Exception`.
4. **Tests** (`docs/testing.md`): `tests/<same path>/test_*.py`; one test per behavior; `test_<what>_<condition>_<expected>`; `InMemoryStore` fixture; REST mocked; webhook tests sign with a fixture secret via the real verifier. A module without a test file is not done.
5. **Local gate = CI** (`.github/workflows/`): `ruff check .` · `black --check .` · `pytest`.
