import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchContextPreview, parseContextPreview } from './chat-context-preview';

afterEach(() => vi.unstubAllGlobals());

const item = {
  source_kind: 'personal_memory', source_id: 'opaque-memory-id-123', source_version: 'revision-7', sha256: 'a'.repeat(64),
  source_timestamp: '2026-10-22T08:00:00Z', fact_kind: 'preference', verification_status: 'user_confirmed',
  state: 'active', expires_at: null,
};
const preview = (overrides: Record<string, unknown> = {}) => ({
  schema_version: 'context.v1', request_id: 'request-123', session_id: 'session-a', evaluated_at: '2026-10-22T08:01:00Z',
  status: 'available', source_status: { personal_memory: 'available', knowledge: 'none' }, items: [item], ...overrides,
});

describe('Context v1 preview contract', () => {
  it('accepts exact metadata-only schema bound to the requested session', () => {
    expect(parseContextPreview(preview(), 'session-a')?.items).toEqual([item]);
  });

  it.each([
    preview({ session_id: 'session-b' }),
    preview({ extra: 'body must not be accepted' }),
    preview({ items: [{ ...item, content: 'private source body' }] }),
    preview({ items: [{ ...item, source_id: '/private/path' }] }),
    preview({ items: Array.from({ length: 4 }, (_, index) => ({ ...item, source_id: `opaque-memory-${index}` })) }),
    preview({ items: Array.from({ length: 6 }, (_, index) => ({ ...item, source_kind: index < 4 ? 'personal_memory' : 'knowledge', source_id: `opaque-${index}` })) }),
    preview({ status: 'none' }),
    preview({ items: [{ ...item, source_version: 'x'.repeat(9000) }] }),
  ])('rejects malformed, unsafe, over-budget, or inconsistent response %#', (value) => {
    expect(parseContextPreview(value, 'session-a')).toBeNull();
  });

  it('sends only a trimmed query with no-store and same-origin credentials', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(preview()), {
      status: 200, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'private, no-store' },
    }));
    vi.stubGlobal('fetch', fetchMock);
    const result = await fetchContextPreview('session-a', '  synthetic question  ', new AbortController().signal);
    expect(result.session_id).toBe('session-a');
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/chat/sessions/session-a/context-preview');
    expect(init.method).toBe('POST');
    expect(init.cache).toBe('no-store');
    expect(init.credentials).toBe('same-origin');
    expect(JSON.parse(String(init.body))).toEqual({ query: 'synthetic question' });
    expect(Object.keys(JSON.parse(String(init.body)))).toEqual(['query']);
  });

  it('rejects empty and overlength requests before network access', async () => {
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    await expect(fetchContextPreview('session-a', '  ', new AbortController().signal)).rejects.toMatchObject({ status: 400 });
    await expect(fetchContextPreview('session-a', '😀'.repeat(201), new AbortController().signal)).rejects.toMatchObject({ status: 400 });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('fails closed when the Core response omits private no-store', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(preview()), { status: 200 })));
    await expect(fetchContextPreview('session-a', 'synthetic', new AbortController().signal)).rejects.toMatchObject({ status: 502 });
  });
});
