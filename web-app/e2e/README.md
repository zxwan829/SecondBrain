# Synthetic browser acceptance

This package contains the manually dispatched Linux Chromium acceptance requested by Issue #96. It runs only against a temporary Core data root and a loopback Vite server. The App passphrase is generated per run, stored in a mode-0600 temporary file, and never written to GitHub Secrets or report files. Hermes is not configured; Chat endpoints are browser-only fixtures. Promote, model integrations, memory, and scheduler remain off.

The browser journey checks the blank Chat entry before any session is explicitly created, explicit `journal_intent` capture, a committed POST with its response deliberately lost, exact same-request retry, exact Inbox GET, changed-content 409, an untrusted-Origin 403, authentication refusal, ordinary chat without an Inbox write, protected API request denial, source-root protection, and horizontal overflow at 1440×1000, 820×1180, and 390×844.

```sh
npm ci --prefix web-app/secondbrain-frontend
npm ci --prefix web-app/e2e
python -m pip install -e 'web-app/secondbrain-core[test]'
cd web-app/secondbrain-frontend && npm run build
cd ../e2e && npx playwright install chromium && npm test
```

For a local non-browser Core/Vite smoke test that respects the macOS browser stop gate:

```sh
python web-app/e2e/scripts/run_synthetic_ci.py --http-smoke-only
```

The local smoke mode does not count as browser, click, screenshot, or viewport acceptance. On Linux CI, Playwright emits JUnit/HTML, failure screenshots and traces. Before upload, traces are reduced to loopback path/status/timing metadata and synthetic screenshots; headers, cookies, request/response bodies, snapshots, source and opaque IDs are removed. Temporary Core/Vite processes and all temporary data are deleted on success and failure.
