export type VocabularyTerm = { id: string; name: string; enabled: boolean; built_in?: boolean };
export type VocabularySynonym = { id: string; alias: string; tag_id: string; enabled: boolean };
export type VocabularyAudit = { revision: number; operation: string; actor: string; target: Record<string, unknown>; at: string };
export type VocabularySnapshot = {
  schema_version: number;
  revision: number;
  types: VocabularyTerm[];
  tags: VocabularyTerm[];
  synonyms: VocabularySynonym[];
  audit: VocabularyAudit[];
};

async function request(url: string, init?: RequestInit): Promise<VocabularySnapshot> {
  const response = await fetch(url, { credentials: 'same-origin', ...init });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(typeof payload.detail === 'string' ? payload.detail : `HTTP ${response.status}`) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return payload as VocabularySnapshot;
}

export const vocabularyApi = {
  read: () => request('/api/vocabulary'),
  addType: (snapshot: VocabularySnapshot, name: string) => request('/api/vocabulary/types', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'If-Match': `"${snapshot.revision}"` },
    body: JSON.stringify({ name, confirmed: true }),
  }),
  setTypeEnabled: (snapshot: VocabularySnapshot, id: string, enabled: boolean) => request(`/api/vocabulary/types/${encodeURIComponent(id)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json', 'If-Match': `"${snapshot.revision}"` },
    body: JSON.stringify({ enabled, confirmed: true }),
  }),
  addTag: (snapshot: VocabularySnapshot, name: string) => request('/api/vocabulary/tags', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'If-Match': `"${snapshot.revision}"` },
    body: JSON.stringify({ name, confirmed: true }),
  }),
  setTagEnabled: (snapshot: VocabularySnapshot, id: string, enabled: boolean) => request(`/api/vocabulary/tags/${encodeURIComponent(id)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json', 'If-Match': `"${snapshot.revision}"` },
    body: JSON.stringify({ enabled, confirmed: true }),
  }),
  addSynonym: (snapshot: VocabularySnapshot, alias: string, tagId: string) => request('/api/vocabulary/synonyms', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'If-Match': `"${snapshot.revision}"` },
    body: JSON.stringify({ alias, tag_id: tagId, confirmed: true }),
  }),
};
