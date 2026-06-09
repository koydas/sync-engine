# ADR-003 — HMAC-SHA256 signature verification for webhook reception

**Status**: Accepted  
**Date**: 2026-06-09  
**Deciders**: fullstack-pilot team

---

## Context

ADR-001 establishes that the webhook channel is the primary change-propagation path and that the engine must verify each webhook's signature before inserting it into the queue (invariant #4 in CLAUDE.md). The verification mechanism was not specified by ADR-001.

Three schemes were considered:

1. **Symmetric HMAC-SHA256** — sender and receiver share a secret; the sender attaches `HMAC(secret, body)` as a header.
2. **Asymmetric signature (RSA/ECDSA)** — sender signs the payload with a private key; receiver verifies with the public key.
3. **Bearer token** — sender includes a static shared token in a header; receiver checks equality.

---

## Decision

We use **HMAC-SHA256** with a shared secret.

The signature is transmitted in a request header (e.g. `X-Hub-Signature-256`) as either a bare hex digest or a `sha256=<hex>` prefixed string; both forms are accepted.

Comparison is performed with `hmac.compare_digest` (constant-time) to prevent timing-oracle attacks.

Verification is isolated in `src/sync_engine/webhook/verifier.py` as a single pure function:

```python
def verify_hmac_sha256(payload_bytes: bytes, signature_header: str, secret: str) -> None: ...
```

`WebhookHandler` calls this function as the first step in `handle()`. Any failure raises `WebhookSignatureError` before any queue write occurs (invariant #4).

---

## Why HMAC-SHA256 over asymmetric signatures

- HMAC-SHA256 is the de-facto standard in the webhook ecosystem (GitHub, Stripe, Shopify all use it). Third-party sources that emit webhooks to this engine will already be configured for it.
- Asymmetric signatures add key distribution and rotation complexity for no benefit at this scale: the receiver is a single service, not a distributed public verifier.
- The security model is equivalent when the shared secret is stored as an environment variable and never committed.

## Why HMAC-SHA256 over bearer token

- A bearer token is a static equality check; its security degrades if the comparison is not constant-time (timing oracle) or if the token leaks in logs.
- HMAC binds the signature to the payload body, so a replayed token with a different payload is rejected. A bearer token provides no such protection.

---

## Constant-time comparison requirement

Naive string comparison (`==`) leaks timing information proportional to the length of the shared prefix, enabling offline secret reconstruction. `hmac.compare_digest` compares in fixed time regardless of where the strings diverge. This is mandatory for all signature comparisons in the engine — any future verification code must follow the same constraint.

---

## Consequences

**Positive:**
- Standard scheme: every major webhook source can be configured to sign with HMAC-SHA256 out of the box.
- Timing-safe by construction: `hmac.compare_digest` is the only permitted comparison.
- Isolated: `verifier.py` has no side effects and is independently testable without mocking.
- Tests compute real HMAC signatures with a fixture secret — no mocking needed, the full verification path is exercised.

**Negative / accepted costs:**
- Secret rotation requires coordinating the sender and receiver simultaneously; there is no multi-key grace window in the current implementation.
- The `sha256=` prefix stripping is a convention, not a standard — future sources may use a different prefix, requiring an extension to `verifier.py`.

---

## Rejected alternatives

| Alternative | Reason for rejection |
|---|---|
| Asymmetric signature (RSA/ECDSA) | Disproportionate key management overhead; incompatible with most third-party webhook senders |
| Bearer token | Does not bind signature to payload body; provides no replay protection |
| No verification | Violates invariant #4 in CLAUDE.md — rejected unconditionally |
