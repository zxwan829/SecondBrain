import { afterEach, describe, expect, it } from 'vitest';
import { parseKnowledgeCitationBundle, readCitationRunLocators, rememberCitationRun } from './chat-knowledge-citations';

afterEach(() => localStorage.clear());

const locator = { session_id: 'session-a', run_id: 'run-a' };
const citation = { citation_id: 'opaqueCitationId_123456', title: '合成参考', sha256: 'a'.repeat(64),
  knowledge_status: 'version_verified', provenance_status: 'verified' };
const bundle = (overrides: Record<string, unknown> = {}) => ({ event: 'knowledge.citations', version: 1,
  ...locator, status: 'available', citations: [citation], ...overrides });

describe('Chat Knowledge citation contract', () => {
  it('accepts the exact Core event and de-duplicates citation IDs', () => {
    const parsed = parseKnowledgeCitationBundle(bundle({ citations: [citation, citation] }), locator);
    expect(parsed?.citations).toHaveLength(1);
    expect(parsed?.status).toBe('available');
  });

  it.each(['none', 'partial', 'unavailable'])('accepts the frozen status %s', (status) => {
    const citations = status === 'none' ? [] : [citation];
    expect(parseKnowledgeCitationBundle(bundle({ status, citations }), locator)?.status).toBe(status);
  });

  it.each([
    bundle({ session_id: 'session-other' }),
    bundle({ run_id: 'run-other' }),
    bundle({ citations: [{ ...citation, url: 'https://untrusted.invalid' }] }),
    bundle({ citations: [{ ...citation, knowledge_status: 'promoted' }] }),
    bundle({ citations: [{ ...citation, provenance_status: 'missing' }] }),
    bundle({ citations: [{ ...citation, title: 'bad\npath' }] }),
    bundle({ citations: [{ ...citation, citation_id: '/private/path' }] }),
    bundle({ status: 'none', citations: [citation] }),
    bundle({ status: 'available', citations: [{ ...citation, knowledge_status: 'stale' }] }),
    bundle({ extra: 'client field' }),
  ])('fails closed on invalid or cross-bound payload %#', (payload) => {
    expect(parseKnowledgeCitationBundle(payload, locator)).toBeNull();
  });

  it('retains only opaque run locators and de-duplicates them across sessions', () => {
    expect(rememberCitationRun(locator)).toBe(true);
    expect(rememberCitationRun(locator)).toBe(true);
    expect(rememberCitationRun({ session_id: 'session-b', run_id: 'run-b' })).toBe(true);
    expect(readCitationRunLocators('session-a')).toEqual([locator]);
    expect(readCitationRunLocators('session-other')).toEqual([]);
  });

  it('rejects malformed locator storage without exposing it', () => {
    localStorage.setItem('secondbrain.chat.knowledgeCitationRuns', '{');
    expect(readCitationRunLocators('session-a')).toEqual([]);
  });
});
