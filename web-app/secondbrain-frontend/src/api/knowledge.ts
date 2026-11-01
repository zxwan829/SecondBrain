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

export type KnowledgeFolder = { name: string; path: string };
export type KnowledgeFoldersResult = {
  status: 'ok' | 'partial'; path: string; folders: KnowledgeFolder[];
  scan: { entries: number; complete: boolean };
};
export type KnowledgeBrowseItem = {
  id: string; path: string; title: string; updated: string; tags: string[];
  metadata_status: 'ok' | 'unsupported';
};
export type KnowledgeTagFacet = { name: string; count: number; count_complete: boolean };
export type KnowledgeBrowseResult = {
  status: 'ok' | 'partial'; path: string; tag_facets: KnowledgeTagFacet[];
  items: KnowledgeBrowseItem[]; total: number; total_complete: boolean;
  offset: number; limit: number; next_offset: number | null;
  scan: { entries: number; complete: boolean };
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

function isNonNegativeInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && Number(value) >= 0;
}

function isSafeRelativePath(value: string): boolean {
  return value.length > 0 && value.length <= 4096 && !value.startsWith('/')
    && !/[\\\u0000-\u001f\u007f]/.test(value)
    && !/%(?:2e|2f|5c|25(?:2e|2f|5c))/i.test(value)
    && value.split('/').every((part) => part !== '' && part !== '.' && part !== '..' && part.length <= 255);
}

function isFoldersResult(value: unknown): value is KnowledgeFoldersResult {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const result = value as Record<string, unknown>;
  if ((result.status !== 'ok' && result.status !== 'partial') || typeof result.path !== 'string'
    || !Array.isArray(result.folders) || !result.folders.every((folder) => {
      if (!folder || typeof folder !== 'object' || Array.isArray(folder)) return false;
      const item = folder as Record<string, unknown>;
      return typeof item.name === 'string' && isSafeRelativePath(item.name)
        && !item.name.includes('/') && typeof item.path === 'string' && isSafeRelativePath(item.path)
        && item.path === (result.path ? `${result.path}/${item.name}` : item.name);
    }) || !result.scan || typeof result.scan !== 'object') return false;
  const scan = result.scan as Record<string, unknown>;
  return isNonNegativeInteger(scan.entries) && typeof scan.complete === 'boolean'
    && (result.status === 'partial' || scan.complete);
}

function isBrowseResult(value: unknown): value is KnowledgeBrowseResult {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const result = value as Record<string, unknown>;
  if ((result.status !== 'ok' && result.status !== 'partial') || typeof result.path !== 'string'
    || !Array.isArray(result.items) || !result.items.every((row) => {
      if (!row || typeof row !== 'object' || Array.isArray(row)) return false;
      const item = row as Record<string, unknown>;
      return typeof item.id === 'string' && typeof item.path === 'string' && isSafeRelativePath(item.path)
        && (result.path === '' || item.path === result.path || item.path.startsWith(`${result.path}/`))
        && item.path.toLowerCase().endsWith('.md') && typeof item.title === 'string'
        && typeof item.updated === 'string' && Array.isArray(item.tags)
        && item.tags.every((tag) => typeof tag === 'string')
        && (item.metadata_status === 'ok' || item.metadata_status === 'unsupported')
        && (item.metadata_status !== 'unsupported' || item.tags.length === 0);
    }) || !Array.isArray(result.tag_facets) || !result.tag_facets.every((facet) => {
      if (!facet || typeof facet !== 'object' || Array.isArray(facet)) return false;
      const item = facet as Record<string, unknown>;
      return typeof item.name === 'string' && isNonNegativeInteger(item.count)
        && typeof item.count_complete === 'boolean';
    }) || !isNonNegativeInteger(result.total) || typeof result.total_complete !== 'boolean'
    || !isNonNegativeInteger(result.offset) || !isNonNegativeInteger(result.limit)
    || !(result.next_offset === null || isNonNegativeInteger(result.next_offset))
    || !result.scan || typeof result.scan !== 'object') return false;
  const scan = result.scan as Record<string, unknown>;
  return isNonNegativeInteger(scan.entries) && typeof scan.complete === 'boolean'
    && (result.status === 'partial' || (scan.complete && result.total_complete
      && (result.tag_facets as KnowledgeTagFacet[]).every((facet) => facet.count_complete)));
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
  async folders(path: string, signal: AbortSignal): Promise<KnowledgeFoldersResult> {
    const params = new URLSearchParams({ path });
    const result = await requestJson<unknown>(`/api/knowledge/folders?${params}`, signal);
    if (!isFoldersResult(result) || result.path !== path) throw new KnowledgeApiError(502);
    return result;
  },

  async browse(path: string, tags: string[], match: 'and' | 'or', offset: number, signal: AbortSignal): Promise<KnowledgeBrowseResult> {
    const params = new URLSearchParams({ path, match, offset: String(offset), limit: '20' });
    tags.forEach((tag) => params.append('tag', tag));
    const result = await requestJson<unknown>(`/api/knowledge/browse?${params}`, signal);
    if (!isBrowseResult(result) || result.path !== path || result.offset !== offset || result.limit !== 20) {
      throw new KnowledgeApiError(502);
    }
    return result;
  },

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
