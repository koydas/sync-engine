# sync-engine

Hybrid REST/webhook sync engine — push/pull coordination, idempotent processing, and failure recovery. Extracted from production integration patterns of `fullstack-pilot`.

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
│   └── adr/                    # Architecture Decision Records
│       └── ADR-001-hybrid-rest-webhook.md
├── src/
│   └── sync_engine/            # main package (upcoming)
│       ├── webhook/            # webhook reception and verification
│       ├── reconciliation/     # REST polling loop
│       ├── processor/          # idempotent event processing
│       └── store/              # sync state persistence
├── tests/
├── CLAUDE.md
└── README.md
```

---

## Architecture decisions

| ADR | Decision | Status |
|-----|----------|--------|
| [ADR-001](docs/adr/ADR-001-hybrid-rest-webhook.md) | Hybrid REST/webhook architecture | Accepted |

---

## Design invariants

- **Idempotency everywhere**: the same data can arrive twice (webhook + reconciliation). Every operation must be safe to replay.
- **Webhook assumed unreliable**: reconciliation is not optional — it is the primary safety net.
- **At-least-once delivery**: webhooks are acknowledged after commit, never before.
- **`last_successful_sync_at` is sacred**: this value is what allows any gap to be recomputed. Never overwrite it without completing the sync.

---

## Target integrations

Services from `fullstack-pilot` — details added to `src/` as implementations land.

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
