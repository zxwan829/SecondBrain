export type ProjectSourceStatus = 'real' | 'partial' | 'empty' | 'not_configured' | 'unavailable';
export type ProjectSourceRef = { id: string; version: string };
export type ProjectRecord = {
  id: string;
  title: string;
  status: 'active' | 'paused' | 'completed' | 'archived' | 'unknown';
  next_step?: string;
  recent_activity?: { kind: 'task' | 'journal' | 'capture' | 'review'; occurred_at: string };
  linked_notes?: ProjectSourceRef[];
  updated_at?: string;
  source_ref: ProjectSourceRef;
};
export type ProjectsResponse = {
  status: ProjectSourceStatus;
  items: ProjectRecord[];
  pagination: { limit: number; offset: number; has_more: boolean };
  source: { kind: 'explicit-project-index' } | null;
  freshness: { checked_at: string };
};

export type BriefSourceStatus = 'real' | 'partial' | 'stale' | 'failed' | 'empty' | 'not_configured' | 'unavailable';
export type BriefSourceRef = { kind: 'project' | 'task' | 'note' | 'capture' | 'review' | 'journal'; id: string; version: string };
export type DailyBriefRecord = {
  brief_id: string;
  date: string;
  timezone: string;
  generated_at: string;
  generation_status: 'generated' | 'partial' | 'stale' | 'failed';
  categories: string[];
  summary: string;
  source_refs: BriefSourceRef[];
};
export type DailyBriefResponse = {
  status: BriefSourceStatus;
  items: DailyBriefRecord[];
  source: { kind: 'core-daily-brief-store' } | null;
  freshness: { checked_at: string };
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function hasOnlyKeys(value: Record<string, unknown>, allowed: readonly string[]): boolean {
  return Object.keys(value).every((key) => allowed.includes(key));
}

function isIsoDateTime(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,9})?(Z|([+-])(\d{2}):(\d{2}))$/.exec(value);
  if (!match) return false;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText, , , offsetHourText, offsetMinuteText] = match;
  const year = Number(yearText); const month = Number(monthText); const day = Number(dayText);
  const hour = Number(hourText); const minute = Number(minuteText); const second = Number(secondText);
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const offsetHour = offsetHourText === undefined ? 0 : Number(offsetHourText);
  const offsetMinute = offsetMinuteText === undefined ? 0 : Number(offsetMinuteText);
  return month >= 1 && month <= 12 && day >= 1 && day <= daysInMonth
    && hour <= 23 && minute <= 59 && second <= 59
    && offsetHour <= 23 && offsetMinute <= 59 && Number.isFinite(Date.parse(value));
}

function isUtcTimestamp(value: unknown): value is string {
  return isIsoDateTime(value) && /(?:Z|\+00:00)$/.test(value);
}

function isIsoDate(value: unknown): value is string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && Number.isFinite(Date.parse(`${value}T00:00:00.000Z`))
    && new Date(`${value}T00:00:00.000Z`).toISOString().slice(0, 10) === value;
}

function isOpaqueId(value: unknown): value is string {
  // Keep this aligned with Core's bounded opaque ID contract. These identifiers
  // are never interpreted as paths by the UI.
  return typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value);
}

function isSha256(value: unknown): value is string {
  return typeof value === 'string' && /^[a-f0-9]{64}$/i.test(value);
}

function parseProjectRef(value: unknown): ProjectSourceRef | null {
  if (!isRecord(value) || !hasOnlyKeys(value, ['id', 'version']) || !isOpaqueId(value.id) || !isSha256(value.version)) return null;
  return { id: value.id, version: value.version.toLowerCase() };
}

function parseProject(value: unknown): ProjectRecord | null {
  const allowed = ['id', 'title', 'status', 'next_step', 'recent_activity', 'linked_notes', 'updated_at', 'source_ref'];
  if (!isRecord(value) || !hasOnlyKeys(value, allowed) || !isOpaqueId(value.id)
    || typeof value.title !== 'string' || !value.title.trim() || value.title.length > 300
    || !['active', 'paused', 'completed', 'archived', 'unknown'].includes(String(value.status))) return null;
  const sourceRef = parseProjectRef(value.source_ref);
  if (!sourceRef) return null;
  let nextStep: string | undefined;
  if (value.next_step !== undefined) {
    if (typeof value.next_step !== 'string' || value.next_step.length > 2000) return null;
    nextStep = value.next_step;
  }
  let recentActivity: ProjectRecord['recent_activity'];
  if (value.recent_activity !== undefined) {
    if (!isRecord(value.recent_activity) || !hasOnlyKeys(value.recent_activity, ['kind', 'occurred_at'])
      || !['task', 'journal', 'capture', 'review'].includes(String(value.recent_activity.kind))
      || !isIsoDateTime(value.recent_activity.occurred_at)) return null;
    recentActivity = { kind: value.recent_activity.kind as NonNullable<ProjectRecord['recent_activity']>['kind'], occurred_at: value.recent_activity.occurred_at };
  }
  let linkedNotes: ProjectSourceRef[] | undefined;
  if (value.linked_notes !== undefined) {
    if (!Array.isArray(value.linked_notes) || value.linked_notes.length > 100) return null;
    linkedNotes = [];
    for (const item of value.linked_notes) {
      const ref = parseProjectRef(item);
      if (!ref) return null;
      linkedNotes.push(ref);
    }
  }
  let updatedAt: string | undefined;
  if (value.updated_at !== undefined) {
    if (!isIsoDateTime(value.updated_at)) return null;
    updatedAt = value.updated_at;
  }
  return { id: value.id, title: value.title, status: value.status as ProjectRecord['status'], source_ref: sourceRef,
    ...(nextStep !== undefined ? { next_step: nextStep } : {}), ...(recentActivity ? { recent_activity: recentActivity } : {}),
    ...(linkedNotes ? { linked_notes: linkedNotes } : {}), ...(updatedAt ? { updated_at: updatedAt } : {}) };
}

export function parseProjectsResponse(value: unknown, expectedLimit = 1, expectedOffset = 0): ProjectsResponse | null {
  if (!isRecord(value) || !hasOnlyKeys(value, ['status', 'items', 'pagination', 'source', 'freshness'])
    || !['real', 'partial', 'empty', 'not_configured', 'unavailable'].includes(String(value.status))
    || !Array.isArray(value.items) || value.items.length > expectedLimit || !isRecord(value.pagination)
    || !hasOnlyKeys(value.pagination, ['limit', 'offset', 'has_more'])
    || value.pagination.limit !== expectedLimit || value.pagination.offset !== expectedOffset || typeof value.pagination.has_more !== 'boolean'
    || !isRecord(value.freshness) || !hasOnlyKeys(value.freshness, ['checked_at']) || !isUtcTimestamp(value.freshness.checked_at)) return null;
  const status = value.status as ProjectSourceStatus;
  let source: ProjectsResponse['source'];
  if (value.source === null) source = null;
  else if (isRecord(value.source) && hasOnlyKeys(value.source, ['kind']) && value.source.kind === 'explicit-project-index') source = { kind: 'explicit-project-index' };
  else return null;
  if ((status === 'not_configured' || status === 'unavailable') && (value.items.length !== 0 || source !== null)) return null;
  if (status === 'empty' && (value.items.length !== 0 || source === null)) return null;
  if (status === 'real' && (value.items.length === 0 || source === null)) return null;
  if (status === 'partial' && source === null) return null;
  const items: ProjectRecord[] = [];
  for (const raw of value.items) {
    const item = parseProject(raw);
    if (!item) return null;
    items.push(item);
  }
  return { status, items, pagination: { limit: expectedLimit, offset: expectedOffset, has_more: value.pagination.has_more }, source,
    freshness: { checked_at: value.freshness.checked_at } };
}

function parseBriefSourceRef(value: unknown): BriefSourceRef | null {
  if (!isRecord(value) || !hasOnlyKeys(value, ['kind', 'id', 'version'])
    || !['project', 'task', 'note', 'capture', 'review', 'journal'].includes(String(value.kind))
    || !isOpaqueId(value.id) || !isSha256(value.version)) return null;
  return { kind: value.kind as BriefSourceRef['kind'], id: value.id, version: value.version.toLowerCase() };
}

function parseBriefRecord(value: unknown, requestedDate: string, requestedTimezone: string): DailyBriefRecord | null {
  const allowed = ['brief_id', 'date', 'timezone', 'generated_at', 'generation_status', 'categories', 'summary', 'source_refs'];
  if (!isRecord(value) || !hasOnlyKeys(value, allowed) || !isOpaqueId(value.brief_id)
    || value.date !== requestedDate || value.timezone !== requestedTimezone || !isIsoDate(value.date)
    || !isIsoDateTime(value.generated_at) || !['generated', 'partial', 'stale', 'failed'].includes(String(value.generation_status))
    || !Array.isArray(value.categories) || value.categories.length > 30
    || !value.categories.every((category) => typeof category === 'string' && category.trim().length > 0 && category.length <= 80)
    || typeof value.summary !== 'string' || value.summary.length > 20000
    || !Array.isArray(value.source_refs) || value.source_refs.length > 50) return null;
  const refs: BriefSourceRef[] = [];
  const seen = new Set<string>();
  for (const raw of value.source_refs) {
    const ref = parseBriefSourceRef(raw);
    if (!ref) return null;
    const key = `${ref.kind}:${ref.id}`;
    if (seen.has(key)) return null;
    seen.add(key); refs.push(ref);
  }
  if (value.generation_status === 'generated' && refs.length === 0) return null;
  return { brief_id: value.brief_id, date: value.date, timezone: value.timezone, generated_at: value.generated_at,
    generation_status: value.generation_status as DailyBriefRecord['generation_status'], categories: [...value.categories] as string[],
    summary: value.summary, source_refs: refs };
}

export function parseDailyBriefResponse(value: unknown, requestedDate: string, requestedTimezone: string): DailyBriefResponse | null {
  if (!isRecord(value) || !hasOnlyKeys(value, ['status', 'items', 'source', 'freshness'])
    || !['real', 'partial', 'stale', 'failed', 'empty', 'not_configured', 'unavailable'].includes(String(value.status))
    || !Array.isArray(value.items) || value.items.length > 1 || !isRecord(value.freshness)
    || !hasOnlyKeys(value.freshness, ['checked_at']) || !isUtcTimestamp(value.freshness.checked_at)) return null;
  const status = value.status as BriefSourceStatus;
  let source: DailyBriefResponse['source'];
  if (value.source === null) source = null;
  else if (isRecord(value.source) && hasOnlyKeys(value.source, ['kind']) && value.source.kind === 'core-daily-brief-store') source = { kind: 'core-daily-brief-store' };
  else return null;
  if (status === 'not_configured' && (value.items.length !== 0 || source !== null)) return null;
  if (status === 'unavailable' && value.items.length !== 0) return null;
  if (status === 'empty' && (value.items.length !== 0 || source === null)) return null;
  if (status !== 'not_configured' && status !== 'unavailable' && source === null) return null;
  if (status === 'real' && value.items.length !== 1) return null;
  if (['stale', 'failed'].includes(status) && value.items.length !== 0) return null;
  if (status === 'partial' && value.items.length > 1) return null;
  const items: DailyBriefRecord[] = [];
  for (const raw of value.items) {
    const item = parseBriefRecord(raw, requestedDate, requestedTimezone);
    if (!item) return null;
    if ((status === 'real' && item.generation_status !== 'generated')
      || (status === 'partial' && item.generation_status !== 'partial')
      || (status === 'stale' && item.generation_status !== 'stale')
      || (status === 'failed' && item.generation_status !== 'failed')) return null;
    items.push(item);
  }
  return { status, items, source, freshness: { checked_at: value.freshness.checked_at } };
}
