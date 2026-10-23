# D086 Core S1–S3 candidate contracts (pending freeze)

**Status: proposal only.** This document records B-line design input for Issue
#97. It does not authorize an adapter, public route, real Hermes access,
Core-owned consent/admission, or changes to the existing Web Inbox contract.
Implementation remains gated on A/PMO freezing the unresolved contracts.

## S0 review result

The existing `TrustedCaptureSuggestionBindingAuthority` and
`TrustedCaptureSuggestionBindingStore` remain an internal, fail-closed metadata
candidate. The store is not configured as an admission path. Its tests cover
source/consent rechecks, drift, expiry, identity mismatch, UTF-8 limits,
cross-process same-key races, conflicting bindings, atomic-replace interruption,
directory-fsync ambiguity, replay durability, unsafe state/lock/temp files and
root identity replacement.

The existing Web Inbox entry path treats its event key only as idempotency,
requires authenticated Web identity, serializes same-key requests, binds replay
to exact content and request metadata, and fails closed when state is missing,
corrupt or inconsistent with Raw. Synthetic HTTP coverage now also recreates
the Core app after Raw persistence but before state persistence: replay returns
503, preserves the exact Raw bytes, and does not synthesize a state record.

No frozen security defect was reproduced in this S0 review. These tests do not
prove an OS crash/power-loss guarantee or provide cross-filesystem transaction
semantics.

## S1 candidate: verified suggestion source reader

Before source bytes can be considered trusted, a Core-internal reader would
need to return a server-authenticated event with: immutable source event ID,
non-Agent-forgeable subject mapping, exact original bytes and SHA-256,
monotonic anti-ABA version, source origin, server received time, expiry and
evidence of edit/delete state. The reader must distinguish missing, changed,
expired, unauthorized and unavailable states without returning content through
errors. A read from Web SSE, client session/run, or caller-supplied suggestion
object is not provenance. Source-of-truth, credentials and lifecycle semantics
remain unresolved and require A/PMO freeze.

## S2 candidate: Core-owned consent record

Consent would be a durable Core-owned record bound to subject, exact source
event/version/hash and a unique user action. Its contract must define accept,
revoke, expiry, one-time consumption, idempotent replay, concurrent double
accept, caller authentication and audit evidence. The current
`CoreCaptureConsentRecord` is a type candidate only; it is not a durable
consent ledger and must not authorize admission.

## S3 candidate: Inbox admission and recovery

Candidate atomic sequence: verify exact source and current consent revision;
stage the exact original bytes; durably sync staged data; commit one Inbox event
bound to source identity/version/hash and consent revision; then return success.
The contract must define the linearization point for revoke-versus-commit,
same-key exact replay, conflicting replay, interruption at each persistence
boundary, restart recovery and unknown outcomes. No implementation may claim
atomicity across source, consent and Inbox until the backing-store transaction
and recovery model are frozen.

## Failure-injection matrix to freeze before implementation

| Injection point / condition | Required result | Evidence required |
| --- | --- | --- |
| Source missing, edited, deleted, expired or version regresses | Reject; no Inbox Raw/state write | Synthetic reader transitions and unchanged store snapshot |
| Consent missing, revoked, expired or subject differs | Reject; no Inbox Raw/state write | Durable consent state before/after plus audit result |
| Two accepts for same event/version race | One commit; other exact replay or explicit conflict | Multi-process race, one durable event, stable response identity |
| Same key with changed bytes/version/consent | Conflict; never overwrite prior Raw/state | Replay matrix across restart |
| Failure before Raw write | No committed event; retry semantics frozen | Fault injection and filesystem snapshot |
| Raw durable, state/commit absent | Unknown/incomplete; no success replay or rewrite | Restart replay returns safe pending/error; bytes unchanged |
| Commit replace succeeds but directory fsync fails | Unknown outcome; no durable-success claim | Restart and replay after successful/failed fsync |
| Consent revoke races commit | Deterministic winner at a frozen linearization point | Controlled cross-process interleaving |
| Audit persistence fails | No success unless audit and admission atomicity is frozen | Audit failure injection and durable state comparison |

## Decisions still required from A/PMO

1. Hermes source of truth, server credentials, identity mapping and event
   lifecycle/version/TTL semantics.
2. User confirmation and revocation semantics, including action proof and
   one-time-consumption behavior.
3. Whether to reuse an existing internal authorization path or introduce an
   internal adapter; no public endpoint is proposed here.
4. Storage transaction boundaries, revoke-versus-commit linearization,
   durability assumptions and recovery/operator procedure.
5. Required test gates for process death, filesystem sync errors, replay and
   audit failure.
