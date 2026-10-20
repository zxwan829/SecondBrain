# A Web-only synthetic integration evidence

This document records local Web integration evidence for Issue #96. The Vitest walkthrough uses React/jsdom and mocked HTTP responses; a separate isolated Edge run now exercises the fixed frontend against a real local Core HTTP process and temporary synthetic roots. Neither run calls Hermes, accesses NAS, Vault, production accounts, or real data. Promote remains OFF.

## Frozen inputs and status

- A frontend base: PR #98 HEAD `98b2ed52eb68bb02f0cb190e92b1c425348b099f`.
- B wire contract reference only: PR #99 HEAD `c92634fd94b32fec47e50aa7ef4ba107d98f7520`. No B source is merged into this candidate.
- B Core readiness remains `NOT_MET`; B3 real OS UID/ACL/mount validation is out of scope and is not awaited.
- This candidate is stacked on PR #98 because the App-level Home-effect fix and synthetic integration test depend on its unmerged frontend. It is not an independent PR against `main`; merge order must keep #98 before this integration PR.

## Reproducible synthetic walkthrough

Run from `web-app/secondbrain-frontend`:

```sh
npm test -- --run src/web-synthetic-integration.test.tsx
```

The `requires explicit Inbox, Review, Promote, search and detail actions and preserves the exact mocked contract` test performs:

| Step | Explicit UI action | Allowed mock request(s) | Expected state and negative assertion |
| --- | --- | --- | --- |
| 1 | Open `/inbox` | `GET /api/auth/session` | Scope chooser only. No `/api/home`, inbox data, Review, Promote, Knowledge, Notes, or Chat request. |
| 2 | Choose `Capture 待处理` | `GET /api/inbox/summary?limit=100` | One synthetic Capture summary appears. Organizer status/run is not requested. |
| 3 | Open the listed Capture | `GET /api/capture/{synthetic-id}`, then `GET /api/inbox/{synthetic-id}/preview` | Only that ID's metadata and text preview appear. |
| 4 | Choose `查看对应 Review` | `GET /api/promote/review/items`, exact `GET /api/promote/review/items/{review_path}`, `GET /api/promote/status` | URL carries the exact encoded source path. No other Review detail is read. No `/api/home` is issued during Inbox-to-Review navigation. |
| 5 | Select the exact Review, then request a preview | `POST /api/promote/review/preview` with exact path, source SHA, and target | Full source/projected Markdown and target facts are rendered. No write is implied by preview. |
| 6 | Enter the synthetic-only passphrase and explicitly confirm | `POST /api/promote/auth/unlock`, `POST /api/promote/review/confirm` with `confirm_intent: promote_exact_preview`, then exact operation GET | Confirm is sent once. Initial `confirmed` remains pending; only matching `promoted` status and output SHA produces success. No legacy approve route is called. |
| 7 | Follow the explicit Knowledge link, submit a non-empty search, open a result | `GET /api/knowledge/search?q=...&limit=50`, then only selected opaque detail ID | No search occurs on route load. Verified, unverified, and missing provenance states remain distinct in the detail UI. |

The same file contains two negative integration checks:

- `fails closed for Promote OFF and an explicit HTTP 423 without unlock, confirm or a success link`: only the preview POST is made; no unlock, confirm, operation read, or Knowledge success link appears.
- `keeps recovery_required fail-closed after one confirmation and does not suggest success`: one confirm and one operation read; the UI asks for recovery review, keeps confirm disabled, and offers no Knowledge success link.

## Reused regression evidence

The following existing tests are run alongside the new App-level test; they cover specific cases without duplicating Core-side tests:

- `capture-flow.test.tsx`: `requires an explicit Core approval check, posts the exact 202 contract, and confirms the single Inbox entry by GET`; `keeps a valid 202 receipt unverified and hides its source link when the exact GET mismatches`; `restores an opaque session receipt without a trusted link while exact GET is pending or fails`; `fails closed when SSE has only the untrusted legacy proposal_id`; `retries an uncertain POST with the same event identity and restores only the session-bound receipt`; `ignores a capture suggestion delivered by an old Run after switching sessions`.
- `PromotePreviewPanel.test.tsx`: `requires preview, independent unlock, explicit one-time confirm and server status before saying complete`; `does not replay a confirmation whose response is lost; it queries the operation instead`; `requires a fresh preview after a stale response and never exposes raw error details`; HTTP 401/403/409/410/423/429/503 safe-message cases; malformed Preview and mismatched operation ID/output hash cases.
- `ReviewPage.promote.test.tsx`: list-only default, explicit detail selection, stale detail clearing, unmount abort, and late detail response isolation.
- `KnowledgePage.test.tsx`: no passive request before explicit search, explicit selected detail only, unverified provenance, stale response isolation, authorization failure clearing, and detail abort on unmount.

These are frontend tests against Mock HTTP or isolated component APIs, not real Core HTTP, browser E2E, Hermes channel integration, filesystem promotion, or production business acceptance.

## Isolated real Core HTTP + Edge retest (2026-10-20)

- Fixed inputs: frontend is PR #98 `98b2ed52eb68bb02f0cb190e92b1c425348b099f` plus this PR's candidate; Core is PR #99 `c92634fd94b32fec47e50aa7ef4ba107d98f7520`.
- Core ran on `https://127.0.0.1:39697` with a temporary self-signed loopback certificate and a fresh private temporary root containing only synthetic Raw, Review, Knowledge, and Core state. `SB_PROMOTE_ENABLED=false`; Hermes was not configured.
- Edge used a new headless temporary context, blocked Service Workers and all non-loopback origins. Chat session creation, Run, and SSE were mocked; Proposal History, login, Inbox POST, exact receipt GET, and Review list/status were real Core HTTP.
- Seeded and approved one synthetic Review proposal whose `suggestion.original.value` exactly equaled the synthetic SSE `originalText`. History returned the real Core object shape; Web accepted it only after exact equality validation.
- Redacted HTTP sequence: anonymous proposal read `401`; App login `200`; synthetic seed `202`; proposal create/decision/history `200`; after explicit UI confirmation, approved Inbox POST `202`; same opaque Inbox ID GET `200`. POST and GET bindings matched source event ID, proposal ID/version, and `source_ref.capture_id`.
- Blank route login was `GET /api/auth/session 401` → `POST /api/auth/login 200`; direct `/chat/blank` and subsequent direct `/review` each produced **zero** `/api/home` requests. Blank entry issued no session-list GET. The receipt stored in sessionStorage was bound to the newly created synthetic session ID.
- External request count was zero. No model/Hermes call, Promote confirmation, production data, NAS access, or deployment occurred. The temporary Core process was stopped after the run; redacted evidence remains outside the repository under `/private/tmp/secondbrain96-object-home-20261020/`.

## Detected frontend issue and fix

The App-level test reproduced an unintended `GET /api/home` at `/review` while leaving Inbox for an exact Review. Updating the previous-page ref before the transition guard meant a repeated effect execution could see Review as the previous page and fall through to the broad Home aggregate. `App.tsx` now retains a one-transition suppression marker across effect re-entry (including StrictMode replay) and clears it on the next route. The new App-level test asserts that no Home request occurs through Inbox → Review → Knowledge.

## Boundaries and remaining checks

- The synthetic Promote success fixture proves frontend request/response handling only. It is not evidence of Promote being enabled, a write occurring, or Core output correctness.
- No real filesystem Promote output hash, service-side idempotency, cross-process claim, Core restart recovery, actual Hermes adapter, UID/ACL/mount, or B3 readiness was exercised here.
- Full integration and production readiness remain unclaimed. A ChatGPT review is required before merge; no merge, deployment, NAS access, or real data access is part of this candidate.
