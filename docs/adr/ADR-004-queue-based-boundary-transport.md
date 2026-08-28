# ADR-004 — Queue-based transport for cross-boundary ingestion and propagation

**Status**: Accepted
**Date**: 2026-08-28
**Deciders**: fullstack-pilot team

---

## Context

ADR-001 established webhook (push, HTTP) as the primary ingestion channel and REST as the recovery channel. Its "Rejected alternatives" table dismissed a message broker as over-engineering — in that context, the engine and its sources were assumed to be directly network-reachable, and inbound HTTP was the natural transport.

Two new integrations do not share that assumption:

- **Ingestion**: Système A (and Postman, used for manual testing) run outside the network boundary sync-engine operates in. sync-engine is deployed on-premise; opening an inbound HTTP path from outside that perimeter for every new source is not viable operationally.
- **Egress**: sync-engine must hand off processed events to Système B — a separate on-premise service with its own database — without sync-engine depending on Système B's availability or network path, and without exposing an inbound path on Système B's side either.

Three options were considered:

1. **Keep HTTP push and open an inbound path** through the perimeter (firewall/VPN exception) for each new source and each downstream consumer.
2. **Introduce a queue at each boundary crossing**: the producer pushes, the consumer on the other side pulls. Neither side needs to accept inbound connections from the other.
3. **REST-only polling both ways**: sync-engine polls Système A, Système B polls sync-engine.

---

## Decision

We introduce queues as the transport at each boundary crossing, accessed through a single pluggable interface, `SyncQueue` (`src/sync_engine/queue/base.py`), following the same ABC + injected-backend pattern already established for `SyncStore` (ADR-002).

The end-to-end mechanic for one integration:

```
Système A --push--> QueueA --pull--> sync-engine --[commit to store]--> --push--> QueueB --pull--> Système B
```

- **QueueA (ingestion)** — Système A and Postman push signed events. sync-engine pulls, verifies the signature (`verify_hmac_sha256`, ADR-003 — unchanged), deduplicates and enqueues into the existing local durable queue (`SyncStore.enqueue_webhook`), exactly as today's `WebhookHandler.handle()` does. A QueueA message is only deleted (acknowledged) after that local enqueue has committed.
- **QueueB (egress)** — once the processor commits the processed state to `SYNC-ENGINE-DB` and marks the event processed, it pushes the result to QueueB. Système B pulls from QueueB on its own schedule; sync-engine has no knowledge of Système B's availability.

`SyncQueue`'s surface is intentionally minimal, mirroring `SyncStore`:

| Method | Purpose |
|---|---|
| `push(message_id, payload)` | Publish a message |
| `pull(max_messages)` | Retrieve pending messages as `(message_id, payload)` pairs |
| `delete(message_id)` | Acknowledge / remove a message, called only after the local operation that depended on it has committed |

The same interface is instantiated twice — QueueA used in pull mode, QueueB in push mode — there is no separate inbound/outbound ABC. The concrete broker technology (SQS, Azure Service Bus, RabbitMQ, ...) is chosen and injected at startup per ADR-002's dependency-injection convention; no engine code imports a concrete broker client. ADR-004 does not lock in a vendor.

HTTP webhook reception (`WebhookHandler`, ADR-001/ADR-003) is not removed — it is reused unchanged as the verification+dedup+enqueue step, now invoked by a queue consumer (`webhook/consumer.py`) that pulls from QueueA instead of an HTTP route handing it a request. sync-engine itself no longer needs to terminate inbound HTTP traffic originating outside its network boundary.

---

## Why not opening an inbound path (option 1)

- Every new source or downstream consumer needs its own firewall/VPN exception — an operational cost that scales with the number of integrations, not a one-time cost.
- It reintroduces, on the send side, the exact reliability problem ADR-001's hybrid design was built to avoid on the receive side: if sync-engine (or Système B) is briefly unreachable, the sender's push simply fails, and the event is lost before it ever reaches a durable queue — unless the sender retries indefinitely, which we don't control.

## Why not REST-only polling both ways (option 3)

- The structural-latency and wasted-load arguments ADR-001 already made against full polling apply symmetrically here — they don't disappear because the direction changed from "engine polls a third party" to "engine polls / is polled across an internal boundary".

## Why a queue is no longer "over-engineering" here (revisiting ADR-001)

ADR-001 rejected a broker because, in that context, a broker would have added operational surface without solving a problem push-over-HTTP didn't already solve. Here the problem is structural: there is no viable inbound path across the on-premise boundary in either direction. A queue removes the inbound-path requirement entirely, which HTTP push cannot do regardless of how it's tuned. The operational cost of running a broker is accepted because it replaces a firewall-exception-per-integration cost that scales worse.

---

## Consequences

**Positive:**
- No inbound HTTP path required across the on-premise boundary, in either direction.
- `SyncQueue` reuses the DI pattern already proven for `SyncStore` — an `InMemoryQueue` covers all tests, no I/O, no fixtures, no network calls in CI.
- Existing invariants are extended, not replaced: "acknowledge after commit" (CLAUDE.md invariant #2) now also governs when a QueueA message is deleted (after local enqueue) and when a QueueB push happens (after DB commit + `mark_event_processed`).
- Adding a new source or downstream system means wiring a new pair of queues, not opening new network paths.

**Negative / accepted costs:**
- A message broker becomes required infrastructure at each boundary crossing (previously avoided).
- Two failure modes need explicit handling in the implementation: a QueueA pull whose local enqueue fails (the message must not be deleted — redelivery is expected), and a QueueB push that fails after the local DB commit (the event is durably processed locally, but propagation to Système B must be retried independently).
- `reconciliation/`'s REST-based gap-fill (ADR-001) remains necessary. At-least-once delivery on a queue is not the same guarantee as "never delayed or dropped by the broker itself"; nothing here removes the need for the recovery loop.

---

## Rejected alternatives

| Alternative | Reason for rejection |
|---|---|
| Inbound HTTP exception per source/consumer (status quo extended) | Operational cost scales per integration; reintroduces the send-side reliability gap ADR-001 already solved for the receive side |
| REST-only polling both directions | Same latency/load problems ADR-001 rejected for polling, now facing both boundaries instead of one |
| Single shared queue for both directions | Conflates two independent failure domains (ingestion vs. egress) and two independent consumers (sync-engine vs. Système B); a backlog on one side would block the other |
