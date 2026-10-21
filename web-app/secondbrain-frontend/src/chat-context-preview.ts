export type ContextStatus = 'available' | 'none' | 'partial' | 'unavailable';
export type ContextSourceKind = 'personal_memory' | 'knowledge';

export type ContextPreviewItem = {
  source_kind: ContextSourceKind;
  source_id: string;
  source_version: string;
  sha256: string;
  source_timestamp: string;
  fact_kind: string | null;
  verification_status: string;
  state: string;
  expires_at: string | null;
};

export type ContextPreview = {
  schema_version: 'context.v1';
  request_id: string;
  session_id: string;
  evaluated_at: string;
  status: ContextStatus;
  source_status: { personal_memory: ContextStatus; knowledge: ContextStatus };
  items: ContextPreviewItem[];
};

const STATUSES = new Set<ContextStatus>(['available', 'none', 'partial', 'unavailable']);
const SESSION_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$/;
const OPAQUE_ID = /^[A-Za-z0-9._~-]{8,256}$/;
const SHA256 = /^[a-f0-9]{64}$/;

function record(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function exactKeys(value: Record<string, unknown>, expected: string[]): boolean {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length && actual.every((key, index) => key === wanted[index]);
}

function boundedText(value: unknown, max = 128): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= max
    && /^[A-Za-z0-9][A-Za-z0-9._:-]*$/.test(value);
}

function isoDate(value: unknown): value is string {
  return typeof value === 'string' && value.length <= 64 && Number.isFinite(Date.parse(value));
}

function parseItem(value: unknown): ContextPreviewItem | null {
  if (!record(value) || !exactKeys(value, ['source_kind', 'source_id', 'source_version', 'sha256', 'source_timestamp', 'fact_kind', 'verification_status', 'state', 'expires_at'])) return null;
  if ((value.source_kind !== 'personal_memory' && value.source_kind !== 'knowledge')
    || typeof value.source_id !== 'string' || !OPAQUE_ID.test(value.source_id)
    || !boundedText(value.source_version, 128)
    || typeof value.sha256 !== 'string' || !SHA256.test(value.sha256)
    || !isoDate(value.source_timestamp)
    || (value.fact_kind !== null && !boundedText(value.fact_kind, 64))
    || !boundedText(value.verification_status, 64)
    || !boundedText(value.state, 64)
    || (value.expires_at !== null && !isoDate(value.expires_at))) return null;
  return value as ContextPreviewItem;
}

/** Strictly accepts the metadata-only Context v1 projection; unknown fields fail closed. */
export function parseContextPreview(value: unknown, expectedSessionId: string): ContextPreview | null {
  if (!record(value) || !exactKeys(value, ['schema_version', 'request_id', 'session_id', 'evaluated_at', 'status', 'source_status', 'items'])) return null;
  if (value.schema_version !== 'context.v1'
    || typeof value.request_id !== 'string' || !SESSION_ID.test(value.request_id)
    || value.session_id !== expectedSessionId || !SESSION_ID.test(expectedSessionId)
    || !isoDate(value.evaluated_at)
    || typeof value.status !== 'string' || !STATUSES.has(value.status as ContextStatus)
    || !record(value.source_status) || !exactKeys(value.source_status, ['personal_memory', 'knowledge'])
    || typeof value.source_status.personal_memory !== 'string' || !STATUSES.has(value.source_status.personal_memory as ContextStatus)
    || typeof value.source_status.knowledge !== 'string' || !STATUSES.has(value.source_status.knowledge as ContextStatus)
    || !Array.isArray(value.items) || value.items.length > 6) return null;

  const items: ContextPreviewItem[] = [];
  const seen = new Set<string>();
  const counts: Record<ContextSourceKind, number> = { personal_memory: 0, knowledge: 0 };
  for (const raw of value.items) {
    const item = parseItem(raw);
    if (!item) return null;
    counts[item.source_kind] += 1;
    if (counts[item.source_kind] > 3) return null;
    const key = `${item.source_kind}\0${item.source_id}\0${item.source_version}`;
    if (seen.has(key)) return null;
    seen.add(key);
    items.push(item);
  }
  if (new TextEncoder().encode(JSON.stringify(value)).byteLength > 8 * 1024) return null;
  if ((value.status === 'none' && items.length !== 0)
    || (value.status === 'available' && !items.length)
    || (value.status === 'unavailable' && items.length !== 0)) return null;
  return value as ContextPreview;
}

export async function fetchContextPreview(sessionId: string, query: string, signal: AbortSignal): Promise<ContextPreview> {
  const trimmed = query.trim();
  if (!SESSION_ID.test(sessionId) || [...trimmed].length < 1 || [...trimmed].length > 200) {
    throw Object.assign(new Error('Invalid context preview request'), { status: 400 });
  }
  const response = await fetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}/context-preview`, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store', signal,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ query: trimmed }),
  });
  const cacheControl = response.headers.get('Cache-Control')?.toLowerCase().split(',').map((value) => value.trim()) ?? [];
  if (!cacheControl.includes('private') || !cacheControl.includes('no-store')) {
    throw Object.assign(new Error('Context preview cache policy was not verified'), { status: 502 });
  }
  if (!response.ok) throw Object.assign(new Error('Context preview unavailable'), { status: response.status });
  const payload: unknown = await response.json();
  const parsed = parseContextPreview(payload, sessionId);
  if (!parsed) throw Object.assign(new Error('Invalid context preview response'), { status: 502 });
  return parsed;
}

/** Metadata-only natural recall contract. It never alters the Hermes Run payload. */
export async function fetchContextCandidates(sessionId: string, input: string, signal: AbortSignal): Promise<ContextPreview> {
  const trimmed = input.trim();
  if (!SESSION_ID.test(sessionId) || [...trimmed].length < 1 || [...trimmed].length > 2000) {
    throw Object.assign(new Error('Invalid context candidate request'), { status: 400 });
  }
  const response = await fetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}/context-candidates`, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store', signal,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ input: trimmed }),
  });
  const cacheControl = response.headers.get('Cache-Control')?.toLowerCase().split(',').map((value) => value.trim()) ?? [];
  if (!cacheControl.includes('private') || !cacheControl.includes('no-store')) {
    throw Object.assign(new Error('Context candidates cache policy was not verified'), { status: 502 });
  }
  if (!response.ok) throw Object.assign(new Error('Context candidates unavailable'), { status: response.status });
  const payload: unknown = await response.json();
  const parsed = parseContextPreview(payload, sessionId);
  if (!parsed) throw Object.assign(new Error('Invalid context candidate response'), { status: 502 });
  return parsed;
}
