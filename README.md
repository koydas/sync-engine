# sync-engine

Moteur de synchronisation hybride REST/webhook — coordination push/pull, traitement idempotent, et récupération après panne. Extrait de patterns production réels des intégrations `fullstack-pilot`.

---

## Blueprint

```
Source (REST API / Webhook)
        │
        ▼
┌───────────────────┐
│   Webhook Handler │  ◄── canal primaire (temps réel)
│   (verify + queue)│
└────────┬──────────┘
         │
         ▼
┌───────────────────┐     ┌─────────────────────┐
│  Sync Processor   │◄────│  Reconciliation Loop │  ◄── canal de récupération
│  (idempotent)     │     │  (REST delta poll)   │
└────────┬──────────┘     └─────────────────────┘
         │
         ▼
┌───────────────────┐
│   Target Store    │
│   (local state)   │
└───────────────────┘
```

**Principe fondamental** : le webhook propage les changements en temps réel ; le REST récupère les gaps. Voir [ADR-001](docs/adr/ADR-001-hybrid-rest-webhook.md).

---

## Structure

```
sync-engine/
├── docs/
│   └── adr/                    # Architecture Decision Records
│       └── ADR-001-hybrid-rest-webhook.md
├── src/
│   └── sync_engine/            # package principal (à venir)
│       ├── webhook/            # réception et vérification des webhooks
│       ├── reconciliation/     # boucle de polling REST
│       ├── processor/          # traitement idempotent des événements
│       └── store/              # persistance de l'état de sync
├── tests/
├── CLAUDE.md
└── README.md
```

---

## Décisions d'architecture

| ADR | Décision | Statut |
|-----|----------|--------|
| [ADR-001](docs/adr/ADR-001-hybrid-rest-webhook.md) | Architecture hybride REST/webhook | Accepté |

---

## Invariants de conception

- **Idempotence partout** : une même donnée peut arriver deux fois (webhook + reconciliation). Toute opération doit être safe à rejouer.
- **Webhook non fiable par hypothèse** : la reconciliation n'est pas optionnelle, c'est la ligne de défense principale.
- **At-least-once delivery** : les webhooks sont acquittés après commit, jamais avant.
- **`last_successful_sync_at` est sacrée** : cette valeur permet de recalculer n'importe quel gap. Ne jamais l'écraser sans avoir terminé la sync.

---

## Intégrations cibles

Services issus de `fullstack-pilot` — détails dans `src/` au fur et à mesure des implémentations.

---

## Développement

```bash
# setup (à venir)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# tests
pytest

# linting
ruff check src/ tests/
```
