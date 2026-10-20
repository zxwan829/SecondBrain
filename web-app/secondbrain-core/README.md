# SecondBrain App / Core

The D074 first-stage standalone App/Core implementation is local development
code and has not been deployed. It serves the FE-4-derived React app, same-origin
APIs, one App login session, Review status, and a server-side Hermes BFF. Hermes
remains the Agent Runtime and NAS files remain the business source of truth.
Production Compose, services, ports, permissions, and Promote state are
unchanged.

## Local development

- Build frontend: run `npm ci`, `npm run typecheck`, and `npm run build` in
  `secondbrain-frontend/`.
- Run frontend with Vite: `npm run dev` in `secondbrain-frontend/`; `/api` is
  proxied to the Core/App on `127.0.0.1:8000`.
- Run Core/App: set the required paths and exact App Origin/Host values shown in
  `.env.example`, provide a private password file, then run
  `python -m secondbrain_core` from this directory.
- `SB_HERMES_API_KEY_FILE` is a server-only credential file. It must never be
  exposed to the browser. Do not use the placeholder paths or values in the
  example as production configuration.
- `SB_PROMOTE_ENABLED` defaults to `false`. The production `create_app` refuses
  startup whenever it is `true`, for both `inline` and `subprocess` modes. This
  code has no verifiable isolated Worker, restricted Writer, or independent
  approval authority; an inline worker and a subprocess sharing the Core UID
  are not isolation boundaries. Environment flags, including test-mode names,
  cannot bypass this refusal. The only successful Promote tests assemble the
  HTTP routes directly in a test-only fixture and do not make the production
  application factory accept Promote.
- `SB_PROMOTE_WORKER_MODE=subprocess` selects the one-request subprocess
  protocol candidate while Promote is disabled. It does not provision or imply
  a worker identity, peer-authenticated IPC, ACL, mount sandbox, or production
  authorization.
- Organizer's SiliconFlow adapter is not loaded unless
  `SB_ORGANIZER_MODEL_ENABLED=true` is explicitly configured. Its preferred
  candidate is `deepseek-ai/DeepSeek-V4-Flash`; the key must come from a private
  file named by `SB_ORGANIZER_API_KEY_FILE`. The adapter currently fails the
  Core hard input/output token and hard cost gates, so connecting it does not
  enable manual or scheduled execution. Do not configure a real key or enable
  the adapter for local synthetic tests.

## Implemented and verified locally

- Standalone React/Vite entry and Core-hosted SPA/static assets; no Hermes
  Dashboard Plugin SDK dependency in the app bundle.
- One App session for Home, Chat, and Review; exact Origin and request-host
  checks for mutations; HttpOnly/SameSite cookie; no browser-supplied identity
  is accepted by the Core approval routes.
- Home and Review data are read from configured Review and Knowledge files;
  Review decisions are read from the existing versioned Core approval store.
- Hermes BFF routes for Sessions, history, create/fork/update/delete, run,
  streaming events, status recovery, and stop. The adapter normalizes the
  Hermes v0.21.5 / `749220ef` `data` lists, nested `session.id`, and JSON SSE
  event payloads. The API key is attached only by the server.
- Promote UI is guarded by Core's `promote_enabled` response and explicit user
  confirmation. Core defaults closed and retains SHA-256/version and audit
  protections.
- Journal API is always routed but returns an explicit unavailable response unless
  `SB_JOURNAL_ROOT` names an existing
  Core-owned `0700` directory. Authenticated writes require an explicit
  `记一下` / `写日记` phrase, append the original text to a per-date JSONL file,
  and use a persistent idempotency key. Chat's anchored explicit intent calls this
  API directly; ordinary Chat and Hermes tools cannot call this path implicitly.
- The channel-neutral Core intake contract is `POST /api/inbox/entries` with
  `original_text`, `source_channel`, `source_event_id`, `occurred_at`, `intent`,
  and optional `attachment_refs` (`[{capture_id, sha256}]`). An approved
  suggestion additionally carries `approved_proposal_id` and
  `approved_proposal_version`. The server derives a trusted `web` identity from
  the authenticated App action; body fields cannot assert a channel principal.
  Hermes and other external adapters are not registered. Event IDs are
  idempotency keys, not caller identity. Browser
  `occurred_at` is preserved as source metadata; Core `captured_at` is the
  authoritative receipt time. Core creates consent evidence from the successful
  App action and persists the original text through the existing Capture Raw →
  Review path. Replays with the same event key and request are idempotent;
  changed payloads conflict. `explicit_capture`, `journal_intent`, and
  `task_intent` are stored in Inbox; Journal and Task are not executed here.
  `approved_suggestion` requires an exact current `approved_recorded` proposal ID,
  version, and matching source content; it persists only through Capture Raw →
  Review and does not execute Journal, Project, Knowledge, or other target actions.
  Core repeats the proposal decision/version, source digest, and vocabulary
  revision checks under the per-event persistence lock immediately before the
  first Raw/state write. This closes changes injected after the initial HTTP
  validation and before persistence starts; it is not a cross-store transaction,
  so a mutation in the remaining interval after that check is still a documented
  race pending an explicitly designed shared lock/transaction boundary.
  Same-key concurrent identical requests reuse one durable Capture; competing
  payloads (including time, proposal version, or attachment binding) conflict.
  If a write leaves Raw without valid state, or state is corrupt/missing or no
  longer matches Raw, Core preserves the bytes and returns a recovery error for
  manual review; it never reconstructs missing state or overwrites the Raw on
  retry.
  Attachment references are limited to up to five existing Core Capture IDs
  plus SHA-256 values, which Core reopens without following links and rehashes;
  arbitrary paths, stale hashes, unsupported channel-owned sources, and repeated
  IDs are rejected. The stored response exposes only the opaque reference and hash.
  `GET /api/inbox/entries/{inbox_id}` restores the exact event after refresh under
  the App session.
- Knowledge source status can become `verified` only when a single exact
  promotion is supported by reconstructing `render_promoted_markdown()` from the
  exact current Review bytes and trusted `request_id`, Review digest, and
  approval time, then matching those canonical bytes to Knowledge, Audit, and
  (for B1b) the durable exact-confirmation operation output hash and
  `promote_exact_preview` intent. This rejects synchronized Knowledge/Audit hash
  drift. Legacy B1a records remain eligible only when their canonical output can
  be reconstructed exactly. Earlier B1b operation records that do not persist
  the exact confirmation intent remain unverified; no history is rewritten.
  The verifier reads one Review path and never scans
  Raw/Private; missing, corrupt, oversized, duplicate, or drifted evidence returns
  `unverified` with no source link.
- The subprocess Worker is a local process-boundary candidate only. It accepts
  one bounded Promote request, receives no App secret, closes inherited file
  descriptors, and runs under CPU/file/output bounds. Core startup rejects the
  combination of this same-UID candidate and enabled Promote. A separate OS UID,
  read-only approval/Review mounts, and write-only-or-minimal Knowledge/Audit
  ACLs are not provisioned here; therefore B3 production isolation remains
  blocked.
- B3 isolation design (not implemented or deployment-authorized): run the
  worker under a dedicated OS UID with a fixed executable and fixed, configured
  roots; expose only a versioned, size-bounded request over a private Unix
  domain socket and authenticate the peer UID (for example, platform peer
  credentials). Do not accept caller-selected filesystem roots. The worker
  should read only the exact pinned Review and Approval evidence; it should
  receive narrowly scoped write access only to the approved Knowledge target
  and append-only audit destination, while operation claims/state remain under
  Core ownership. Core and worker state directories must have explicit owner,
  group, and mode checks before startup. Timeout, malformed IPC, wrong peer,
  disconnect, or uncertain completion must fail closed and require explicit
  recovery with the same durable request ID; never infer success from child
  exit status alone. Production mounts, ACLs, account provisioning, and
  cross-store recovery protocol still require separate design review and
  authorization. Local tests do not assert OS isolation.
- Task API is always routed but returns an explicit unavailable response unless
  `SB_TASK_ROOT` names an existing Core-owned `0700` directory. It uses one
  locked, atomically replaced JSON store for idempotent create, status/date query,
  optimistic updates, and traceable state history. Chat accepts only the explicit
  `添加待办：` / `建个待办：` prefixes; Today provides edit, complete, and reopen.
  Reminder delivery is not implemented.
- Authenticated Core read contracts expose `GET /api/projects` as an honest
  `not_configured` response until a trusted project source exists, and
  `GET /api/activity` as a metadata-only projection of Journal/Task records with
  explicit operation and session references. Activity never exposes Journal
  bodies, Task titles/commands, session IDs, or operation IDs. Its default read
  checks at most 365 exact Journal day paths and reports `partial` because older
  files may exist; explicit date ranges are paired, timezone-aware, and limited
  to 31 days. No Hermes/session/message history is read by these endpoints.
- `GET /api/daily-brief?date=YYYY-MM-DD&timezone=...` currently returns
  `not_configured`; there is no trusted brief source yet, and the route does not
  read Hermes history or call a model. `GET /api/agent/health` reports only
  status, source, and checked time from a Hermes capabilities request; it never
  returns session/message data or upstream diagnostic payloads.
- Home is an explicitly requested read and caps traversal at 500 directory
  entries, depth 4, 50 Markdown candidates, and 256 KiB per file. Each section
  reports status, source, and freshness; truncation is surfaced as `partial`.
  `GET /api/calendar` requires a paired single-month date window of at most 31
  days and returns the strict `{status,items,source,freshness}` envelope.
  Items allow only opaque `id`, `kind`, `date`, optional `occurred_at`, and
  optional Task `status`; Journal labels are localized by the client.
- Tests cover authentication/origin rejection, no-session/forged approval,
  Promote fail-closed, real file reads, deferred status, Hermes server-side
  auth, SSE/stop, and same-origin SPA routing.

## Not yet verified or delivered

- Authenticated live compatibility against the deployed Hermes v0.21.5 API and
  service-side key provisioning. NAS read-only checks found port 8642 listening
  only on Hermes loopback; uncredentialed requests are rejected. App-to-Hermes
  integration requires a separately authorized internal bind/key configuration.
- Remaining V1 business modules and all previously accepted workflow
  regressions in the independent App.
- Production App/Core image, Compose integration, NAS deployment, DSM HTTPS
  runtime trusted-proxy/Cookie/SSE behavior, and browser acceptance. Offline
  tests cover exact proxy peer handling and Secure cookies when the trusted
  forwarded scheme is HTTPS.
- Production Promote. Hermes Knowledge remains read-only; Core Knowledge remains
  read-only and `SB_PROMOTE_ENABLED=false` in production.
- OS-level Promote process/UID and filesystem mount separation is not established
  by this local code. The existing worker is called in-process, so the new
  provenance verifier does not make Promote safe to enable. A dedicated worker
  identity, read-only approval evidence, narrowly writable Knowledge target, and
  deployment topology require separate design, review, and authorization.
- Journal has only local synthetic tests. It has not been deployed or mounted
  against the production `50-Journal` directory; no real Journal data was read
  or written.

Build the single-service candidate image from `web-app/` using `Dockerfile.app`.
Image building is not deployment. Do not change the production port, Compose,
containers, mounts, or Promote setting without separate authorization.

# Trusted channel adapter status

`create_trusted_channel_router()` is an opt-in router factory and is not
registered by the production `create_app()`. Synthetic HTTP tests inject a
test-only identity provider to validate explicit Inbox saves, event replay and
identity scoping. No real adapter authenticator, key rotation/revocation
service, channel consent source, or external attachment binding is implemented.
`approved_suggestion` and external attachment intake fail closed until Core
can verify their proposal/source/vocabulary or attachment bindings. Do not
register this router in production before those external authentication and
consent contracts are reviewed and implemented.
