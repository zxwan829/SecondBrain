import React, { useCallback, useEffect, useState } from 'react';
import { parseProjectsResponse, type ProjectRecord, type ProjectsResponse } from './projects-brief-wire';

type Locale = 'zh-CN' | 'en';
type PageId = 'projects' | 'activity';
type PageLoadState = 'loading' | 'loaded' | 'backend-not-implemented' | 'unauthorized' | 'unavailable';
type ActivityKind = 'journal' | 'task';
type ActivityEvent = {
  activity_id: string;
  kind: ActivityKind;
  status: 'succeeded' | 'failed';
  occurred_at: string;
  journal_date?: string;
  task_due_date?: string | null;
  task_status?: 'open' | 'completed' | null;
};
type ActivityResponse = {
  status: 'ok' | 'empty' | 'partial' | 'unavailable';
  items: ActivityEvent[];
  pagination: { limit: number; offset: number; has_more: boolean };
  source: Array<'journal' | 'tasks'>;
  freshness: { checked_at: string };
};

const forbiddenActivityFields = ['original_text', 'original_command', 'session_id', 'operation_id'];

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isIsoDateTime(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}

function parseActivityResponse(value: unknown): ActivityResponse | null {
  const allowedResponseFields = new Set(['status', 'items', 'pagination', 'source', 'freshness']);
  if (!isRecord(value) || Object.keys(value).some((field) => !allowedResponseFields.has(field))
    || !['ok', 'empty', 'partial', 'unavailable'].includes(String(value.status))
    || !Array.isArray(value.items) || !isRecord(value.pagination) || !Array.isArray(value.source)
    || !isRecord(value.freshness) || !isIsoDateTime(value.freshness.checked_at)) return null;
  const pagination = value.pagination;
  if (!Number.isInteger(pagination.limit) || !Number.isInteger(pagination.offset)
    || typeof pagination.has_more !== 'boolean') return null;
  const items: ActivityEvent[] = [];
  const allowedEventFields = new Set(['activity_id', 'kind', 'status', 'occurred_at', 'journal_date', 'task_due_date', 'task_status']);
  for (const raw of value.items) {
    if (!isRecord(raw) || Object.keys(raw).some((field) => !allowedEventFields.has(field))
      || forbiddenActivityFields.some((field) => Object.hasOwn(raw, field))) return null;
    if (typeof raw.activity_id !== 'string' || !raw.activity_id.trim()
      || (raw.kind !== 'journal' && raw.kind !== 'task')
      || (raw.status !== 'succeeded' && raw.status !== 'failed')
      || !isIsoDateTime(raw.occurred_at)) return null;
    if (raw.journal_date !== undefined && (typeof raw.journal_date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(raw.journal_date))) return null;
    if (raw.task_due_date !== undefined && raw.task_due_date !== null
      && (typeof raw.task_due_date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(raw.task_due_date))) return null;
    if (raw.task_status !== undefined && raw.task_status !== null
      && raw.task_status !== 'open' && raw.task_status !== 'completed') return null;
    items.push(raw as unknown as ActivityEvent);
  }
  if (!value.source.every((item) => item === 'journal' || item === 'tasks')) return null;
  return {
    status: value.status as ActivityResponse['status'], items,
    pagination: { limit: pagination.limit as number, offset: pagination.offset as number, has_more: pagination.has_more },
    source: value.source as ActivityResponse['source'],
    freshness: { checked_at: value.freshness.checked_at },
  };
}

async function loadPage(page: PageId, signal: AbortSignal): Promise<unknown> {
  const path = page === 'projects'
    ? '/api/projects?limit=1&offset=0'
    : '/api/activity?limit=50&offset=0';
  const response = await fetch(path, { credentials: 'same-origin', signal, headers: { Accept: 'application/json' } });
  if (response.status === 401 || response.status === 403) throw new Error('unauthorized');
  if (response.status === 404 || response.status === 501) throw new Error('backend-not-implemented');
  if (!response.ok) throw new Error('unavailable');
  return response.json();
}

const projectsPreview = [
  { id: 'SYNTH-PROJECT-001', name: '合成项目 · 家庭知识整理', status: '进行中', next: '确认资料分类规则', notes: ['合成资料目录', '分类草案'] },
  { id: 'SYNTH-PROJECT-002', name: '合成项目 · 阅读计划', status: '待开始', next: '选择第一本书', notes: ['计划草稿'] },
];
const activityPreview: ActivityEvent[] = [
  { activity_id: 'SYNTH-ACTIVITY-001', kind: 'journal', status: 'succeeded', occurred_at: '2026-10-20T09:30:00+08:00', journal_date: '2026-10-20' },
  { activity_id: 'SYNTH-ACTIVITY-002', kind: 'task', status: 'failed', occurred_at: '2026-10-19T16:00:00+08:00', task_due_date: '2026-10-21', task_status: 'open' },
];

const copy = {
  'zh-CN': {
    projects: { eyebrow: 'WORKSPACE / PROJECTS', title: '项目', description: '查看项目状态、下一步行动与关联资料。' },
    activity: { eyebrow: 'WORKSPACE / ACTIVITY', title: '动态', description: '按时间查看收录、审核与协作事件。' },
    unavailable: '该页面数据暂不可用。请稍后重试。', unauthorized: '当前账户无权读取此页面数据。',
    notImplemented: 'BACKEND_NOT_IMPLEMENTED · 只读接口尚未进入 main。',
    projectsUnconfigured: 'NOT BUSINESS CLOSED · 尚未配置可信项目数据源。当前不会扫描文件目录或从收件箱推断项目。',
    projectsEmpty: '可信项目索引已读取，但当前没有项目记录。',
    projectsUnavailable: '可信项目数据源暂不可用。没有回退到目录扫描或推断。',
    projectPartial: '部分项目来源或关联未通过核验；仅展示 Core 已确认的记录。',
    projectStatuses: { active: '进行中', paused: '已暂停', completed: '已完成', archived: '已归档', unknown: '未知' },
    projectRecent: '最近活动', linkedNoteRefs: '已核验关联笔记引用',
    activityUnconfigured: '暂无可展示的 Core Journal/Task 操作动态。未读取 Hermes 会话或消息。',
    partial: '部分来源暂不可用；以下仅展示可确认的来源。', empty: '暂无动态。',
    retry: '重试', localPreview: '查看本地合成预览', hidePreview: '隐藏合成预览',
    local: 'LOCAL_CANDIDATE · SYNTHETIC FIXTURE', disclosure: '仅本地开发预览样例，不是你的真实业务数据。',
    projectStatus: '状态', next: '下一步', notes: '关联资料', journal: '日记操作', task: '待办操作',
    succeeded: '已完成', failed: '未完成', dueDate: '到期日期', taskStatus: '待办状态',
    happenedAt: '时间', checkedAt: '数据检查时间', source: '数据来源', sources: { journal: '日记', tasks: '待办' },
  },
  en: {
    projects: { eyebrow: 'WORKSPACE / PROJECTS', title: 'Projects', description: 'Review project status, next actions, and related notes.' },
    activity: { eyebrow: 'WORKSPACE / ACTIVITY', title: 'Activity', description: 'Review capture, approval, and collaboration events.' },
    unavailable: 'This page data is unavailable. Try again later.', unauthorized: 'This account cannot read this page.',
    notImplemented: 'BACKEND_NOT_IMPLEMENTED · The read-only API is not on main yet.',
    projectsUnconfigured: 'NOT BUSINESS CLOSED · No trusted project source is configured. Files are not scanned and projects are not inferred from Inbox.',
    projectsEmpty: 'The trusted project index was read successfully and contains no project records.',
    projectsUnavailable: 'The trusted project source is unavailable. No directory scan or inference was used as a fallback.',
    projectPartial: 'Some project sources or relations could not be verified; only Core-confirmed records are shown.',
    projectStatuses: { active: 'Active', paused: 'Paused', completed: 'Completed', archived: 'Archived', unknown: 'Unknown' },
    projectRecent: 'Recent activity', linkedNoteRefs: 'Verified linked note references',
    activityUnconfigured: 'No Core Journal/Task activity is available. Hermes sessions and messages were not read.',
    partial: 'Some sources are unavailable; only confirmed sources are shown.', empty: 'No activity yet.',
    retry: 'Retry', localPreview: 'Show local synthetic preview', hidePreview: 'Hide synthetic preview',
    local: 'LOCAL_CANDIDATE · SYNTHETIC FIXTURE', disclosure: 'Local development preview only. This is not real business data.',
    projectStatus: 'Status', next: 'Next action', notes: 'Related notes', journal: 'Journal operation', task: 'Task operation',
    succeeded: 'Succeeded', failed: 'Failed', dueDate: 'Due date', taskStatus: 'Task status',
    happenedAt: 'Time', checkedAt: 'Data checked', source: 'Sources', sources: { journal: 'Journal', tasks: 'Tasks' },
  },
} as const;

export function V1ReadOnlyPage({ page, locale }: { page: PageId; locale: Locale }) {
  const text = copy[locale][page];
  const t = copy[locale];
  const [state, setState] = useState<PageLoadState>('loading');
  const [activity, setActivity] = useState<ActivityResponse | null>(null);
  const [projects, setProjects] = useState<ProjectsResponse | null>(null);
  const [preview, setPreview] = useState(false);
  const [revision, setRevision] = useState(0);
  const load = useCallback(async (signal: AbortSignal) => {
    setState('loading');
    try {
      const payload = await loadPage(page, signal);
      if (signal.aborted) return;
      if (page === 'projects') {
        const parsed = parseProjectsResponse(payload);
        if (!parsed) throw new Error('unavailable');
        setProjects(parsed);
        setState('loaded');
        return;
      }
      const parsed = parseActivityResponse(payload);
      if (!parsed) throw new Error('unavailable');
      setActivity(parsed);
      setState('loaded');
    } catch (error) {
      if (signal.aborted) return;
      const reason = error instanceof Error ? error.message : 'unavailable';
      setState(reason === 'unauthorized' ? 'unauthorized' : reason === 'backend-not-implemented' ? 'backend-not-implemented' : 'unavailable');
    }
  }, [page]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, revision]);

  const eventTitle = (event: ActivityEvent) => event.kind === 'journal' ? t.journal : t.task;
  const formatTime = (value: string) => new Date(value).toLocaleString(locale === 'en' ? 'en-US' : 'zh-CN');

  return (
    <section className={`v1-readonly-page v1-readonly-page-${page}`} aria-labelledby={`${page}-title`}>
      <header className="v1-page-header">
        <div>
          <p className="eyebrow">SECONDBRAIN <span>/</span> {text.eyebrow}</p>
          <h1 id={`${page}-title`}>{text.title}</h1>
          <p className="workspace-subtitle">{text.description}</p>
        </div>
        <button type="button" className="v1-page-retry" onClick={() => setRevision((value) => value + 1)} disabled={state === 'loading'}>{t.retry}</button>
      </header>

      {state === 'loading' ? <p className="v1-page-state" role="status">{locale === 'en' ? 'Loading…' : '正在加载…'}</p>
        : state === 'backend-not-implemented' ? <p className="v1-page-state is-unavailable" role="status">{t.notImplemented}</p>
          : state === 'unauthorized' ? <p className="v1-page-state is-unavailable" role="alert">{t.unauthorized}</p>
            : state === 'unavailable' ? <p className="v1-page-state is-unavailable" role="alert">{t.unavailable}</p>
              : page === 'projects' && projects?.status === 'not_configured' ? <p className="v1-page-state" role="status">{t.projectsUnconfigured}</p>
                : page === 'projects' && projects?.status === 'unavailable' ? <p className="v1-page-state is-unavailable" role="alert">{t.projectsUnavailable}</p>
                  : page === 'projects' && projects?.status === 'empty' ? <p className="v1-page-state" role="status">{t.projectsEmpty} · {locale === 'en' ? 'Checked' : '检查时间'} {new Date(projects.freshness.checked_at).toLocaleString(locale === 'en' ? 'en-US' : 'zh-CN')}</p>
                    : page === 'projects' && projects ? <>
                      {projects.status === 'partial' && <p className="v1-page-state is-partial" role="status">{t.projectPartial}</p>}
                      <ProjectList items={projects.items} locale={locale} checkedAt={projects.freshness.checked_at} />
                    </>
                : activity?.status === 'unavailable' ? <p className="v1-page-state is-unavailable" role="alert">{t.unavailable}</p>
                  : activity?.items.length === 0 ? <p className="v1-page-state" role="status">{t.empty}</p>
                    : <>
                      {activity?.status === 'partial' && <p className="v1-page-state is-partial" role="status">{t.partial}</p>}
                      <ol className="v1-activity-list" aria-label={text.title}>
                        {activity?.items.map((event) => (
                          <li className="v1-data-card v1-activity-card" key={event.activity_id}>
                            <span className="v1-activity-marker" aria-hidden="true" />
                            <div className="v1-activity-copy">
                              <div className="v1-data-card-heading"><h2>{eventTitle(event)}</h2><span className="v1-status-pill">{event.status === 'succeeded' ? t.succeeded : t.failed}</span></div>
                              <dl className="v1-activity-meta">
                                <div><dt>{t.source}</dt><dd>{t.sources[event.kind === 'journal' ? 'journal' : 'tasks']}</dd></div>
                                <div><dt>{t.happenedAt}</dt><dd><time>{formatTime(event.occurred_at)}</time></dd></div>
                                {event.journal_date && <div><dt>{t.journal}</dt><dd><time>{event.journal_date}</time></dd></div>}
                                {event.task_due_date && <div><dt>{t.dueDate}</dt><dd><time>{event.task_due_date}</time></dd></div>}
                                {event.task_status && <div><dt>{t.taskStatus}</dt><dd>{event.task_status}</dd></div>}
                              </dl>
                            </div>
                          </li>
                        ))}
                      </ol>
                    </>}

      {import.meta.env.DEV && <section className="v1-local-preview" aria-label={t.local}>
        <button type="button" className="v1-local-preview-toggle" aria-expanded={preview} onClick={() => setPreview((value) => !value)}>{preview ? t.hidePreview : t.localPreview}</button>
        {preview && <div className="v1-local-preview-content">
          <strong>{t.local}</strong><p>{t.disclosure}</p>
          {page === 'projects' ? <div className="v1-project-grid">{projectsPreview.map((project) => <article className="v1-data-card v1-project-card" key={project.id} data-fixture-id={project.id}>
            <div className="v1-data-card-heading"><h2>{project.name}</h2><span className="v1-status-pill">{project.status}</span></div>
            <dl className="v1-data-fields"><div><dt>{t.next}</dt><dd>{project.next}</dd></div></dl>
            <div className="v1-related-notes"><h3>{t.notes}</h3><ul>{project.notes.map((note) => <li key={note}>{note}</li>)}</ul></div>
          </article>)}</div> : <ol className="v1-activity-list">{activityPreview.map((event) => <li className="v1-data-card v1-activity-card" key={event.activity_id} data-fixture-id={event.activity_id}>
            <span className="v1-activity-marker" aria-hidden="true" /><div className="v1-activity-copy"><div className="v1-data-card-heading"><h2>{eventTitle(event)}</h2><span className="v1-status-pill">{event.status === 'succeeded' ? t.succeeded : t.failed}</span></div>
              <dl className="v1-activity-meta"><div><dt>{t.happenedAt}</dt><dd><time>{formatTime(event.occurred_at)}</time></dd></div></dl></div>
          </li>)}</ol>}
        </div>}
      </section>}
    </section>
  );
}

function ProjectList({ items, locale, checkedAt }: { items: ProjectRecord[]; locale: Locale; checkedAt: string }) {
  const t = copy[locale];
  return <>
    <p className="calendar-source-note">{locale === 'en' ? 'Source checked' : '来源检查时间'} · {new Date(checkedAt).toLocaleString(locale === 'en' ? 'en-US' : 'zh-CN')}</p>
    <div className="v1-project-grid">
      {items.map((project) => <article className="v1-data-card v1-project-card" key={project.id}>
        <div className="v1-data-card-heading"><h2>{project.title}</h2><span className="v1-status-pill">{t.projectStatuses[project.status]}</span></div>
        {(project.next_step || project.updated_at || project.recent_activity || project.linked_notes) && <dl className="v1-data-fields">
          {project.next_step && <div><dt>{t.next}</dt><dd>{project.next_step}</dd></div>}
          {project.updated_at && <div><dt>{t.checkedAt}</dt><dd><time>{new Date(project.updated_at).toLocaleString(locale === 'en' ? 'en-US' : 'zh-CN')}</time></dd></div>}
          {project.recent_activity && <div><dt>{t.projectRecent}</dt><dd>{project.recent_activity.kind} · <time>{new Date(project.recent_activity.occurred_at).toLocaleString(locale === 'en' ? 'en-US' : 'zh-CN')}</time></dd></div>}
          {project.linked_notes && project.linked_notes.length > 0 && <div><dt>{t.linkedNoteRefs}</dt><dd>{project.linked_notes.length}</dd></div>}
        </dl>}
      </article>)}
    </div>
  </>;
}
