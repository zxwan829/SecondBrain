import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  JournalSourceOptionsError,
  journalSourceOptionsApi,
  parseJournalSourceOptions,
} from './journal-source-options';

const date = '2026-10-20';
const version = 'f'.repeat(64);
const firstId = `${date}:${'a'.repeat(64)}`;
const secondId = `${date}:${'b'.repeat(64)}`;
const freshness = { checked_at: '2026-10-20T01:30:00Z' };

function payload(status: 'real' | 'empty' | 'unavailable' = 'real') {
  return {
    status,
    items: status === 'real' ? [
      { kind: 'journal', id: firstId, date, version },
      { kind: 'journal', id: secondId, date, version },
    ] : [],
    freshness,
  };
}

describe('Journal source options contract', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('accepts the exact frozen metadata response and preserves sorted IDs', () => {
    expect(parseJournalSourceOptions(payload(), date)?.items.map((item) => item.id)).toEqual([firstId, secondId]);
    expect(parseJournalSourceOptions(payload('empty'), date)?.status).toBe('empty');
    expect(parseJournalSourceOptions(payload('unavailable'), date)?.items).toEqual([]);
  });

  it.each([
    ['extra top-level key', { ...payload(), summary: 'must not be accepted' }],
    ['missing freshness', { status: 'empty', items: [] }],
    ['wrong item date', { ...payload(), items: [{ kind: 'journal', id: firstId, date: '2026-10-19', version }] }],
    ['uppercase row ID', { ...payload(), items: [{ kind: 'journal', id: `${date}:${'A'.repeat(64)}`, date, version }] }],
    ['uppercase version', { ...payload(), items: [{ kind: 'journal', id: firstId, date, version: 'A'.repeat(64) }] }],
    ['duplicate ID', { ...payload(), items: [{ kind: 'journal', id: firstId, date, version }, { kind: 'journal', id: firstId, date, version }] }],
    ['descending IDs', { ...payload(), items: [...payload().items].reverse() }],
    ['real without items', { ...payload(), items: [] }],
    ['unavailable with partial items', { ...payload('unavailable'), items: [{ kind: 'journal', id: firstId, date, version }] }],
    ['noncanonical freshness', { ...payload(), freshness: { checked_at: '2026-10-20T01:30:00+00:00' } }],
    ['invalid requested date', payload()],
  ])('fails closed for %s', (_name, response) => {
    const requestedDate = _name === 'invalid requested date' ? '2026-02-30' : date;
    expect(parseJournalSourceOptions(response, requestedDate)).toBeNull();
  });

  it('uses only the explicit metadata GET with same-origin credentials and no cache', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => Response.json(payload()));
    vi.stubGlobal('fetch', fetchMock);
    const controller = new AbortController();
    await journalSourceOptionsApi.list(date, controller.signal);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/daily-brief/source-options/journal?date=${date}`);
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ credentials: 'same-origin', cache: 'no-store', signal: controller.signal });
  });

  it('does not make a request for a noncanonical date', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    await expect(journalSourceOptionsApi.list('2026-02-30', new AbortController().signal))
      .rejects.toMatchObject({ reason: 'invalid-request' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    [401, 'unauthorized'], [403, 'unauthorized'], [400, 'invalid-request'],
    [422, 'invalid-request'], [503, 'unavailable'],
  ] as const)('maps HTTP %i to a safe error category', async (status, reason) => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('private error detail', { status })));
    await expect(journalSourceOptionsApi.list(date, new AbortController().signal))
      .rejects.toBeInstanceOf(JournalSourceOptionsError);
    await expect(journalSourceOptionsApi.list(date, new AbortController().signal))
      .rejects.toMatchObject({ reason });
  });

  it('rejects malformed successful JSON as unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{not-json', { status: 200 })));
    await expect(journalSourceOptionsApi.list(date, new AbortController().signal))
      .rejects.toMatchObject({ reason: 'unavailable' });
  });
});
