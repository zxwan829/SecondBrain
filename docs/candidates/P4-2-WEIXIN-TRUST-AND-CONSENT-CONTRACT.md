# P4-2 Weixin trust and consent contract candidate

Status: **candidate for review; not a production integration contract**.

Scope: synthetic-only validation of the existing Hermes v0.22.2 native Weixin
channel path and the opt-in Core adapter in PR #101/#237. This candidate does
not register the adapter in the application, create platform credentials, or
claim that a real Weixin account can be connected.

## Proposed minimum contract

1. **Authenticate before identity mapping.** The adapter accepts only an event
   delivered by the authenticated Hermes native Gateway path. The verifier
   authenticates the exact request bytes and the configured adapter/tenant.
   Request JSON, message text, display names, and forwarded headers cannot
   assert a Core principal, consent, or channel.
2. **Map a verified platform subject server-side.** A configured allowlist maps
   an authenticated platform subject to one stable Core principal. Unknown or
   unmapped subjects fail closed. The Core route is not directly exposed as a
   platform webhook.
3. **Require an explicit capture action.** Ordinary conversation is not Inbox
   input. A capture event must carry an explicit user action/consent record
   bound to the authenticated principal, source event, exact original content
   digest, intent, and occurrence time. Core stores the consent evidence ID;
   body fields cannot supply it.
4. **Check current consent on every delivery.** The trusted provider checks
   that the grant is currently active before Core performs either a new write
   or an idempotent replay. Revocation blocks both. This synthetic candidate
   models that check; the production consent registry and revocation API are
   not implemented here.
5. **Make intake idempotent.** The stable event namespace is
   `(channel, adapter, tenant, Core principal, native event ID)`. Same key and
   same authenticated request digest returns the existing Inbox ID without a
   second Raw write, including after Core restart. Same key with changed
   content, intent, attachments, or consent evidence returns conflict and does
   not overwrite the original.
6. **Fail closed for unsupported payloads.** Attachments remain rejected until
   a separate contract binds platform media IDs, sender/event, bounded
   download, content hash, and Core Capture record. No platform message is
   treated as approval for Journal, Task execution, Knowledge, or Promote.

## Open decisions before a real account integration

- Confirm the precise Hermes Gateway caller-authentication mechanism and
  Weixin adapter identity fields for the deployed v0.22.2 image.
- Define consent creation, renewal, expiry, revocation authority, and what
  happens to already accepted Inbox records after revocation. This candidate
  only specifies that revocation blocks future intake/replay; it does not
  delete prior records.
- Confirm allowed direct/group-chat and message-type matrix, and whether the
  platform's supported account flow is available for the intended deployment.
- Separately authorize real QR binding and end-to-end account acceptance.

The synthetic test provider uses a test-only fixed key and synthetic identities.
It is not suitable for deployment and is not a real Hermes protocol simulator.
