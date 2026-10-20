# D086 Web capture suggestion contract

**Status:** frontend consumes the frozen local wire contract from PR #99 HEAD `407ab602a9f286aade434359e4bff8340dec6a05` using synthetic HTTP tests only. PR #99 is not treated as merged or production-ready; B reports `B_CORE_LOCAL_READY=NOT MET` because trusted external-channel integration and OS-level isolation remain incomplete.

## Suggestion and approval proof

The Chat UI accepts a structured `capture.suggestion` SSE event for display only. Its `source_event_id`, `occurred_at`, and exact `original_text` are bounded and validated. The old SSE `proposal_id` is not an authorization credential. To make submission available, the event must include `approved_proposal_id` (32 lowercase hex) and `approved_proposal_version` (positive integer).

The user must explicitly request verification. The browser then fetches only the exact proposal history:

```http
GET /api/inbox/proposals/{approved_proposal_id}/history
```

The frontend requires an exact proposal ID, `approved_recorded` status, matching version, supported kind (`journal`, `review`, or `project`), non-empty current `source_version`, integer `vocabulary_version`, and `proposal.suggestion.original` byte-for-byte equal to the proposed text. Any absent, stale, mismatched, unauthorized, or malformed proof fails closed. This GET is not a write and does not cause the page to enumerate proposals. The Core rechecks source and vocabulary at POST time.

The current PR #99 Core registers only authenticated App web identity; it does not yet provide a trusted Hermes identity adapter or a Chat-source Proposal creation path. Therefore a Hermes SSE event without a genuine, current Core-approved binding remains display-only. The frontend never converts it to `explicit_capture` as a fallback. A browser-supplied ID alone does not establish that such an adapter exists.

## Explicit confirm and exact wire

After the exact Core approval has been checked, the user must type `确认收录` and activate the submit button. The frontend sends:

```http
POST /api/inbox/entries
Content-Type: application/json
```

```json
{
  "original_text": "Exact approved source text",
  "source_channel": "web",
  "source_event_id": "stable-event-key",
  "occurred_at": "2026-10-20T01:02:03Z",
  "intent": "approved_suggestion",
  "approved_proposal_id": "32-lowercase-hex-characters",
  "approved_proposal_version": 4
}
```

No client-supplied identity or consent evidence is sent. There is no `Idempotency-Key` header: Core derives idempotency from authenticated channel identity plus the stable `source_event_id`. A retry after an uncertain network result reuses the same event ID and exact request body.

Only HTTP **202** is accepted. The frontend validates `inbox_id` as a 32-hex Capture ID, `captured_at`, `status`, source `{channel:"web",event_id}`, `intent`, `replayed`, the server-issued consent evidence and its proposal/source-version binding, and the returned approved-proposal binding. It renders 202 as “Core accepted; current processing status: …”; it never presents 202 as Review completion or Knowledge publication.

The UI then requests only:

```http
GET /api/inbox/entries/{inbox_id}
```

The exact GET must match the saved event, proposal/version, source version, authenticated Core consent evidence, and `source_ref.capture_id`. A validated opaque receipt is stored in `sessionStorage` under a key scoped to the Hermes Session ID; no proposed text or consent subject is stored. On refresh the app restores only that session's exact receipt and performs one ID-addressed GET, never an Inbox list scan. Switching sessions clears visible state and invalidates late responses. Failure, unknown status, malformed 2xx, 401/403/409/503, or response mismatch cannot be shown as successful processing.

## Synthetic regression cases

- No proposal GET or Inbox POST occurs merely from receiving the event.
- Legacy `proposal_id` without the Core-approved ID/version remains display-only and cannot submit.
- Exact Core history approval permits the explicitly confirmed request; stale status, ID/version mismatch, source text mismatch, and malformed approval block POST.
- HTTP 202 with matching source, proposal, and consent bindings is accepted as processing/queued only; 200/201, malformed 202, unknown status, or a mismatched GET cannot claim success.
- 401/403/409/503 and network ambiguity do not create a success state. A retry uses the exact same event ID/body; Core's `replayed` result and the exact GET are checked.
- Refresh restores only one Session-scoped opaque receipt. Switching Session does not query or display another session's receipt. Late SSE from an old Session is ignored.

All verification here is local frontend HTTP mocking. No real Hermes trusted adapter, actual Core process, production persistence, real Vault, browser login, model call, or production acceptance was exercised. `B_CORE_LOCAL_READY` remains separate from this A-line local readiness, and PR #98 must not be described as A/B integration or production approval.
