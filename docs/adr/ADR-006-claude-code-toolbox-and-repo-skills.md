# ADR-006 — Claude Code toolbox and repo-local skills

**Status**: Accepted  
**Date**: 2026-10-22  
**Deciders**: sync-engine maintainers

---

## Context

Sessions in this repo had no declared tooling: no PR review/fix commands, and the procedures that `CLAUDE.md` describes in prose (when to write an ADR, how to add a module with its tests) had to be re-derived each time. The cross-repo decision is [ai-dev-tools ADR-018](https://github.com/koydas/ai-dev-tools/blob/main/docs/adr/ADR-018-consumer-repo-adoption.md).

## Decision

1. `.claude/settings.json` enables the `ai-dev-tools` plugin (`koydas/ai-dev-tools` marketplace).
2. Invariants and conventions stay in `CLAUDE.md` (always loaded). Procedures live in `.claude/skills/`: `new-adr` (decision criteria, numbering, index, superseding) and `add-sync-module` (placement, invariants, exceptions, mirrored tests, ruff/black/pytest).
3. Skills link to `CLAUDE.md` and `docs/testing.md`; they do not restate invariants. If a skill and `CLAUDE.md` disagree, `CLAUDE.md` wins and the skill is fixed.
4. Cloud sessions get the commands from the environment setup script, not from this repo. Documented in [`docs/claude-code.md`](../claude-code.md).

## Consequences

- Reviews and fixes run through the same toolbox as the other repos; repo rules take precedence over its defaults.
- No effect on the runtime package, the invariants, or CI.
- Skills can drift from `CLAUDE.md`; mitigation is item 3 and review of both together.
