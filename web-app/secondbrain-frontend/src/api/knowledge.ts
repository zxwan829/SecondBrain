export type KnowledgeProvenanceStatus = 'verified' | 'missing' | 'unverified';

export type KnowledgeSearchItem = {
  id: string;
  title: string;
  snippet: string;
  match: 'title' | 'content';
  updated: string;
  sha256: string;
  provenance_status: KnowledgeProvenanceStatus;
};

export type KnowledgeSearchResult = {
  items: KnowledgeSearchItem[];
  status: 'ok' | 'truncated';
};

export type KnowledgeDetail = {
  id: string;
  content: string;
  sha256: string;
  updated: string;
  provenance_status: KnowledgeProvenanceStatus;
};

export type KnowledgeSource =
  | { status: 'available'; provenance_status: 'verified'; source: { kind: 'review'; ref: string; sha256: string; request_id: string } }
  | { status: 'missing'; provenance_status: 'missing'; source: null }
  | { status: 'unavailable'; provenance_status: 'unverified'; source: null };

export class KnowledgeApiError extends Error {
  constructor(readonly status: number) {
    super(`Knowledge request failed (${status})`);
    this.name = 'KnowledgeApiError';
  }
}

async function requestJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', signal });
  if (!response.ok) throw new KnowledgeApiError(response.status);
  try {
    return await response.json() as T;
  } catch {
    throw new KnowledgeApiError(502);
  }
}

function isProvenanceStatus(value: unknown): value is KnowledgeProvenanceStatus {
  return value === 'verified' || value === 'missing' || value === 'unverified';
}

function isSearchItem(value: unknown): value is KnowledgeSearchItem {
  if (!value || typeof value !== 'object') return false;
  const item = value as Record<string, unknown>;
  return typeof item.id === 'string' && typeof item.title === 'string'
    && typeof item.snippet === 'string' && (item.match === 'title' || item.match === 'content')
    && typeof item.updated === 'string' && typeof item.sha256 === 'string'
    && isProvenanceStatus(item.provenance_status);
}

function isSafeReviewRef(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= 512
    && !value.startsWith('/') && !/[\\\u0000-\u001f\u007f]/.test(value)
    && value.split('/').every((part) => part !== '' && part !== '.' && part !== '..');
}

function isKnowledgeSource(value: unknown): value is KnowledgeSource {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const result = value as Record<string, unknown>;
  const keys = Object.keys(result).sort();
  if (keys.join(',') !== 'provenance_status,source,status') return false;
  if (result.status === 'missing') return result.provenance_status === 'missing' && result.source === null;
  if (result.status === 'unavailable') return result.provenance_status === 'unverified' && result.source === null;
  if (result.status !== 'available' || result.provenance_status !== 'verified'
    || !result.source || typeof result.source !== 'object' || Array.isArray(result.source)) return false;
  const source = result.source as Record<string, unknown>;
  if (Object.keys(source).sort().join(',') !== 'kind,ref,request_id,sha256'
    || source.kind !== 'review' || !isSafeReviewRef(source.ref)
    || typeof source.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(source.sha256)
    || typeof source.request_id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(source.request_id)) return false;
  return true;
}

export const knowledgeApi = {
  async search(query: string, signal: AbortSignal): Promise<KnowledgeSearchResult> {
    const params = new URLSearchParams({ q: query, limit: '50' });
    const result = await requestJson<KnowledgeSearchResult>(`/api/knowledge/search?${params}`, signal);
    if (!result || !Array.isArray(result.items) || !result.items.every(isSearchItem)
      || (result.status !== 'ok' && result.status !== 'truncated')) {
      throw new KnowledgeApiError(502);
    }
    return result;
  },

  async detail(id: string, signal: AbortSignal): Promise<KnowledgeDetail> {
    const detail = await requestJson<KnowledgeDetail>(`/api/knowledge/items/${encodeURIComponent(id)}`, signal);
    if (!detail || detail.id !== id || typeof detail.content !== 'string'
      || typeof detail.sha256 !== 'string' || typeof detail.updated !== 'string'
      || !isProvenanceStatus(detail.provenance_status)) {
      throw new KnowledgeApiError(502);
    }
    return detail;
  },

  async source(id: string, signal: AbortSignal): Promise<KnowledgeSource> {
    const source = await requestJson<unknown>(`/api/knowledge/items/${encodeURIComponent(id)}/source`, signal);
    if (!isKnowledgeSource(source)) throw new KnowledgeApiError(502);
    return source;
  },
};
