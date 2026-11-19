export type PersonalMemory = {
  memory_id: string;
  revision: number;
  content: { text: string };
  category: string;
  fact_kind: string;
  status: string;
  revision_status?: string;
  recorded_at: string;
  expires_at?: string | null;
  source?: { type: string; ref: string };
};

const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const categories = new Set(['preference', 'experience', 'project_context', 'fact']);
const factKinds = new Set(['user_stated', 'user_confirmed', 'inference']);
const memoryStatuses = new Set(['active', 'pending_verification', 'revoked', 'expired', 'superseded']);

function parseMemory(value: unknown): PersonalMemory | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const row = value as Record<string, unknown>;
  const content = row.content && typeof row.content === 'object' && !Array.isArray(row.content)
    ? row.content as Record<string, unknown> : null;
  if (typeof row.memory_id !== 'string' || !SAFE_ID.test(row.memory_id)
    || !Number.isSafeInteger(row.revision) || (row.revision as number) < 1
    || !content || typeof content.text !== 'string' || content.text.length > 4000
    || typeof row.category !== 'string' || !categories.has(row.category)
    || typeof row.fact_kind !== 'string' || !factKinds.has(row.fact_kind)
    || typeof row.status !== 'string' || !memoryStatuses.has(row.status) || typeof row.recorded_at !== 'string' || row.recorded_at.length > 64
    || !Number.isFinite(Date.parse(row.recorded_at))) return null;
  const sourceValue = row.source;
  const sourceType = sourceValue === undefined ? row.source_type : undefined;
  const sourceRef = sourceValue === undefined ? row.source_ref : undefined;
  let source: PersonalMemory['source'];
  if (sourceValue !== undefined) {
    if (!sourceValue || typeof sourceValue !== 'object' || Array.isArray(sourceValue)) return null;
    const value = sourceValue as Record<string, unknown>;
    if (!isSafeSource(value.type, value.ref)) return null;
    source = { type: value.type as string, ref: value.ref as string };
  } else if (sourceType !== undefined || sourceRef !== undefined) {
    // Core's stable Personal Memory event response uses flat source_type/source_ref
    // fields; accept that authoritative wire shape as well as the legacy Web mock.
    if (!isSafeSource(sourceType, sourceRef)) return null;
    source = { type: sourceType as string, ref: sourceRef as string };
  }
  return { memory_id: row.memory_id, revision: row.revision as number,
    content: { text: content.text }, category: row.category, fact_kind: row.fact_kind,
    status: row.status, recorded_at: row.recorded_at,
    revision_status: typeof row.revision_status === 'string' ? row.revision_status : undefined,
    expires_at: typeof row.expires_at === 'string' || row.expires_at === null ? row.expires_at : undefined, source };
}

function isSafeSource(type: unknown, ref: unknown): type is string {
  return typeof type === 'string' && /^[A-Za-z0-9._-]{1,64}$/.test(type)
    && typeof ref === 'string' && ref.length <= 512 && !ref.startsWith('/') && !ref.includes('\\')
    && !ref.split('/').includes('..') && /^[A-Za-z0-9_.:/#@+ -]+$/.test(ref);
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(path, { credentials: 'same-origin', cache: 'no-store', ...init,
    headers: { Accept: 'application/json', ...(init?.body ? { 'Content-Type': 'application/json' } : {}), ...init?.headers } });
  const cacheControl = response.headers.get('Cache-Control')?.toLowerCase().split(',').map((value) => value.trim()) ?? [];
  if (!cacheControl.includes('private') || !cacheControl.includes('no-store')) {
    throw Object.assign(new Error('Personal memory cache policy was not verified'), { status: 502 });
  }
  if (!response.ok) throw Object.assign(new Error('Personal memory request failed'), { status: response.status });
  return response.json();
}

export async function fetchPersonalMemories(signal?: AbortSignal): Promise<PersonalMemory[]> {
  const body = await request('/api/personal-memory?limit=20', { signal });
  if (!body || typeof body !== 'object' || !Array.isArray((body as Record<string, unknown>).items)
    || ((body as { items: unknown[] }).items.length > 20)) {
    throw Object.assign(new Error('Invalid personal memory response'), { status: 502 });
  }
  const rows = ((body as { items: unknown[] }).items).map(parseMemory);
  if (rows.some((row) => !row)) throw Object.assign(new Error('Invalid personal memory item'), { status: 502 });
  return rows as PersonalMemory[];
}

export async function fetchPersonalMemoryHistory(memoryId: string, signal?: AbortSignal): Promise<PersonalMemory[]> {
  if (!SAFE_ID.test(memoryId)) throw Object.assign(new Error('Invalid memory identifier'), { status: 400 });
  const body = await request(`/api/personal-memory/${encodeURIComponent(memoryId)}/history`, { signal });
  if (!body || typeof body !== 'object' || (body as Record<string, unknown>).memory_id !== memoryId
    || !Array.isArray((body as Record<string, unknown>).revisions)
    || ((body as { revisions: unknown[] }).revisions.length > 1000)) {
    throw Object.assign(new Error('Invalid personal memory history'), { status: 502 });
  }
  const rows = ((body as { revisions: unknown[] }).revisions).map(parseMemory);
  if (rows.some((row) => !row)) throw Object.assign(new Error('Invalid personal memory history item'), { status: 502 });
  return rows as PersonalMemory[];
}

export type MemoryChange = {
  memory_id: string;
  expected_revision: number;
  idempotency_key: string;
  source_type: 'user_confirmed';
  source_ref: string;
};

export async function correctPersonalMemory(attempt: MemoryChange & { content: { text: string } }, signal?: AbortSignal): Promise<PersonalMemory> {
  return parseChangeResponse(await request(`/api/personal-memory/${encodeURIComponent(attempt.memory_id)}/correct`, {
    method: 'POST', signal, body: JSON.stringify({ expected_revision: attempt.expected_revision,
      idempotency_key: attempt.idempotency_key, content: attempt.content,
      source_type: attempt.source_type, source_ref: attempt.source_ref }),
  }), attempt);
}

export async function revokePersonalMemory(attempt: MemoryChange, signal?: AbortSignal): Promise<PersonalMemory> {
  return parseChangeResponse(await request(`/api/personal-memory/${encodeURIComponent(attempt.memory_id)}/revoke`, {
    method: 'POST', signal, body: JSON.stringify({ expected_revision: attempt.expected_revision,
      idempotency_key: attempt.idempotency_key, source_type: attempt.source_type, source_ref: attempt.source_ref }),
  }), attempt);
}

function parseChangeResponse(body: unknown, attempt: MemoryChange): PersonalMemory {
  const parsed = parseMemory(body);
  if (!parsed || parsed.memory_id !== attempt.memory_id || parsed.revision !== attempt.expected_revision + 1) {
    throw Object.assign(new Error('Memory change receipt did not match the requested revision'), { status: 502 });
  }
  return parsed;
}
