import { afterEach, describe, expect, it, vi } from 'vitest';
import { correctPersonalMemory, fetchPersonalMemories, revokePersonalMemory } from './personal-memory';

afterEach(() => vi.unstubAllGlobals());

const row = { memory_id: 'memory-synthetic-1', revision: 1, content: { text: 'synthetic preference' },
  category: 'preference', fact_kind: 'user_stated', status: 'active', recorded_at: '2026-10-22T00:00:00Z',
  source: { type: 'user_message', ref: 'synthetic-session/message-1' } };
const response = (body: unknown, status = 200, headers: Record<string, string> = { 'Cache-Control': 'private, no-store' }) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });

describe('Personal Memory lifecycle client', () => {
  it('loads only a bounded authorized list with no-store', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ items: [row] })); vi.stubGlobal('fetch', fetchMock);
    await expect(fetchPersonalMemories()).resolves.toEqual([row]);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/personal-memory?limit=20');
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ cache: 'no-store', credentials: 'same-origin' });
  });

  it('fails closed when cache policy or record shape is invalid', async () => {
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ items: [row] }, 200, {})));
    await expect(fetchPersonalMemories()).rejects.toMatchObject({ status: 502 });
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ items: [{ ...row, memory_id: '../private' }] })));
    await expect(fetchPersonalMemories()).rejects.toMatchObject({ status: 502 });
  });

  it('sends correction revision and key exactly, then verifies next revision receipt', async () => {
    const next = { ...row, revision: 2, content: { text: 'corrected preference' } };
    let calls = 0;
    const fetchMock = vi.fn(async (_url: string | URL | Request, _init?: RequestInit) => {
      calls += 1;
      return response(calls > 1 ? { ...next, revision: 3 } : next, 200);
    });
    vi.stubGlobal('fetch', fetchMock);
    const attempt = { memory_id: row.memory_id, expected_revision: 1, idempotency_key: 'key-synthetic-1',
      source_type: 'user_confirmed' as const, source_ref: 'web-personal-memory-confirmation/key-synthetic-1',
      content: { text: 'corrected preference' } };
    await expect(correctPersonalMemory(attempt)).resolves.toMatchObject({ revision: 2 });
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      expected_revision: 1, idempotency_key: attempt.idempotency_key, content: attempt.content,
      source_type: attempt.source_type, source_ref: attempt.source_ref,
    });
    await expect(correctPersonalMemory({ ...attempt, idempotency_key: 'key-synthetic-2' })).rejects.toMatchObject({ status: 502 });
  });

  it('sends revoke with explicit source and idempotency metadata', async () => {
    const next = { ...row, revision: 2, status: 'revoked' };
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response(next)); vi.stubGlobal('fetch', fetchMock);
    await revokePersonalMemory({ memory_id: row.memory_id, expected_revision: 1, idempotency_key: 'key-synthetic-revoke',
      source_type: 'user_confirmed', source_ref: 'web-personal-memory-confirmation/key-synthetic-revoke' });
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/personal-memory/${row.memory_id}/revoke`);
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toMatchObject({ expected_revision: 1,
      idempotency_key: 'key-synthetic-revoke', source_type: 'user_confirmed' });
  });
});
