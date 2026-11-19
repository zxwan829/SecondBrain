export type GroundingCandidate = {
  citation_id: string; title: string; sha256: string;
  knowledge_status: 'version_verified'; provenance_status: 'verified';
};
export type GroundingCandidates = {
  event: 'knowledge.grounding-candidates'; version: 1; session_id: string;
  status: 'available' | 'none' | 'partial' | 'unavailable' | 'needs_review';
  answer_attribution: 'not_established'; items: GroundingCandidate[];
};

const SESSION = /^[A-Za-z0-9_.:-]{1,256}$/;
const ID = /^[A-Za-z0-9_-]{12,64}$/;
const SHA = /^[a-f0-9]{64}$/;
const STATUSES = new Set(['available', 'none', 'partial', 'unavailable', 'needs_review']);
function record(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

export function parseGroundingCandidates(value: unknown, expectedSessionId: string): GroundingCandidates | null {
  if (!SESSION.test(expectedSessionId) || !record(value)
    || Object.keys(value).sort().join(',') !== 'answer_attribution,event,items,session_id,status,version'
    || value.event !== 'knowledge.grounding-candidates' || value.version !== 1
    || value.session_id !== expectedSessionId || typeof value.status !== 'string' || !STATUSES.has(value.status)
    || value.answer_attribution !== 'not_established' || !Array.isArray(value.items) || value.items.length > 3) return null;
  const seen = new Set<string>();
  for (const item of value.items) {
    if (!record(item) || Object.keys(item).sort().join(',') !== 'citation_id,knowledge_status,provenance_status,sha256,title'
      || typeof item.citation_id !== 'string' || !ID.test(item.citation_id) || seen.has(item.citation_id)
      || typeof item.title !== 'string' || !item.title.trim() || item.title.length > 200
      || typeof item.sha256 !== 'string' || !SHA.test(item.sha256)
      || item.knowledge_status !== 'version_verified' || item.provenance_status !== 'verified') return null;
    seen.add(item.citation_id);
  }
  if ((value.status === 'none' && value.items.length !== 0)
    || (value.status === 'available' && value.items.length !== 1)
    || (value.status === 'needs_review' && value.items.length < 2)
    || (value.status === 'unavailable' && value.items.length !== 0)) return null;
  if (new TextEncoder().encode(JSON.stringify(value)).byteLength > 8 * 1024) return null;
  return value as GroundingCandidates;
}

export async function fetchGroundingCandidates(sessionId: string, query: string, signal: AbortSignal): Promise<GroundingCandidates> {
  const normalized = query.trim();
  if (!SESSION.test(sessionId) || !normalized || [...normalized].length > 2000) {
    throw Object.assign(new Error('Invalid grounding-candidates request'), { status: 400 });
  }
  const response = await fetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}/grounding-candidates`, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store', signal,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ query: normalized }),
  });
  const directives = response.headers.get('Cache-Control')?.toLowerCase().split(',').map((part) => part.trim()) ?? [];
  if (!directives.includes('private') || !directives.includes('no-store')) {
    throw Object.assign(new Error('Grounding-candidates cache policy was not verified'), { status: 502 });
  }
  if (!response.ok) throw Object.assign(new Error('Grounding candidates are unavailable'), { status: response.status });
  const payload: unknown = await response.json();
  const parsed = parseGroundingCandidates(payload, sessionId);
  if (!parsed) throw Object.assign(new Error('Invalid grounding-candidates response'), { status: 502 });
  return parsed;
}
