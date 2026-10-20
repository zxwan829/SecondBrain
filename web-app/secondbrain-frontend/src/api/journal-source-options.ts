export type JournalSourceOptionsStatus = 'real' | 'empty' | 'unavailable';

export type JournalSourceOption = {
  kind: 'journal';
  id: string;
  date: string;
  version: string;
};

export type JournalSourceOptions = {
  status: JournalSourceOptionsStatus;
  items: JournalSourceOption[];
  freshness: { checked_at: string };
};

export type JournalSourceOptionsFailure = 'unauthorized' | 'invalid-request' | 'unavailable';

export class JournalSourceOptionsError extends Error {
  constructor(readonly reason: JournalSourceOptionsFailure) {
    super(reason);
    this.name = 'JournalSourceOptionsError';
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));
}

function isCanonicalDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00.000Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function isUtcTimestamp(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value)) return false;
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 19) === value.slice(0, 19);
}

export function parseJournalSourceOptions(value: unknown, requestedDate: string): JournalSourceOptions | null {
  if (!isCanonicalDate(requestedDate) || !isRecord(value)
    || !hasExactKeys(value, ['status', 'items', 'freshness'])
    || !['real', 'empty', 'unavailable'].includes(String(value.status))
    || !Array.isArray(value.items) || value.items.length > 20
    || !isRecord(value.freshness) || !hasExactKeys(value.freshness, ['checked_at'])
    || !isUtcTimestamp(value.freshness.checked_at)) return null;

  const status = value.status as JournalSourceOptionsStatus;
  if ((status === 'real' && value.items.length === 0)
    || (status !== 'real' && value.items.length !== 0)) return null;

  const items: JournalSourceOption[] = [];
  let previousRowId = '';
  for (const raw of value.items) {
    if (!isRecord(raw) || !hasExactKeys(raw, ['kind', 'id', 'date', 'version'])
      || raw.kind !== 'journal' || raw.date !== requestedDate
      || typeof raw.id !== 'string' || typeof raw.version !== 'string'
      || !new RegExp(`^${requestedDate}:[a-f0-9]{64}$`).test(raw.id)
      || !/^[a-f0-9]{64}$/.test(raw.version)) return null;
    const rowId = raw.id.slice(requestedDate.length + 1);
    if (rowId <= previousRowId) return null;
    previousRowId = rowId;
    items.push({ kind: 'journal', id: raw.id, date: raw.date, version: raw.version });
  }

  return {
    status,
    items,
    freshness: { checked_at: value.freshness.checked_at },
  };
}

export const journalSourceOptionsApi = {
  async list(date: string, signal: AbortSignal): Promise<JournalSourceOptions> {
    if (!isCanonicalDate(date)) throw new JournalSourceOptionsError('invalid-request');
    const query = new URLSearchParams({ date });
    const response = await fetch(`/api/daily-brief/source-options/journal?${query}`, {
      credentials: 'same-origin',
      cache: 'no-store',
      signal,
      headers: { Accept: 'application/json' },
    });
    if (response.status === 401 || response.status === 403) {
      throw new JournalSourceOptionsError('unauthorized');
    }
    if (response.status === 400 || response.status === 422) {
      throw new JournalSourceOptionsError('invalid-request');
    }
    if (!response.ok) throw new JournalSourceOptionsError('unavailable');
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      throw new JournalSourceOptionsError('unavailable');
    }
    const parsed = parseJournalSourceOptions(payload, date);
    if (!parsed) throw new JournalSourceOptionsError('unavailable');
    return parsed;
  },
};
