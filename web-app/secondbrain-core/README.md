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
- `SB_PROMOTE_ENABLED` defaults to `false`. Keep it false until separately
  authorized production deployment, mount isolation, and approval validation.
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
  deployed v0.21.5 / `749220ef` `data` lists, nested `session.id`, and JSON SSE
  event payloads. The v0.22.2 pinned source also preserves these routes and
  maps `/v1/runs.instructions` to that run's ephemeral system prompt. Core
  regenerates relevant memory instructions per run; Hermes Memory Provider is
  not enabled, and Core JSONL remains authoritative. The API key is attached
  only by the server.
- Promote UI is guarded by Core's `promote_enabled` response and explicit user
  confirmation. Core defaults closed and retains SHA-256/version and audit
  protections.
- Tests cover authentication/origin rejection, no-session/forged approval,
  Promote fail-closed, real file reads, deferred status, Hermes server-side
  auth, SSE/stop, and same-origin SPA routing.

## Not yet verified or delivered

- Authenticated live compatibility against deployed Hermes v0.21.5, runtime
  behavior on v0.22.2, and service-side key provisioning. Source-contract and
  offline adapter tests do not replace an isolated v0.22.2 + deterministic Stub
  run. NAS read-only checks found port 8642 listening only on Hermes loopback;
  uncredentialed requests are rejected. App-to-Hermes integration requires a
  separately authorized internal bind/key configuration.
- Remaining V1 business modules and all previously accepted workflow
  regressions in the independent App.
- Production App/Core image, Compose integration, NAS deployment, DSM HTTPS
  runtime trusted-proxy/Cookie/SSE behavior, and browser acceptance. Offline
  tests cover exact proxy peer handling and Secure cookies when the trusted
  forwarded scheme is HTTPS.
- Production Promote. Hermes Knowledge remains read-only; Core Knowledge remains
  read-only and `SB_PROMOTE_ENABLED=false` in production.

Build the single-service candidate image from `web-app/` using `Dockerfile.app`.
Image building is not deployment. Do not change the production port, Compose,
containers, mounts, or Promote setting without separate authorization.
