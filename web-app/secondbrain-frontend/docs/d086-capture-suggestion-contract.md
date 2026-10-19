# D086 Web capture suggestion contract (synthetic v0)

**Status: frontend-only synthetic contract; proposed Core endpoint is not implemented on this base.** This file is for Mock/UI testing and is not evidence that a production Core deployment can accept this request.

## Suggestion event from the existing Chat Run SSE

The Web layer recognizes only a structured SSE JSON event named `capture.suggestion`:

```json
{
  "event": "capture.suggestion",
  "proposal_id": "synthetic-proposal-id",
  "source_event_id": "synthetic-source-event-id",
  "occurred_at": "2026-10-20T00:00:00Z",
  "original_text": "Exact proposed text"
}
```

The browser rejects missing, malformed, empty, or over-limit fields. Ordinary assistant text is never parsed as a suggestion. Receiving the event does not write or enqueue business data. The user must type the exact phrase `确认收录` and activate the explicit button.

## Confirm request

```http
POST /api/inbox/entries
Content-Type: application/json
Idempotency-Key: <proposal_id>
```

```json
{
  "original_text": "Exact proposed text",
  "source_channel": "web_chat",
  "source_event_id": "synthetic-source-event-id",
  "occurred_at": "2026-10-20T00:00:00Z",
  "intent": "approved_suggestion"
}
```

The `intent` field expresses the user's requested action; it is not authorization evidence. The Core must bind the authenticated principal and explicit action server-side, validate source identity and idempotency, and own durable Inbox creation. The frontend does not choose suggestion thresholds, persist proposals, or retry automatically.

## Success and failure

Synthetic success is HTTP `201` with `{ "inbox_id": "<opaque-id>", "status": "accepted", "captured_at": "<ISO timestamp>", "source": { "capture_id": "<32 lowercase hex characters>" } }`. `inbox_id` is the Core entry identity; the nested source `capture_id` must match the current Inbox summary's existing identifier. The UI shows `/inbox#capture-<source.capture_id>` only after validating this response. The Inbox renders entries with a matching `capture_id` as `id="capture-<capture_id>"`.

Non-2xx responses remain failures; the UI retains the suggestion text and displays the sanitized localized Core error. HTTP `409` is a conflict/stale proposal and is not treated as success. A malformed 2xx response is also failure. No HTTP status implies durable success unless Core returns the expected accepted payload.

## Contract gap

Issue #97 proposes `POST /api/inbox/entries` and channel-neutral capture fields, but leaves exact schema/status to a future Core PR. Before real integration, B must either adopt this synthetic v0 contract or publish a compatible frozen contract. The current frontend tests mock it; no real Core endpoint, server-side consent binding, persistence, or production workflow was exercised.

## Local Mock demonstration and coverage

1. Send an ordinary synthetic chat prompt and return a structured `capture.suggestion` SSE event. Confirm that the preview alone makes no Inbox request.
2. Enter anything other than the exact phrase and confirm submit stays disabled. Enter `确认收录`; return a valid 201 and verify the Inbox link appears only after validating the response and opaque source ID.
3. Repeat with HTTP 409 and malformed HTTP 2xx bodies; the suggestion remains visible, an error is shown, and no success link appears.
4. Start a Run in synthetic Session A, switch to Session B before its delayed SSE arrives, then return the suggestion and terminal frame. The stale proposal must not appear and no Inbox write may occur.
5. Open Inbox with `#capture-<32-hex-id>` while its list request is pending. Once the synthetic list resolves, verify the exact row receives focus and scrolls into view. When the loaded list omits the ID, verify the explicit not-found status.

These steps describe local synthetic tests only. Real Core HTTP behavior, browser login/session behavior, production persistence, and user acceptance remain NOT RUN.
