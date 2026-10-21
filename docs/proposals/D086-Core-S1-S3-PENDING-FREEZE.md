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

## D086-M1 interface and integration matrix (candidate, not frozen)

The fixed reviewed stack is main `4dee72cbfc37144a2803514abb9d42bc7a069656`
→ #148 `3276ceda8736740e95b0b1a9b37e30f125234681`
→ #150 `9309145b1f3c473c310c9435afebc64a4cbe5281`
→ #151 `211d3d9f9912b8de18ae12af2be65fdd2e57d5f3`
→ #152 `1321ad0997fd8062c4e47679fb282caf1a8ace8f`.
All four PRs remain Open/Draft. A's latest verdict (#97 comment #6309891586)
is `B_CORE_LOCAL_READY=PASS_WITH_LIMITS` only for an isolated cooperative
synthetic model; adversarial same-UID safety is BLOCKED and production readiness
is NO. B's tests and A's independent tests are separate evidence.

| Layer / candidate interface | Trusted input → output | Authority and permissions | Replay / CAS / failure behavior |
| --- | --- | --- | --- |
| S1 — internal source reader; injected into admission service | Server-side read by immutable event ID → verified snapshot of source system, event ID, subject, exact text/hash, monotonic version, received/expiry/lifecycle fields | Only a Core-created reader is trusted. Caller DTO, Web body, Session/Run ID, SSE payload or Agent assertion is not source authority. Current implementation uses a synthetic reader only; no route. | Compare independent reads and validate ID/subject/version/hash/intent/expiry; final read at commit edge. Any observed drift/missing/expired/unavailable source fails closed without source details in errors. Anti-ABA is tested in the synthetic model only. |
| S2 — synthetic consent ledger: accept/revoke | Signed test action proof bound to subject + event + version + hash + intent + action key → consent ID, revision/state and audit row | Local test HMAC issuer and SQLite only. It is not a Web Session, CSRF proof, user click, Hermes identity or real Core permission. No API route. | SQLite `BEGIN IMMEDIATE` serializes revisions. Revoke first advances revision/inactivates and stale admission rejects; admission commit first remains admitted if later revoked. Invalid proof, stale revision, changed binding or replay conflict fails closed. |
| S3 — `SyntheticInboxAdmission.admit_from_reader(action_proof)` | Signed synthetic action proof; source is fetched through injected reader; active consent revision → stable Inbox ID, Raw relative reference, operation and manifest | Service construction supplies reader; callers cannot supply trusted source DTO/text/subject/version. This remains a synthetic internal service, not the real `POST /api/inbox/entries` path and not production Inbox admission. | Exact same authenticated synthetic subject/source/event + intent/key/version/hash/consent revision replays one ID; changed intent/key/version/hash/consent for the same event conflicts. A distinct event is a distinct slot. Consent, operation and Raw manifest share SQLite CAS/transaction; Raw bytes live in a separate filesystem and are fsynced before SQLite commit. |
| R1 — `SyntheticOperatorDiagnostic(root)` | Explicit local synthetic root → redacted counts, status/findings and bounded digest prefixes | No route, CLI auth, operator identity or OS privilege proof. Descriptor-relative no-follow reads; DB bytes are bounded-read from a pinned fd into in-memory query-only SQLite. | Read-only: no lock/temp/sidecar, repair, cleanup or recovery write. Unsafe mode/owner/symlink, replacement, corruption or budget exhaustion returns unavailable/fail-closed. This is not production operator diagnostics. |

### Ordered call sequence (synthetic model only)

1. A Core-owned service receives an action proof; it verifies the synthetic
   signature, fixed origin, action, expiry and binding. This is not proof of a
   real human action.
2. The service acquires the synthetic source event guard, pins and identity-
   checks the configured Raw directory, then enters SQLite `BEGIN IMMEDIATE`.
3. It reads the source twice and validates exact identity/text/hash/version,
   checks active consent at the expected revision, and checks the operation
   slot for exact replay or conflict.
4. For a new admission it creates the Raw child with relative
   `O_NOFOLLOW|O_EXCL`, fsyncs the file and pinned directory, verifies bytes
   through the same descriptor, and re-reads the source.
5. It stages operation and manifest rows, rechecks Raw directory identity in
   the transaction's immediately-before-commit callback, then SQLite commits.
   Success is returned only after the transaction context exits successfully.
6. R1 is a separate read-only observer. It does not run in the admission path
   and cannot repair any state.

### Frozen Web/Core boundary to preserve

- Existing explicit Web capture remains separate: authenticated Web identity
  and action permission are server-derived for `POST /api/inbox/entries`;
  exact ID-addressed `GET` uses its existing read permission. Preserve the
  current wire schema and status behavior. The event key is idempotency, not
  provenance. This path does not authenticate Hermes suggestion events.
- `capture.suggestion` display, client Session/Run IDs and any browser-supplied
  source/subject/consent fields cannot authorize this synthetic or a future real
  admission. Do not connect Web to the S1–S3 synthetic service.
- S1–S3 have no `create_app()` route and no localhost HTTP end-to-end
  acceptance. Synthetic pytest is module-level evidence, not Web/Core
  integration evidence. No new HTTP status code or response schema is implied.

### Verified status versus remaining proof

| Capability | Evidence status |
| --- | --- |
| S1 source snapshot validation, drift and anti-ABA behavior | Synthetic tests passed; A independent cumulative test passed with limits. No real Hermes authority, server credentials or event lifecycle verified. |
| S2 persistence, revision CAS, revoke ordering, replay and process restart | Synthetic SQLite tests passed; A independent cumulative test passed with limits. No actual user consent/action or Web authentication verified. |
| S3 exact replay/conflict, 2/4/8-process races, kill/restart and Raw-fsync-before-DB interruption | Synthetic tests passed; A independent cumulative test passed for cooperative model. No global Raw/SQLite transaction is established. |
| R1 descriptor-anchored, redacted, no-write diagnostics | Synthetic tests and A independent read-only checks passed with limits. No operator authentication, OS role separation or production ACL verified. |
| Same-UID Raw directory rename after final name check but before SQLite commit | A reproduced at fixed stack: admission can commit while the pinned Raw inode is detached from configured `Raw/`, leaving manifest path missing. **ADVERSARIAL_SAME_UID=BLOCKED.** |
| Web/Core HTTP integration, actual Hermes, production OS isolation, hardware power loss | **NOT PROVEN / NOT RUN.** |

Raw and SQLite are separate durability domains. A crash after Raw file/directory fsync but before SQLite commit can leave an unreferenced Raw orphan; SQLite commit and filesystem persistence are not globally atomic. The model performs no automatic orphan cleanup, replay adoption, repair or recovery write. A same-UID actor can rename a pinned directory inode after the final pathname identity check; dirfd pinning prevents following a substituted symlink but does not supply OS authorization or guarantee that the inode remains beneath its configured pathname through commit. Repeated application-level `stat` checks are not an OS isolation substitute, and no further patch is proposed for that threat.

### Web/Core integration prerequisites

Before any production or public integration, A/PMO must freeze and separately accept:

1. The Hermes source-of-truth API, server-side credentials, actor-to-subject
   mapping, immutable event identity, anti-ABA version, receipt/expiry, and
   edit/delete semantics. The Core adapter—not Web—must fetch and verify it.
2. The real human action boundary: authenticated Web identity, CSRF/origin
   policy, exact event/version/hash/intent binding, one-time action key,
   consent persistence, revision CAS and revoke ordering. Client-provided
   Session/Run and source fields are never authority.
3. A durable storage/recovery contract that states what the commit point means
   across SQLite and Raw, what response is allowed for an unknown fsync/commit
   outcome, how Raw-only or detached-Raw states are surfaced, and which
   operator may diagnose them. Automatic repair, delete, replay adoption or
   recovery writes remain unauthorized.
4. A real OS isolation design with distinct service/writer principals and
   directory ownership/permissions that deny an untrusted writer rename rights
   over the service's Raw parent. Validate effective UID/GID, mount/ACL
   behavior, parent-directory rename denial and process boundary in a dedicated
   non-production environment. If separation cannot be demonstrated, fail
   closed; do not claim same-UID resistance.
5. Exact public wire compatibility and HTTP tests only after the route contract
   is frozen: authentication, request/response/status, idempotency/conflict,
   source drift, permission denial, resource limits, read-only behavior and
   existing Inbox GET/POST regression. Nothing in this document adds a route.

Until these decisions and tests are accepted, S1–S3 remain synthetic candidates,
R1 remains an unexposed local diagnostic model, and production readiness is
BLOCKED.