import { describe, expect, it, vi } from 'vitest';
import { fetchGroundingCandidates, parseGroundingCandidates } from './chat-grounding-candidates';

const valid = {
  event: 'knowledge.grounding-candidates', version: 1, session_id: 'session-A', status: 'available',
  answer_attribution: 'not_established', items: [{ citation_id: 'AbcdefghijklmnopQRST', title: 'Synthetic source',
    sha256: 'a'.repeat(64), knowledge_status: 'version_verified', provenance_status: 'verified' }],
};

describe('grounding candidates contract', () => {
  it('accepts the exact metadata-only event and rejects drift, unknown fields, and text leaks', () => {
    expect(parseGroundingCandidates(valid, 'session-A')).toEqual(valid);
    expect(parseGroundingCandidates({ ...valid, session_id: 'session-B' }, 'session-A')).toBeNull();
    expect(parseGroundingCandidates({ ...valid, excerpt: 'private text' }, 'session-A')).toBeNull();
    expect(parseGroundingCandidates({ ...valid, items: [{ ...valid.items[0], relative_path: 'secret.md' }] }, 'session-A')).toBeNull();
    expect(parseGroundingCandidates({ ...valid, answer_attribution: 'grounded' }, 'session-A')).toBeNull();
  });

  it('posts only a query with no-store and requires the response cache policy', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(valid), {
      status: 200, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'private, no-store' },
    }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(fetchGroundingCandidates('session-A', 'synthetic query', new AbortController().signal)).resolves.toEqual(valid);
    expect(fetchMock).toHaveBeenCalledWith('/api/chat/sessions/session-A/grounding-candidates', expect.objectContaining({
      method: 'POST', cache: 'no-store', body: JSON.stringify({ query: 'synthetic query' }),
    }));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(valid), { status: 200 })));
    await expect(fetchGroundingCandidates('session-A', 'synthetic query', new AbortController().signal)).rejects.toMatchObject({ status: 502 });
    vi.unstubAllGlobals();
  });
});
