export type CitationStatus = 'available' | 'none' | 'partial' | 'unavailable';
export type CitationKnowledgeStatus = 'version_verified' | 'stale' | 'unavailable';

export type KnowledgeCitation = {
  citation_id: string;
  title: string;
  sha256: string;
  knowledge_status: CitationKnowledgeStatus;
  provenance_status: 'verified';
};

export type KnowledgeCitationBundle = {
  version: 1;
  run_id: string;
  session_id: string;
  status: CitationStatus;
  citations: KnowledgeCitation[];
  error_status?: number;
};

export type CitationRunLocator = { session_id: string; run_id: string };

const LOCATOR_KEY = 'secondbrain.chat.knowledgeCitationRuns';
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$/;
const OPAQUE_ID = /^[A-Za-z0-9._~-]{16,256}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const STATUSES = new Set<CitationStatus>(['available', 'none', 'partial', 'unavailable']);
const KNOWLEDGE_STATUSES = new Set<CitationKnowledgeStatus>(['version_verified', 'stale', 'unavailable']);

function exactKeys(value: Record<string, unknown>, expected: string[]): boolean {
  const keys = Object.keys(value).sort();
  return keys.length === expected.length && keys.every((key, index) => key === [...expected].sort()[index]);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function parseCitation(value: unknown): KnowledgeCitation | null {
  if (!isRecord(value) || !exactKeys(value, ['citation_id', 'title', 'sha256', 'knowledge_status', 'provenance_status'])) return null;
  if (typeof value.citation_id !== 'string' || !OPAQUE_ID.test(value.citation_id)
    || typeof value.title !== 'string' || !value.title.trim() || value.title.length > 240
    || /[\u0000-\u001f\u007f]/.test(value.title)
    || typeof value.sha256 !== 'string' || !SHA256.test(value.sha256)
    || typeof value.knowledge_status !== 'string' || !KNOWLEDGE_STATUSES.has(value.knowledge_status as CitationKnowledgeStatus)
    || value.provenance_status !== 'verified') return null;
  return {
    citation_id: value.citation_id,
    title: value.title.trim(),
    sha256: value.sha256,
    knowledge_status: value.knowledge_status as CitationKnowledgeStatus,
    provenance_status: 'verified',
  };
}

/** Strictly parses the frozen Core projection. No client/model fields are accepted. */
export function parseKnowledgeCitationBundle(value: unknown, expected: CitationRunLocator): KnowledgeCitationBundle | null {
  if (!isRecord(value) || !exactKeys(value, ['event', 'version', 'run_id', 'session_id', 'status', 'citations'])) return null;
  if (value.event !== 'knowledge.citations' || value.version !== 1
    || value.run_id !== expected.run_id || value.session_id !== expected.session_id
    || typeof value.status !== 'string' || !STATUSES.has(value.status as CitationStatus)
    || !Array.isArray(value.citations) || value.citations.length > 3) return null;
  const citations: KnowledgeCitation[] = [];
  const seen = new Set<string>();
  for (const row of value.citations) {
    const citation = parseCitation(row);
    if (!citation) return null;
    if (!seen.has(citation.citation_id)) {
      citations.push(citation);
      seen.add(citation.citation_id);
    }
  }
  const status = value.status as CitationStatus;
  if ((status === 'none' && citations.length !== 0)
    || (status === 'available' && (citations.length === 0
      || citations.some((citation) => citation.knowledge_status !== 'version_verified')))) return null;
  return { version: 1, run_id: expected.run_id, session_id: expected.session_id, status, citations };
}

/** Read locator IDs only; citation content and status always come from Core history. */
export function readCitationRunLocators(sessionId: string): CitationRunLocator[] {
  if (!SAFE_ID.test(sessionId)) return [];
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(LOCATOR_KEY) ?? '[]');
    if (!Array.isArray(parsed)) return [];
    const seen = new Set<string>();
    const rows: CitationRunLocator[] = [];
    for (const row of parsed) {
      if (!isRecord(row) || !exactKeys(row, ['session_id', 'run_id'])
        || row.session_id !== sessionId || typeof row.run_id !== 'string' || !SAFE_ID.test(row.run_id)) continue;
      if (seen.has(row.run_id)) continue;
      seen.add(row.run_id);
      rows.push({ session_id: sessionId, run_id: row.run_id });
    }
    return rows.slice(-50);
  } catch {
    return [];
  }
}

export function rememberCitationRun(locator: CitationRunLocator): boolean {
  if (!SAFE_ID.test(locator.session_id) || !SAFE_ID.test(locator.run_id)) return false;
  try {
    let parsed: unknown = [];
    try { parsed = JSON.parse(localStorage.getItem(LOCATOR_KEY) ?? '[]'); } catch { parsed = []; }
    const rows = Array.isArray(parsed) ? parsed.filter((row): row is CitationRunLocator =>
      isRecord(row) && typeof row.session_id === 'string' && SAFE_ID.test(row.session_id)
      && typeof row.run_id === 'string' && SAFE_ID.test(row.run_id)) : [];
    const deduped = rows.filter((row) => !(row.session_id === locator.session_id && row.run_id === locator.run_id));
    deduped.push(locator);
    localStorage.setItem(LOCATOR_KEY, JSON.stringify(deduped.slice(-200)));
    return true;
  } catch {
    return false;
  }
}

export function citationErrorBundle(locator: CitationRunLocator, status: number): KnowledgeCitationBundle {
  return { version: 1, run_id: locator.run_id, session_id: locator.session_id,
    status: status === 404 || status === 409 ? 'partial' : 'unavailable', citations: [], error_status: status };
}
