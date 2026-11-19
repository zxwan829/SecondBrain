import { describe, expect, it } from 'vitest';
import { parseVerifiedInboxEntry } from './inbox-entry';

const id = 'a'.repeat(32);
const base = {
  inbox_id: id, status: 'processing', captured_at: '2026-10-21T01:02:03Z', occurred_at: '2026-10-21T01:00:00Z',
  source: { channel: 'web', event_id: 'synthetic-event-1' }, intent: 'journal_intent',
  consent_evidence: { kind: 'authenticated_app_explicit_action', subject: 'synthetic-user', recorded_at: '2026-10-21T01:00:00Z' },
  approved_proposal: null,
  source_ref: { capture_id: id, review_path: null, review_sha256: null },
};
const invalidCases: Array<[unknown, string]> = [
  [{ ...base, inbox_id: 'b'.repeat(32) }, 'different entry id'],
  [{ ...base, status: 'unknown' }, 'unknown status'],
  [{ ...base, source_ref: { ...base.source_ref, capture_id: 'b'.repeat(32) } }, 'different capture binding'],
  [{ ...base, source_ref: { ...base.source_ref, review_path: '10-Review/../../private.md', review_sha256: 'b'.repeat(64) } }, 'path traversal'],
  [{ ...base, source_ref: { ...base.source_ref, review_path: '../private.md', review_sha256: 'b'.repeat(64) } }, 'relative path traversal'],
  [{ ...base, source_ref: { ...base.source_ref, review_path: '10-Review/item.md', review_sha256: 'bad' } }, 'unpaired source hash'],
];

describe('verified Inbox entry projection', () => {
  it('accepts the exact bounded Core status projection without exposing original text', () => {
    expect(parseVerifiedInboxEntry(base, id)).toMatchObject({ inboxId: id, status: 'processing', intent: 'journal_intent' });
  });

  it.each(invalidCases)('rejects %s', (payload) => {
    expect(parseVerifiedInboxEntry(payload, id)).toBeNull();
  });

  it('accepts the exact Core-relative Review path paired with a SHA-256 source version', () => {
    expect(parseVerifiedInboxEntry({ ...base, source_ref: {
      capture_id: id, review_path: 'Inbox-synthetic note.md', review_sha256: 'c'.repeat(64),
    } }, id)?.reviewPath).toBe('Inbox-synthetic note.md');
  });

  it('requires approved-suggestion consent evidence to bind the same Proposal ID, version, and source version', () => {
    const proposal = { proposal_id: 'd'.repeat(32), version: 4, kind: 'review', source_version: 'source-v4' };
    const approved = { ...base, intent: 'approved_suggestion', approved_proposal: proposal,
      consent_evidence: { kind: 'authenticated_app_approved_proposal', subject: 'synthetic-user',
        recorded_at: '2026-10-21T01:00:00Z', proposal_id: proposal.proposal_id, proposal_version: proposal.version,
        source_version: proposal.source_version } };
    expect(parseVerifiedInboxEntry(approved, id)?.intent).toBe('approved_suggestion');
    expect(parseVerifiedInboxEntry({ ...approved, consent_evidence: { ...approved.consent_evidence, proposal_version: 5 } }, id)).toBeNull();
  });
});
