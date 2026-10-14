# SecondBrain App frontend

Standalone React + TypeScript + Vite application. It mounts its own React root,
serves the FE-4 visual shell, and calls only same-origin `/api/*` endpoints.
Hermes credentials are server-side and must never be added to `VITE_*` values.

Run `npm ci`, `npm run typecheck`, and `npm run build`. For local development,
start the Core/App API on `127.0.0.1:8000`, then run `npm run dev`; Vite proxies
`/api` to that service. For the single-container image, build from `web-app/`
with `Dockerfile.app`; it builds the frontend and copies the static output into
the existing Core/App service image.
