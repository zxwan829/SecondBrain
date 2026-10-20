# D086 trusted capture suggestion binding candidate

Status: **internal candidate / no production adapter / no public wire frozen**.
This note describes code and proof boundaries; it is not a new API contract and
must not be read as evidence of Hermes integration or production acceptance.

## Observed Core path on the reviewed main

1. A normal Chat `capture.suggestion` is a UI suggestion. No Core code path
   currently authenticates a Hermes event, re-reads its original message, or
   binds a Hermes Session/Run/message identity to Core. Client-supplied Session
   or Run identifiers are not authority.
2. `POST /api/inbox/entries` requires the authenticated Core App action
   `capture.write`. The current trusted adapter is Web only. Its server-derived
   identity is `authenticated_web_identity`; unknown body fields (including
   identity/consent fields) are rejected. Explicit capture persists the exact
   text and event metadata into Capture Raw/Core state and creates server-side
   consent evidence from the authenticated action. The exact ID-addressed GET
   requires `inbox.read`; it does not enumerate entries.
3. Core Proposal creation from a Capture uses deterministic `_mock_suggestions`
   and a source/version-bound Core record. A user decision is separately
   persisted with actor, version, idempotency key, and history. This is not an
   AI/Hermes proposal.
4. `approved_suggestion` at Inbox POST requires the exact Core Proposal ID and
   version. Core checks `approved_recorded`, supported kind, current source and
   vocabulary versions, and exact source text before persistence, then repeats
   those checks immediately before writing. Missing/fake/stale binding or a
   different body is rejected. Existing event state uses a cross-process lock,
   durable request/content digests, and Raw verification for replay/recovery.
5. Proposal target execution is a later operation: current source and
   vocabulary are rechecked; a fresh execution preview, explicit `confirmed`,
   preview hash, and target action are required. Journal and Review use their
   dedicated stores; Project execution returns 501. This is not Knowledge
   Promote. There is no D086 automatic archive operation; `90-Archive` is not
   an execution target or authorization.

## Internal candidate boundary

`TrustedCaptureSuggestionBindingAuthority` is deliberately unregistered from
`create_app()` and has no route or Inbox persistence side effect. It reads the
source and consent authorities twice and requires both immutable snapshots to
match. A source edit/version change or consent revocation between reads fails
closed. The source reader must verify the exact event record; the Core consent
reader must return an explicit consent audit row for the same authenticated
subject, event ID, source text SHA-256, and source record version. The adapter's
server-side receive time must not be in the future, the source expiry must
still be current, and the Core consent timestamp must fall between receipt and
the current time. Original text is capped by UTF-8 bytes, not character count,
and the complete source/consent projection has a bounded serialized budget.

`TrustedCaptureSuggestionBindingStore` is an unconfigured internal candidate
ledger for synthetic/local validation. It binds one event+subject to one
metadata tuple under an inter-process lock, replays an identical tuple, and
rejects a conflicting content/version/consent tuple. It uses fsync plus atomic
replace; on restart it validates the last complete state before clearing an
orphan temporary file. Corrupt authoritative state fails closed and leaves
files untouched. This ledger is not the Core consent store, does not create an
Inbox entry, and does not make source/consent reads atomic with a future Inbox
write. Any future admission transaction still needs a frozen contract and an
atomic/recoverable seam with the real Core stores.

The returned deterministic binding ID is an idempotency correlation value,
not a bearer credential. Final durable replay/conflict/recovery for Inbox
events remains owned by the existing Core Inbox event store.

The current app injects neither adapter, so this candidate fails closed. The
candidate deliberately does not select a public URL, accept Web Session/Run
claims, translate an SSE `proposal_id` into a Core Proposal, or downgrade a
missing binding to `approved_suggestion`. Adapter authentication details,
consent UX/wire, TTL policy, event/version semantics, and status responses need
one cross-line freeze before public integration.

## Synthetic evidence scope

Tests inject local synthetic source and consent readers to exercise exact
binding, second-read drift/revocation, UTF-8 budgets, candidate ledger replay,
same-event conflicts, concurrent writes, interrupted replace recovery, and
corrupt-state fail-closed behavior. They prove candidate logic only, not a
production Hermes adapter. Existing Core tests separately cover durable Inbox
replay, conflicts, concurrent requests, interrupted writes, corrupt state
recovery, proposal approval, stale versions, and dedicated target execution. A real
localhost test exercises the current `create_app()` Inbox POST/GET and Proposal
approval flow with synthetic data; no model, NAS, Vault, real chat, or external
adapter is involved.
