# CLAUDE.md — sync-engine

Conventions du projet pour les sessions Claude Code.

---

## Architecture

Ce projet suit une architecture hybride REST/webhook documentée dans [ADR-001](docs/adr/ADR-001-hybrid-rest-webhook.md).

**Avant d'implémenter quoi que ce soit**, lire l'ADR concerné. Si une décision d'implémentation contredit un ADR existant, créer un nouvel ADR plutôt que de modifier silencieusement le code.

---

## Structure des packages

```
src/sync_engine/
├── webhook/        # Réception, vérification HMAC, mise en queue
├── reconciliation/ # Boucle REST, calcul des deltas, gap fill
├── processor/      # Traitement idempotent, déduplication par event_id
└── store/          # Persistance : last_successful_sync_at, queue d'événements
```

Chaque package a une responsabilité unique. Ne pas faire traverser la logique de reconciliation dans le webhook handler et vice versa.

---

## Invariants — ne jamais violer

1. **Idempotence** : toute opération de sync doit pouvoir être rejouée sans effet de bord. Utiliser `event_id` comme clé de déduplication.
2. **Acquittement après commit** : marquer un webhook comme traité uniquement après que l'état cible a été écrit.
3. **`last_successful_sync_at`** : mise à jour uniquement après une sync complète et sans erreur. Jamais en début de cycle.
4. **Signature webhook obligatoire** : rejeter tout webhook sans signature valide avant de l'insérer en queue.

---

## Conventions de code

- Python 3.11+, type hints partout.
- `ruff` pour le linting, `black` pour le format — pas de configuration custom.
- Pas de `print()` dans le code applicatif — utiliser `logging` avec des niveaux explicites.
- Les exceptions métier héritent d'une classe de base `SyncError` (à définir dans `src/sync_engine/exceptions.py`).
- Pas de `try/except Exception` silencieux — toujours logger ou re-raise.

---

## Tests

- Framework : `pytest`
- Un test par comportement, pas par fonction.
- Les tests de webhook mockent la vérification de signature (ne pas dépendre de secrets en test).
- Les tests de reconciliation mockent l'API REST (pas d'appels réseau en CI).
- Nommage : `test_<ce_qui_est_testé>_<condition>_<comportement_attendu>`.

---

## ADRs

- Répertoire : `docs/adr/`
- Format : `ADR-NNN-titre-court.md`
- Numérotation séquentielle, pas de réutilisation.
- Statuts valides : `Proposé` | `Accepté` | `Déprécié` | `Remplacé par ADR-NNN`
- Un ADR ne se modifie pas après acceptation — on crée un ADR de remplacement.

---

## Git

- Branche de développement courante : `claude/sync-engine-bootstrap-wkdEx`
- Messages de commit en anglais, impératif, sans point final.
- Format : `<type>: <description>` — types : `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
- Ne pas committer de secrets, de fichiers `.env`, ou de tokens.
