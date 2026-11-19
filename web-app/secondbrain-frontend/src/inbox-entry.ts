export type VerifiedInboxEntry = {
  inboxId: string;
  status: 'pending' | 'prepared' | 'processing' | 'completed' | 'partial_success' | 'failed';
  capturedAt: string;
  occurredAt: string;
  sourceChannel: string;
  sourceEventId: string;
  intent: string;
  reviewPath: string | null;
  reviewSha256: string | null;
};

const inboxIdPattern = /^[0-9a-f]{32}$/;
const sha256Pattern = /^[0-9a-f]{64}$/;
const entryStatuses = new Set<VerifiedInboxEntry['status']>([
  'pending', 'prepared', 'processing', 'completed', 'partial_success', 'failed',
]);

function timestamp(value: unknown): value is string {
  return typeof value === 'string' && value.length <= 64 && Number.isFinite(Date.parse(value));
}

function safeReviewPath(value: unknown): value is string {
  if (typeof value !== 'string' || value.length > 1024
    || /[\\\u0000-\u001f\u007f?#]/.test(value)) return false;
  const parts = value.split('/');
  return parts.length > 0 && value.toLowerCase().endsWith('.md')
    && parts.every((part) => Boolean(part) && part !== '.' && part !== '..');
}

/** Parse only the exact Core GET projection. The linked route never loads Raw text. */
export function parseVerifiedInboxEntry(value: unknown, requestedId: string): VerifiedInboxEntry | null {
  if (!inboxIdPattern.test(requestedId) || !value || typeof value !== 'object' || Array.isArray(value)) return null;
  const body = value as Record<string, unknown>;
  const source = body.source as Record<string, unknown> | undefined;
  const evidence = body.consent_evidence as Record<string, unknown> | undefined;
  const sourceRef = body.source_ref as Record<string, unknown> | undefined;
  const approved = body.approved_proposal as Record<string, unknown> | null | undefined;
  const reviewPath = sourceRef?.review_path;
  const reviewSha = sourceRef?.review_sha256;
  const hasReview = typeof reviewPath === 'string' && typeof reviewSha === 'string' && sha256Pattern.test(reviewSha);
  const noReview = reviewPath === null && reviewSha === null;
  const intent = body.intent;
  const expectedEvidence = intent === 'approved_suggestion'
    ? 'authenticated_app_approved_proposal' : 'authenticated_app_explicit_action';
  const validApproval = intent === 'approved_suggestion' ? Boolean(approved
    && typeof approved.proposal_id === 'string' && /^[0-9a-f]{32}$/.test(approved.proposal_id)
    && typeof approved.version === 'number' && Number.isSafeInteger(approved.version) && approved.version > 0
    && ['journal', 'review', 'project'].includes(String(approved.kind))
    && typeof approved.source_version === 'string' && Boolean(approved.source_version)
    && evidence?.proposal_id === approved.proposal_id && evidence?.proposal_version === approved.version
    && evidence?.source_version === approved.source_version) : approved === null;
  if (body.inbox_id !== requestedId || typeof body.status !== 'string'
    || !entryStatuses.has(body.status as VerifiedInboxEntry['status'])
    || !timestamp(body.captured_at) || !timestamp(body.occurred_at)
    || typeof source?.channel !== 'string' || !/^[a-z][a-z0-9_-]{0,31}$/.test(source.channel)
    || typeof source.event_id !== 'string' || !/^[A-Za-z0-9._:-]{1,128}$/.test(source.event_id)
    || typeof intent !== 'string' || !['explicit_capture', 'journal_intent', 'task_intent', 'approved_suggestion'].includes(intent)
    || sourceRef?.capture_id !== requestedId
    || evidence?.kind !== expectedEvidence
    || typeof evidence.subject !== 'string' || !evidence.subject || !timestamp(evidence.recorded_at)
    || !validApproval
    || (!hasReview && !noReview) || (hasReview && !safeReviewPath(reviewPath))) return null;
  return {
    inboxId: requestedId,
    status: body.status as VerifiedInboxEntry['status'],
    capturedAt: body.captured_at,
    occurredAt: body.occurred_at,
    sourceChannel: source.channel,
    sourceEventId: source.event_id,
    intent,
    reviewPath: hasReview ? reviewPath as string : null,
    reviewSha256: hasReview ? reviewSha as string : null,
  };
}

export function inboxEntryStatusLabel(status: VerifiedInboxEntry['status'], en: boolean): string {
  const labels: Record<VerifiedInboxEntry['status'], [string, string]> = {
    pending: ['待处理', 'Pending'], prepared: ['已准备', 'Prepared'], processing: ['处理中', 'Processing'],
    completed: ['处理完成', 'Completed'], partial_success: ['部分完成', 'Partial success'], failed: ['处理失败', 'Failed'],
  };
  return labels[status][en ? 1 : 0];
}

export function inboxEntryErrorLabel(status: number | null, en: boolean): string {
  if (status === 401) return en ? 'Your session expired. Sign in again to verify this Inbox entry.' : '登录状态已失效；重新登录后可核验此 Inbox 条目。';
  if (status === 403) return en ? 'You are not allowed to read this Inbox entry.' : '当前账户无权读取此 Inbox 条目。';
  if (status === 404) return en ? 'This Inbox entry was not found.' : '找不到此 Inbox 条目。';
  if (status === null || status >= 500) return en ? 'Inbox status is temporarily unavailable; its state is unverified.' : 'Inbox 状态暂时不可用；当前状态未核验。';
  return en ? 'Core did not return a verifiable Inbox entry.' : 'Core 未返回可核验的 Inbox 条目。';
}
