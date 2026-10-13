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
- `secondbrain_core.app` exposes only the direct Core API. A user unlocks
  Promote with a Core-only secret, then approves through a short-lived,
  HttpOnly/Secure/SameSite cookie. Origin is exact, CORS is allowlisted, and
  the secret and sessions never pass through Hermes. The unlock secret is a
  provisioned file (0600 or stricter); it is not stored in source or Compose.
- Hermes-authenticated approval router code remains only for historical test
  compatibility and must not be mounted by the production plugin. Core's app
  factory does not register it or accept Hermes `request.state.session`.
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
forwarding and `/api/auth/me` are not an approval trust anchor. The Core-owned
unlock path passed isolated HTTP tests. HTTPS ingress, exact DSM proxy trust,
service UID/ACLs, and production mount isolation remain BLOCKED pending actual
NAS test-directory verification and approved deployment. No production
Compose, service, Dashboard, mount, or data was changed.

## Isolated deployment candidate

`compose.core-isolated.yaml` is a candidate only. It keeps the Core upstream
bound to NAS loopback for the built-in DSM HTTPS reverse proxy; the browser
must call Core directly through that HTTPS endpoint, never through Hermes.
Set only the exact trusted DSM proxy peer in `SB_TRUSTED_PROXY_IPS` and route
via the same HTTPS site as Dashboard so Secure/SameSite cookies work. The NAS
responded on HTTPS ports 443 and 5001 during CORE-2, but route, certificate
hostname, proxy peer address, and DSM ACL were not established. The candidate
therefore cannot yet be promoted to production.

## Tests

Run the existing Promote regression suite from `../promote-worker` with the
isolated Python environment; Core-specific service/router tests are in
`tests/`. Tests use temporary directories only.
