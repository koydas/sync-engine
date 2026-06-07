# ADR-001 — Architecture hybride REST/webhook pour la synchronisation

**Statut** : Accepté  
**Date** : 2026-06-07  
**Décideurs** : équipe fullstack-pilot

---

## Contexte

Le moteur de sync doit maintenir la cohérence des données entre plusieurs services (`fullstack-pilot` et ses intégrations tierces). Trois approches architecturales ont été évaluées :

1. **Full polling** — le moteur interroge périodiquement chaque source via REST.
2. **Full event-driven** — le moteur ne réagit qu'aux webhooks émis par les sources.
3. **Hybride REST/webhook** — les deux canaux coexistent avec des rôles distincts.

---

## Décision

Nous adoptons l'architecture **hybride REST/webhook**.

---

## Pourquoi pas full polling

Le polling pur pose trois problèmes non acceptables en production :

- **Latence structurelle** : un changement n'est visible qu'au prochain cycle ; avec un intervalle de 60 s, la fenêtre de désynchronisation est garantie.
- **Charge inutile** : les requêtes sont émises même quand rien n'a changé. À l'échelle, cela génère du trafic et de la charge côté API tiers sans valeur ajoutée.
- **Rate limiting** : les APIs tierces plafonnent les appels. Un polling agressif consomme le quota, bloquant les opérations critiques.

---

## Pourquoi pas full event-driven

Le mode purement webhook pose des problèmes de fiabilité fondamentaux :

- **Pas de garantie de livraison** : les webhooks sont fire-and-forget côté émetteur. Une interruption réseau, un redémarrage du récepteur, ou une indisponibilité temporaire fait silencieusement disparaître des événements.
- **Pas de snapshot initial** : au démarrage ou après une reprise, il n'existe aucun moyen de reconstruire l'état courant sans interroger la source via REST.
- **Pas d'ordre garanti** : un webhook `updated` peut arriver avant le `created` correspondant. Sans reconciliation, l'état local devient incohérent.
- **Opacité des gaps** : si le moteur est offline pendant 30 minutes, il ne sait pas combien d'événements il a manqués ni lesquels.

---

## Architecture hybride : rôles de chaque canal

### Webhook — canal temps réel (lead par défaut)

Le webhook est le **canal primaire** pour la propagation des changements.

| Responsabilité | Détail |
|---|---|
| Changements unitaires | Création, mise à jour, suppression d'une ressource |
| Faible latence | Propagation < 2 s dans le cas nominal |
| Déclencheur de reconciliation | Un webhook manqué déclenche un poll ciblé |

Le moteur ne fait confiance à un webhook que si sa signature est vérifiée et si son `event_id` n'a pas déjà été traité (idempotence).

### REST — canal de vérité (lead lors des transitions d'état)

Le REST est le **canal de récupération et de bootstrap**.

| Responsabilité | Détail |
|---|---|
| Snapshot initial | Chargement complet à la première connexion ou après une reprise |
| Reconciliation périodique | Poll léger sur `updated_since` toutes les N minutes |
| Gap fill | Après une panne, le moteur calcule la fenêtre manquée et effectue un poll ciblé |
| Source de vérité | En cas de conflit entre état local et payload webhook, le REST arbitre |

---

## Récupération après échec webhook

Trois scénarios de panne sont couverts :

### Scénario 1 — Webhook non reçu (perte réseau courte)

La reconciliation périodique (`updated_since = last_sync_at`) détecte les changements manqués dans la fenêtre suivante. Tolérance maximale : intervalle de reconciliation (cible : 5 min).

### Scénario 2 — Récepteur hors ligne (panne prolongée)

Au redémarrage, le moteur lit `last_successful_sync_at` depuis son store persistant, calcule le delta temporel, et effectue un poll REST `updated_since = last_successful_sync_at`. Les ressources modifiées pendant la panne sont réintégrées avant de ré-ouvrir le canal webhook.

### Scénario 3 — Webhook reçu mais non traité (crash en cours de processing)

Les webhooks entrants sont d'abord écrits dans une queue persistante (at-least-once delivery). Le processing ne marque l'événement comme traité qu'après commit en base. Un worker de reprise réexécute les entrées non acquittées au démarrage.

---

## Conséquences

**Positives :**
- Latence proche du temps réel sur le chemin nominal.
- Résilience garantie : aucun changement ne peut être définitivement perdu.
- Le polling est light (delta uniquement), pas full-scan.

**Négatives / coûts acceptés :**
- Deux chemins de code à maintenir (webhook handler + reconciliation loop).
- Idempotence obligatoire sur toutes les opérations de sync (un même changement peut arriver deux fois).
- Nécessité d'un store persistant pour `last_successful_sync_at` et la queue de webhooks.

---

## Alternatives rejetées

| Alternative | Raison du rejet |
|---|---|
| Message broker (Kafka, SQS) | Sur-ingénierie pour le périmètre actuel ; complexité opérationnelle disproportionnée |
| CDC (Change Data Capture) | Requiert un accès direct aux bases des services tiers — non disponible |
| Long polling | Compromis des deux pires mondes : charge du polling + complexité de gestion des connexions |
