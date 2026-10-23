# P2-2/P2-3 Web integration contract

This Web slice follows SecondBrain Issue #97 comments #6324517914 (P2-2) and #6324519836 (P2-3). It is stacked on Web PR #174 and is not deployable or independently mergeable until the matching Core endpoints and write semantics are available.

## P2-2 natural context candidates

- After a normal Chat Run is accepted, Web asynchronously posts only `{ "input": <the submitted user text> }` to `POST /api/chat/sessions/{session_id}/context-candidates`.
- The candidate request is best effort: it never delays or changes the Hermes Run request. Attachments and blank acceptance sessions skip it.
- Web applies Context v1 exact response parsing, session binding, source item count and byte budgets, `Cache-Control: private, no-store`, and abort/sequence protection across sessions.
- The UI labels results as possible related sources and says they were not added to Hermes input and do not establish grounding.
- `MODEL_CONTEXT_ADMISSION` remains blocked. No model prompt, message history, or Run payload receives candidate metadata or source content.

## P2-3 Personal Memory lifecycle

- The dedicated Memory page performs an authenticated, no-store `GET /api/personal-memory?limit=20`; history is fetched only after an explicit request.
- Correction and revocation require an explicit action, exact typed confirmation, a positive `expected_revision`, and an idempotency key. Network failure keeps the exact attempt for retry; its payload controls are locked until retry or cancellation. A conflict refreshes the active list.
- Web checks the returned receipt's memory ID and next revision before showing success. After a change the list refreshes, and the verified receipt can reopen revision history, including after revocation.
- No create/learn-from-chat control is exposed. Model output cannot trigger writes. No memory payload is persisted in browser storage.

## Compatibility and gate

The current Core P2-2 route and P2-3 CAS/idempotency contract are still being implemented on B's line. This PR intentionally targets the frozen request shapes; old Core may not enforce the expected-revision or idempotency fields. Keep this Draft until B's fixed Core HEAD provides those guarantees and the combined localhost gate verifies authorization-before-IO, conflict/replay behavior, refresh and session isolation. No real data, real Hermes/model, Writer/Promote, browser runtime, production, merge, deployment, or CI is included here.
