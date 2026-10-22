import type { Home } from './home';

export type DataKind = 'REAL' | 'DEMO' | 'UNAVAILABLE';
export type ListItem = { title: string; status?: string; updated?: number | string };
export type TodayState =
  | { kind: 'content'; items: ListItem[]; source: 'REAL' }
  | { kind: 'empty'; source: 'REAL' }
  | { kind: 'unknown'; source: 'UNAVAILABLE' };
export type HomeView = {
  pendingCount: number | null;
  review: ListItem[];
  reviewSource: DataKind;
  projectItems: ListItem[];
  projectSource: DataKind;
  knowledgeItems: ListItem[];
  knowledgeSource: DataKind;
  agentStatus: string | null;
  agentSource: DataKind;
  today: TodayState;
  source: DataKind;
};

const record = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};

function listItems(value: unknown): ListItem[] {
  const list = Array.isArray(value) ? value : record(value).items;
  if (!Array.isArray(list)) return [];
  return list.flatMap((candidate) => {
    if (typeof candidate === 'string' && candidate.trim()) return [{ title: candidate.trim() }];
    const item = record(candidate);
    if (typeof item.title !== 'string' || !item.title.trim()) return [];
    return [{
      title: item.title.trim(),
      status: typeof item.status === 'string' ? item.status : undefined,
      updated: typeof item.updated === 'number' || typeof item.updated === 'string' ? item.updated : undefined,
    }];
  });
}

function todayState(value: unknown): TodayState {
  if (value === null || value === undefined) return { kind: 'unknown', source: 'UNAVAILABLE' };
  const section = record(value);
  const items = listItems(value);
  const status = typeof section.status === 'string' ? section.status.toLowerCase() : '';
  if (status !== 'real' && status !== 'empty') return { kind: 'unknown', source: 'UNAVAILABLE' };
  if (items.length) return { kind: 'content', items, source: 'REAL' };
  if (status === 'empty' && Array.isArray(section.items) && section.items.length === 0) {
    return { kind: 'empty', source: 'REAL' };
  }
  if (typeof section.title === 'string' || typeof section.content === 'string' || typeof section.summary === 'string') {
    const title = String(section.title ?? section.content ?? section.summary).trim();
    if (title) return { kind: 'content', items: [{ title }], source: 'REAL' };
  }
  return { kind: 'unknown', source: 'UNAVAILABLE' };
}

export function adaptHome(home: Home | null): HomeView {
  if (!home) return {
    pendingCount: null,
    review: [],
    reviewSource: 'UNAVAILABLE',
    projectItems: [],
    projectSource: 'UNAVAILABLE',
    knowledgeItems: [],
    knowledgeSource: 'UNAVAILABLE',
    agentStatus: null,
    agentSource: 'UNAVAILABLE',
    today: { kind: 'unknown', source: 'UNAVAILABLE' },
    source: 'UNAVAILABLE',
  };

  const sections = record(home);
  const reviewSection = record(sections.review);
  const rawReview = reviewSection.items;
  const review = listItems(rawReview);
  const pending = reviewSection.pending_count;
  const reviewStatus = typeof reviewSection.status === 'string' ? reviewSection.status.toLowerCase() : '';
  const reviewSource: DataKind =
    (reviewStatus === 'real' || reviewStatus === 'empty') && Array.isArray(rawReview) &&
    typeof pending === 'number' && Number.isFinite(pending) && pending === review.length
      ? 'REAL'
      : 'UNAVAILABLE';

  const projectSection = record(sections.projects);
  const projectItems = listItems(projectSection);
  // The current API exposes files recursively found under 30-Projects. It does
  // not identify business-project records, so those filenames are not rendered
  // as a project list until the API supplies an explicit business-project schema.
  const hasBusinessProjectSchema = projectSection.source_type === 'business-projects' || projectSection.kind === 'business-projects';
  const verifiedProjectItems = hasBusinessProjectSchema ? projectItems : [];

  const knowledgeSection = record(sections.knowledge);
  const knowledgeItems = listItems(knowledgeSection);
  const knowledgeStatus = typeof knowledgeSection.status === 'string' ? knowledgeSection.status.toLowerCase() : '';
  const knowledgeSource: DataKind =
    (knowledgeStatus === 'real' || knowledgeStatus === 'empty') && Array.isArray(knowledgeSection.items)
      ? 'REAL'
      : 'UNAVAILABLE';

  const agentSection = record(sections.agent);
  const rawAgentStatus = agentSection.status;
  // The current plugin API returns a fixed `{status:"online"}` value, rather
  // than reading Hermes runtime health. Require explicit runtime provenance.
  const hasRuntimeProvenance = agentSection.source === 'hermes-runtime' || agentSection.source_type === 'hermes-runtime';
  const agentStatus = hasRuntimeProvenance && ['online', 'unavailable', 'not_configured'].includes(String(rawAgentStatus))
    ? String(rawAgentStatus)
    : null;

  const homeSource: DataKind = sections.status === 'ok' ? 'REAL' : 'UNAVAILABLE';
  return {
    pendingCount: reviewSource === 'REAL' ? pending as number : null,
    review: reviewSource === 'REAL' ? review : [],
    reviewSource,
    projectItems: verifiedProjectItems,
    projectSource: hasBusinessProjectSchema ? 'REAL' : 'UNAVAILABLE',
    knowledgeItems,
    knowledgeSource,
    agentStatus,
    agentSource: agentStatus ? 'REAL' : 'UNAVAILABLE',
    today: todayState(sections.today),
    source: homeSource,
  };
}
