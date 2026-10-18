export type PromotePreviewRequest = {
  review_path: string;
  review_sha256: string;
  target_filename: string;
};

export type PromotePreview = {
  preview_id: string;
  request_id: string;
  expires_at: string;
  source_sha256: string;
  target_filename: string;
  target_precondition: Record<string, unknown>;
  source_markdown: string;
  projected_markdown: string;
  output_sha256: string;
  change_summary: string | string[];
};

export type PromoteOperation = {
  request_id: string;
  status: 'confirmed' | 'claimed' | 'promoting' | 'promoted' | 'already_promoted' | 'recovery_required' | 'failed';
  output_sha256?: string;
  error_code?: string;
};

export class PromoteApiError extends Error {
  constructor(readonly status: number, readonly code?: string) {
    super(`Promote request failed (${status})`);
    this.name = 'PromoteApiError';
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

async function requestJson(url: string, init: RequestInit, signal: AbortSignal): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(url, { ...init, credentials: 'same-origin', cache: 'no-store', signal });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new PromoteApiError(0);
  }
  let payload: unknown = null;
  try { payload = await response.json(); } catch { /* do not expose an untrusted response body */ }
  if (!response.ok) {
    const code = isRecord(payload) && typeof payload.code === 'string' ? payload.code : undefined;
    throw new PromoteApiError(response.status, code);
  }
  return payload;
}

function isSha256(value: unknown): value is string {
  return typeof value === 'string' && /^[a-f0-9]{64}$/i.test(value);
}

function isAbsoluteIsoDateTime(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,9})?(?:Z|([+-])(\d{2}):(\d{2}))$/.exec(value);
  if (!match) return false;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText, , offsetHourText, offsetMinuteText] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const daysInMonth = [31, (year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)) ? 29 : 28,
    31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (month < 1 || month > 12 || day < 1 || day > daysInMonth[month - 1]
    || Number(hourText) > 23 || Number(minuteText) > 59 || Number(secondText) > 59
    || (offsetHourText !== undefined && (Number(offsetHourText) > 23 || Number(offsetMinuteText) > 59))) return false;
  return Number.isFinite(Date.parse(value));
}

function parsePreview(value: unknown): PromotePreview {
  if (!isRecord(value) || typeof value.preview_id !== 'string' || !value.preview_id
    || typeof value.request_id !== 'string' || !value.request_id
    || !isAbsoluteIsoDateTime(value.expires_at)
    || !isSha256(value.source_sha256) || typeof value.target_filename !== 'string' || !value.target_filename
    || !isRecord(value.target_precondition) || typeof value.target_precondition.exists !== 'boolean'
    || value.target_precondition.exists !== false || typeof value.source_markdown !== 'string'
    || typeof value.projected_markdown !== 'string' || !isSha256(value.output_sha256)
    || !(typeof value.change_summary === 'string'
      || (Array.isArray(value.change_summary) && value.change_summary.every((entry) => typeof entry === 'string')))) {
    throw new PromoteApiError(502, 'invalid_preview_response');
  }
  return value as unknown as PromotePreview;
}

function parseOperation(value: unknown, expectedRequestId: string, expectedOutputSha256: string): PromoteOperation {
  const statuses = ['confirmed', 'claimed', 'promoting', 'promoted', 'already_promoted', 'recovery_required', 'failed'];
  if (!isRecord(value) || typeof value.request_id !== 'string' || value.request_id !== expectedRequestId
    || typeof value.status !== 'string' || !statuses.includes(value.status)
    || (value.output_sha256 !== undefined && !isSha256(value.output_sha256))
    || (value.error_code !== undefined && (typeof value.error_code !== 'string' || !/^[a-z0-9_]{1,64}$/i.test(value.error_code)))) {
    throw new PromoteApiError(502, 'invalid_operation_response');
  }
  if ((value.status === 'promoted' || value.status === 'already_promoted')
    && (!isSha256(value.output_sha256) || value.output_sha256.toLowerCase() !== expectedOutputSha256.toLowerCase())) {
    throw new PromoteApiError(502, 'operation_output_mismatch');
  }
  return value as unknown as PromoteOperation;
}

export const promoteApi = {
  async preview(body: PromotePreviewRequest, signal: AbortSignal): Promise<PromotePreview> {
    const value = await requestJson('/api/promote/review/preview', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }, signal);
    const preview = parsePreview(value);
    if (preview.source_sha256.toLowerCase() !== body.review_sha256.toLowerCase()
      || preview.target_filename !== body.target_filename) {
      throw new PromoteApiError(502, 'preview_source_mismatch');
    }
    return preview;
  },

  async unlock(passphrase: string, signal: AbortSignal): Promise<void> {
    const value = await requestJson('/api/promote/auth/unlock', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ passphrase }),
    }, signal);
    if (!isRecord(value) || !['ok', 'unlocked'].includes(String(value.status))) {
      throw new PromoteApiError(502, 'invalid_unlock_response');
    }
  },

  async lock(signal: AbortSignal): Promise<void> {
    const value = await requestJson('/api/promote/auth/lock', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
    }, signal);
    if (value !== null && (!isRecord(value) || !['ok', 'locked'].includes(String(value.status)))) {
      throw new PromoteApiError(502, 'invalid_lock_response');
    }
  },

  async confirm(previewId: string, expectedRequestId: string, signal: AbortSignal): Promise<void> {
    const value = await requestJson('/api/promote/review/confirm', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preview_id: previewId, confirm_intent: 'promote_exact_preview' }),
    }, signal);
    if (!isRecord(value) || typeof value.request_id !== 'string' || value.request_id !== expectedRequestId) {
      throw new PromoteApiError(502, 'invalid_confirm_response');
    }
  },

  async operation(requestId: string, expectedOutputSha256: string, signal: AbortSignal): Promise<PromoteOperation> {
    return parseOperation(await requestJson(`/api/promote/operations/${encodeURIComponent(requestId)}`, {}, signal), requestId, expectedOutputSha256);
  },
};
