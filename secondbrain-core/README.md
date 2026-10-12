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
- The router factory can be mounted under the existing Hermes plugin route
  prefix. Its tests simulate `request.state.session`; they do not prove the
  production Hermes middleware contract or NAS mount isolation.

## Module boundaries

Capture owns intake only when implemented. Review/Promote owns human approval
and the only future Knowledge write path. Journal, Knowledge read/query,
Projects, and Calendar are distinct future modules; no empty placeholder
packages are created in CORE-0. Hermes retains LLM, Chat, Skills, Gateway, and
native retrieval. Dashboard remains the existing plugin and FE-4 UI.

## Production boundary and blocker

Core must be the only service with Knowledge RW and private approval storage.
Ordinary Hermes must have no Knowledge RW mount and no access to Core's private
approval state. Do not treat the simulated FastAPI session in isolated tests as
proof that the production Hermes plugin can validate the login session. The
actual Hermes auth middleware/context and a non-bypassable Dashboard-to-Core
request path remain BLOCKED pending integration evidence. No Compose or
production service change was made.

## Tests

Run the existing Promote regression suite from `../promote-worker` with the
isolated Python environment; Core-specific service/router tests are in
`tests/`. Tests use temporary directories only.

## Canonical source and recovery

The NAS project assets are `web-app/secondbrain-core/` and the sibling
`web-app/promote-worker/` compatibility source and tests. `CORE-0.bundle` in
this directory is a Git bundle rooted at `web-app`; it contains both source
directories and their tests. Restore a working checkout with
`git clone /path/to/CORE-0.bundle core0-baseline`. The legacy Promote patch files
are historical candidates and are not production-ready. Create a new verified
bundle after each accepted source milestone; do not use the Codex temporary
workspace as the only source copy.
