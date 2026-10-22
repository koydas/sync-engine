---
name: new-adr
description: Procedure for adding an ADR to sync-engine — decide whether one is needed, next sequential number, required format and status, index update in CLAUDE.md, superseding instead of editing.
---

1. **Needed?** Yes if the decision picks between structurally different approaches, constrains several packages/future implementations, or is costly to reverse. No for conventions already in `CLAUDE.md`, single-file choices, bug fixes.
2. **Contradicts an existing ADR?** Never edit an accepted ADR. New ADR references it; the old one's status becomes `Superseded by ADR-NNN` (that status line is the only permitted edit).
3. **File**: `docs/adr/ADR-NNN-short-title.md`, NNN = next number in `docs/adr/` (no reuse). Model it on `ADR-005`: `# ADR-NNN — Title`, `**Status**` (`Proposed` | `Accepted` | `Deprecated` | `Superseded by ADR-NNN`), `**Date**`, `**Deciders**`, then Context / Decision / Consequences. Name the code paths (`src/sync_engine/...`) the decision binds.
4. **Index**: add a row to the "Current ADR index" table in `CLAUDE.md`.
5. If the ADR changes behavior, the tests land in the same change (see `add-sync-module`).
