export type JournalInboxBody = {
  original_text: string;
  source_channel: 'web';
  source_event_id: string;
  occurred_at: string;
  intent: 'journal_intent';
};

export type JournalInboxAttempt = {
  sessionId: string;
  body: JournalInboxBody;
  bodyJson: string;
};

export type JournalInboxReceipt = {
  sessionId: string;
  inboxId: string;
  sourceEventId: string;
  occurredAt: string;
};

export const journalInboxIdPattern = /^[0-9a-f]{32}$/;
const sourceEventIdPattern = /^[A-Za-z0-9._:-]{1,128}$/;
const statuses = new Set(['pending', 'prepared', 'processing', 'completed', 'partial_success', 'failed']);

export const journalInboxAttemptKey = (sessionId: string) => `secondbrain.chat.journalInboxAttempt:${sessionId}`;
export const journalInboxReceiptKey = (sessionId: string) => `secondbrain.chat.journalInboxReceipt:${sessionId}`;

export function makeJournalInboxAttempt(sessionId: string, originalText: string,
                                        sourceEventId: string, occurredAt: string): JournalInboxAttempt {
  const body: JournalInboxBody = {
    original_text: originalText,
    source_channel: 'web',
    source_event_id: sourceEventId,
    occurred_at: occurredAt,
    intent: 'journal_intent',
  };
  return { sessionId, body, bodyJson: JSON.stringify(body) };
}

export function parseJournalInboxAttempt(raw: string | null, sessionId: string): JournalInboxAttempt | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Record<string, unknown>;
    const body = value?.body as Record<string, unknown> | undefined;
    if (value?.sessionId !== sessionId || !body || Object.keys(body).sort().join(',') !==
        ['intent', 'occurred_at', 'original_text', 'source_channel', 'source_event_id'].sort().join(',')) return null;
    if (typeof body.original_text !== 'string' || !body.original_text.trim() || body.original_text.length > 200000
      || body.source_channel !== 'web' || body.intent !== 'journal_intent'
      || typeof body.source_event_id !== 'string' || !sourceEventIdPattern.test(body.source_event_id)
      || typeof body.occurred_at !== 'string' || !Number.isFinite(Date.parse(body.occurred_at))
      || typeof value.bodyJson !== 'string' || value.bodyJson !== JSON.stringify(body)) return null;
    return { sessionId, body: body as unknown as JournalInboxBody, bodyJson: value.bodyJson };
  } catch { return null; }
}

export function parseJournalInboxReceipt(raw: string | null, sessionId: string): JournalInboxReceipt | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Record<string, unknown>;
    if (value?.sessionId !== sessionId || typeof value.inboxId !== 'string' || !journalInboxIdPattern.test(value.inboxId)
      || typeof value.sourceEventId !== 'string' || !sourceEventIdPattern.test(value.sourceEventId)
      || typeof value.occurredAt !== 'string' || !Number.isFinite(Date.parse(value.occurredAt))) return null;
    return value as unknown as JournalInboxReceipt;
  } catch { return null; }
}

function validTimestamp(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}

export function parseJournalInboxPostReceipt(value: unknown, attempt: JournalInboxAttempt): { inboxId: string; status: string } | null {
  if (!value || typeof value !== 'object') return null;
  const body = value as Record<string, unknown>;
  const source = body.source as Record<string, unknown> | undefined;
  const evidence = body.consent_evidence as Record<string, unknown> | undefined;
  if (typeof body.inbox_id !== 'string' || !journalInboxIdPattern.test(body.inbox_id)
    || typeof body.status !== 'string' || !statuses.has(body.status)
    || !validTimestamp(body.captured_at) || body.intent !== 'journal_intent'
    || source?.channel !== 'web' || source.event_id !== attempt.body.source_event_id
    || body.occurred_at !== undefined && (!validTimestamp(body.occurred_at)
      || Date.parse(body.occurred_at) !== Date.parse(attempt.body.occurred_at))
    || typeof body.replayed !== 'boolean'
    || evidence?.kind !== 'authenticated_app_explicit_action'
    || typeof evidence.subject !== 'string' || !evidence.subject || !validTimestamp(evidence.recorded_at)) return null;
  return { inboxId: body.inbox_id, status: body.status };
}

export function parseJournalInboxGet(value: unknown, receipt: JournalInboxReceipt): string | null {
  if (!value || typeof value !== 'object') return null;
  const body = value as Record<string, unknown>;
  const source = body.source as Record<string, unknown> | undefined;
  const evidence = body.consent_evidence as Record<string, unknown> | undefined;
  const sourceRef = body.source_ref as Record<string, unknown> | undefined;
  if (body.inbox_id !== receipt.inboxId || typeof body.status !== 'string' || !statuses.has(body.status)
    || body.intent !== 'journal_intent' || source?.channel !== 'web' || source.event_id !== receipt.sourceEventId
    || !validTimestamp(body.captured_at) || !validTimestamp(body.occurred_at)
    || Date.parse(body.occurred_at) !== Date.parse(receipt.occurredAt)
    || evidence?.kind !== 'authenticated_app_explicit_action'
    || typeof evidence.subject !== 'string' || !evidence.subject || !validTimestamp(evidence.recorded_at)
    || sourceRef?.capture_id !== receipt.inboxId) return null;
  return body.status;
}

export function journalInboxFailureLabel(status: number | null, en: boolean): string {
  if (status === 401) return en ? 'Login expired; the original text and exact request are retained. Sign in, then retry the same request.' : '登录已失效；原文和完整请求已保留。重新登录后可用同一请求重试。';
  if (status === 403) return en ? 'This account is not allowed to save to Inbox. The original text and request are retained.' : '当前账户无权写入 Inbox；原文和请求已保留。';
  if (status === 409) return en ? 'Core reported an event-key conflict. The original request is retained and was not replaced.' : 'Core 报告事件标识冲突；原请求已保留，没有改用新标识。';
  if (status === 422) return en ? 'Core rejected the Inbox request. The original text and exact request are retained.' : 'Core 拒绝了 Inbox 请求；原文和完整请求已保留。';
  if (status === 503 || status === null || (status >= 500 && status <= 599)) return en ? 'Inbox is temporarily unavailable or the result is unknown. Retry will reuse the exact same request.' : 'Inbox 暂时不可用或结果未知；重试会复用完全相同的请求。';
  return en ? 'Inbox did not confirm the save. The original text and exact request are retained.' : 'Inbox 尚未确认保存；原文和完整请求已保留。';
}
