# SecondBrain Core (development foundation)

Status: isolated development only; not deployed. This is the planned single
modular-monolith business service. Hermes remains the Agent Runtime and
Dashboard host; NAS files remain the data source of truth.

## Implemented in CORE-0

- `secondbrain_core/modules/review_promote/`: Review format adapter, trusted
  Dashboard request validation, SHA-256 pinning, idempotent approval storage,
  safe Knowledge creation, no-overwrite behavior, and append-only audit.
- `PromoteService` writes an approval record and invokes the Promote worker in
  the same Core process. The previous cross-container polling queue is not used
  by this Core path. The approval store must remain private to Core and outside
  ordinary Hermes file-tool roots.
- Review decisions are persisted by `(relative Review path, SHA-256)` version.
  States are `pending`, `deferred`, `approved`, `promoting`, `promoted`, and
  `failed`. A changed file version starts at `pending`; the Review source is
  retained. Approval records are durable before the Worker starts, so the same
  approved request can be retried after a worker error or process interruption.
- Knowledge creation is no-overwrite and atomic. If file creation succeeds but
  audit append fails, retry verifies the expected output hash and completes the
  missing audit entry. A torn final audit line is removed under the audit lock;
  malformed complete lines fail closed. Stuck `promoting` records remain
  visible and can be reconciled by retrying the same approved request.
- `secondbrain_core.app` exposes only the direct Core API. A user unlocks
  Promote with a Core-only secret, then approves through a short-lived,
  HttpOnly/Secure/SameSite cookie. Origin is exact, CORS is allowlisted, and
  the secret and sessions never pass through Hermes. The unlock secret is a
  provisioned file (0600 or stricter); it is not stored in source or Compose.
- The old Hermes-session write router and service entry point were removed.
  Core's app factory does not accept Hermes `request.state.session` for Promote.
- Read-only Review browsing uses the same-origin Hermes plugin API, which
  verifies the host-injected Dashboard session on each request. It does not
  use the Core unlock secret; Core-owned authorization remains for Promote.

## Module boundaries

Capture owns intake only when implemented. Review/Promote owns human approval
and the only future Knowledge write path. Journal, Knowledge read/query,
Projects, and Calendar are distinct future modules; no empty placeholder
packages are created in CORE-0. Hermes retains LLM, Chat, Skills, Gateway, and
native retrieval. Dashboard remains the existing plugin and FE-4 UI.

## Production boundary and blocker

Core must be the only service with Knowledge RW and private approval storage.
Hermes must lose its current Knowledge RW mount. Runtime evidence showed the
Hermes container is root and receives Basic Auth credentials in its own
environment, so Agent/Shell share that security boundary; Hermes cookie
forwarding and `/api/auth/me` are not an approval trust anchor. Dashboard's
server-side plugin API can validate the host-injected, unexpired Basic Auth
session per request for Review reads. That session alone does not prove a human
approval action. Core Promote still requires its own short-lived Core session;
removing that second unlock requires a separate design for a verifiable,
single-use owner approval assertion and a trust boundary that ordinary Agent
tools cannot use to mint one. Do not pass Hermes identity or `approved=true`
from browser fields to Core. The Core-owned unlock path passed isolated HTTP
tests. HTTPS ingress, exact DSM proxy trust, service UID/ACLs, and production
mount isolation remain BLOCKED pending actual NAS test-directory verification
and approved deployment. No production Compose, service, Dashboard, mount, or
data was changed.

## Isolated deployment candidate

`compose.core-isolated.yaml` is a candidate only. It keeps the Core upstream
bound to NAS loopback for the built-in DSM HTTPS reverse proxy; the browser
must call Core directly through that HTTPS endpoint, never through Hermes.
Set only the exact trusted DSM proxy peer in `SB_TRUSTED_PROXY_IPS` and route
via the same HTTPS site as Dashboard so Secure/SameSite cookies work. The NAS
responded on HTTPS ports 443 and 5001 during CORE-2, but route, certificate
hostname, proxy peer address, and DSM ACL were not established. The candidate
therefore cannot yet be promoted to production.

For the next deployment preparation, remove only Hermes' RW bind mount for
`20-Knowledge` and remove `/secondbrain-write` from `HERMES_WRITE_SAFE_ROOT`;
keep Hermes' RO `/secondbrain` mount and separately scoped Inbox/Review capture
mounts. Give Core UID `1026:100` the Knowledge RW bind mount and its private
state/approval/audit RW mount; keep Review and the unlock secret RO. Verify the
NAS directory ACLs, container effective UID, mount flags, and ordinary Hermes
write denial before enabling Promote. Roll back by disabling Promote and
returning Core's Knowledge mount to RO while retaining generated files and
audit evidence for reconciliation. Never restore Hermes Knowledge RW.

## Tests

Run the existing Promote regression suite from `../promote-worker` with the
isolated Python environment; Core-specific service/router tests are in
`tests/`. Tests use temporary directories only.
