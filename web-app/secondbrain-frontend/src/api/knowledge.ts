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
};
