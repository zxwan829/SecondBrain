# D086 S3 admission transaction candidate

Status: **synthetic design/model only; no admission implementation or wire
contract is frozen**. This proposal does not authorize a route, durable consent
store, WAL, automatic write/recovery, or production diagnostic.

## Candidate operation states

`intent_prepared → source_consent_checked(revision) → raw_staged →
commit_record_durable → inbox_committed`

Each transition is a model state only. The candidate commit point is one
provable serialization boundary shared by consent and Inbox admission. At that
point the current consent revision must still equal the checked revision and
the decision must still be active; the operation's durable WAL record must
include the server-owned actor/event/intent, source version and digest,
consent revision, stable operation key and deterministic Inbox ID. A WAL
commit record counts as durable only after the selected storage's required
file and directory durability operations succeed. An unknown fsync/directory
sync result is not a successful commit. Separate ordinary file renames or
separate locks do not establish this boundary. If the selected stores cannot
provide this shared CAS/serialization point, S3 must remain unimplemented.

## Consent revocation race

- Revoke serializes first: revision advances and becomes inactive. Admission's
  compare-and-swap against the old revision fails, and zero Inbox entries are
  admitted. A previously staged Raw item may remain; the system must not
  silently delete, repair or re-admit it.
- Commit serializes first: one durable admission record wins at its recorded
  consent revision. A later revoke advances the consent revision but does not
  remove that Inbox entry. Downstream effect of revocation on already admitted
  work still requires a decision.
- No claim is made for a system without one shared linearization boundary.

## Replay, conflict and crash outcomes

For the Hermes suggestion domain, the unique replay slot is the same
**server-authenticated subject + source_system + source_event_id**. Intent is
immutable request content, **not** a namespace: reusing the same source event
with a changed intent or rotated idempotency key is a conflict, not a new slot.
Exact intent + key + source version + digest + consent revision replay maps to
the same operation and stable Inbox ID. Changing source version, digest,
consent or decision also conflicts within the slot. A different source event
(or a different authenticated subject/source system) is an independent slot
requiring its own authorized evidence. This model does not retroactively change
existing Web explicit-capture semantics; no caller-supplied source fields are
authoritative. The Inbox endpoint wire code for pending, conflict and unknown durability remains unfrozen.

| Crash point | Candidate internal meaning | Automatic action |
| --- | --- | --- |
| Before Raw staging | No admitted operation | None |
| Raw staged, no provable commit record | Unknown durability / possible Raw-only orphan | None; fail closed, diagnostic only |
| Commit record durable, Inbox not materialized | Durable admission pending | None until a separately approved recovery contract |
| Inbox entry committed | One stable admitted Inbox ID | Exact replay returns same ID |

An HTTP 202, if eventually frozen, may only mean durably accepted/pending Core
work; it never means archived Journal or Knowledge. The exact 202/409/412/503
wire mapping still requires A/PMO approval. Unknown commit durability must
never be reported as success.

## Operator-only diagnostic candidate

First candidate is an offline read-only function/CLI, not HTTP or scheduler.
It must open only an approved local root with no-follow/fd-relative handling
and bounded reads, perform no repair or mutation, and emit fixed statuses:
`RAW_WITHOUT_STATE`, `STATE_WITHOUT_RAW`, `MISMATCH`, or
`UNKNOWN_DURABILITY`. Output may include bounded file counts and truncated
digest prefixes only: no bodies, full paths, credentials or session/run data.
Allowed root, operator UID, resource budgets and diagnostic log retention are
still decisions. Recovery writes, Raw moves/deletes, state reconstruction and
re-admission require a distinct explicit freeze and authorization.

## Required acceptance before any implementation

Choose the actual source authority/revision guarantee; exact consent action,
Origin/session/permission proof, intent vocabulary, expiry/revocation and audit
retention; durable store and shared WAL/CAS seam; revoke-vs-commit behavior;
HTTP response mapping; offline diagnostic ownership/output/retention; and the
minimum crash/process-restart/OS-crash matrix. Current tests only exercise the
synthetic transition model and do not establish filesystem or power-loss
durability.
