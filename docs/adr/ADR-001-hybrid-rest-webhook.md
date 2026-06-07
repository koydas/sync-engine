# ADR-001 — Hybrid REST/webhook architecture for synchronization

**Status**: Accepted  
**Date**: 2026-06-07  
**Deciders**: fullstack-pilot team

---

## Context

The sync engine must maintain data consistency across multiple services (`fullstack-pilot` and its third-party integrations). Three architectural approaches were evaluated:

1. **Full polling** — the engine periodically queries each source via REST.
2. **Full event-driven** — the engine only reacts to webhooks emitted by sources.
3. **Hybrid REST/webhook** — both channels coexist with distinct roles.

---

## Decision

We adopt the **hybrid REST/webhook** architecture.

---

## Why not full polling

Pure polling introduces three unacceptable production problems:

- **Structural latency**: a change is only visible at the next cycle; with a 60s interval, a desync window is guaranteed.
- **Wasted load**: requests are fired even when nothing changed. At scale, this generates traffic and third-party API load with no value.
- **Rate limiting**: third-party APIs cap call rates. Aggressive polling burns the quota, blocking critical operations.

---

## Why not full event-driven

Webhook-only mode has fundamental reliability problems:

- **No delivery guarantee**: webhooks are fire-and-forget on the sender side. A network blip, receiver restart, or temporary unavailability silently drops events.
- **No initial snapshot**: at startup or after recovery, there is no way to reconstruct current state without querying the source via REST.
- **No ordering guarantee**: an `updated` webhook may arrive before its corresponding `created`. Without reconciliation, local state becomes inconsistent.
- **Opaque gaps**: if the engine is offline for 30 minutes, it has no way to know how many events it missed or which ones.

---

## Hybrid architecture: role of each channel

### Webhook — real-time channel (default lead)

The webhook is the **primary channel** for change propagation.

| Responsibility | Detail |
|---|---|
| Unit changes | Resource creation, update, deletion |
| Low latency | Propagation < 2s on the nominal path |
| Reconciliation trigger | A missed webhook triggers a targeted poll |

The engine only trusts a webhook if its signature is verified and its `event_id` has not already been processed (idempotency).

### REST — truth channel (lead during state transitions)

REST is the **recovery and bootstrap channel**.

| Responsibility | Detail |
|---|---|
| Initial snapshot | Full load on first connection or after recovery |
| Periodic reconciliation | Light poll on `updated_since` every N minutes |
| Gap fill | After an outage, the engine computes the missed window and performs a targeted poll |
| Source of truth | In case of conflict between local state and webhook payload, REST arbitrates |

---

## Recovery after webhook failure

Three failure scenarios are covered:

### Scenario 1 — Webhook not received (short network loss)

Periodic reconciliation (`updated_since = last_sync_at`) detects missed changes in the next window. Maximum tolerance: reconciliation interval (target: 5 min).

### Scenario 2 — Receiver offline (extended outage)

On restart, the engine reads `last_successful_sync_at` from its persistent store, computes the time delta, and performs a REST poll `updated_since = last_successful_sync_at`. Resources modified during the outage are reintegrated before the webhook channel is reopened.

### Scenario 3 — Webhook received but not processed (crash mid-processing)

Incoming webhooks are first written to a persistent queue (at-least-once delivery). Processing marks an event as handled only after it has been committed to the store. A recovery worker replays unacknowledged entries at startup.

---

## Consequences

**Positive:**
- Near-real-time latency on the nominal path.
- Guaranteed resilience: no change can be permanently lost.
- Polling is light (delta only), not full-scan.

**Negative / accepted costs:**
- Two code paths to maintain (webhook handler + reconciliation loop).
- Idempotency required on all sync operations (the same change may arrive twice).
- A persistent store is required for `last_successful_sync_at` and the webhook queue.

---

## Rejected alternatives

| Alternative | Reason for rejection |
|---|---|
| Message broker (Kafka, SQS) | Over-engineering for current scope; disproportionate operational complexity |
| CDC (Change Data Capture) | Requires direct database access to third-party services — not available |
| Long polling | Worst-of-both-worlds compromise: polling load + connection management complexity |
