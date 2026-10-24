import React, { useCallback, useEffect, useState } from 'react';
import { parseProjectsResponse, type ProjectRecord, type ProjectsResponse } from './projects-brief-wire';

type Locale = 'zh-CN' | 'en';
type PageId = 'projects' | 'activity';
type PageLoadState = 'loading' | 'loaded' | 'backend-not-implemented' | 'unauthorized' | 'unavailable';
type ActivityKind = 'journal' | 'task' | 'project' | 'daily_brief' | 'personal_memory' | 'capture' | 'review';
type ActivityActionStatus = 'succeeded' | 'failed' | 'updated' | 'created' | 'corrected' | 'revoked' | 'expired';
type CaptureLifecycleStatus = 'pending' | 'prepared' | 'processing' | 'completed' | 'partial_success' | 'failed';
type ReviewStatus = 'pending' | 'deferred' | 'approved' | 'promoting' | 'promoted' | 'failed';
type ActivityEvent = {
  activity_id: string;
  kind: ActivityKind;
  status: ActivityActionStatus | CaptureLifecycleStatus | ReviewStatus;
  occurred_at: string;
  journal_date?: string;
  task_due_date?: string | null;
  task_status?: 'open' | 'completed' | null;
  daily_brief_date?: string;
  project_id?: string;
  project_status?: 'active' | 'paused' | 'completed' | 'archived' | 'unknown';
};
type ActivityResponse = {
  status: 'ok' | 'empty' | 'partial' | 'unavailable';
  items: ActivityEvent[];
  pagination: { limit: number; offset: number; has_more: boolean };
  source: Array<'journal' | 'tasks' | 'projects' | 'daily_brief' | 'personal_memory' | 'capture' | 'review'>;
  freshness: { checked_at: string };
};

const forbiddenActivityFields = ['original_text', 'original_command', 'session_id', 'operation_id'];
const activityActionStatuses: ActivityActionStatus[] = ['succeeded', 'failed', 'updated', 'created', 'corrected', 'revoked', 'expired'];
const captureLifecycleStatuses: CaptureLifecycleStatus[] = ['pending', 'prepared', 'processing', 'completed', 'partial_success', 'failed'];
const reviewStatuses: ReviewStatus[] = ['pending', 'deferred', 'approved', 'promoting', 'promoted', 'failed'];

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
  const allowedEventFields = new Set(['activity_id', 'kind', 'status', 'occurred_at', 'journal_date', 'task_due_date', 'task_status', 'daily_brief_date', 'project_id', 'project_status']);
  const allowedCaptureFields = new Set(['activity_id', 'kind', 'status', 'occurred_at']);
  for (const raw of value.items) {
    if (!isRecord(raw) || Object.keys(raw).some((field) => !allowedEventFields.has(field))
      || forbiddenActivityFields.some((field) => Object.hasOwn(raw, field))) return null;
    const kind = String(raw.kind);
    if (kind === 'capture' && Object.keys(raw).some((field) => !allowedCaptureFields.has(field))) return null;
    const validStatus = kind === 'capture'
      ? captureLifecycleStatuses.includes(String(raw.status) as CaptureLifecycleStatus)
      : kind === 'review'
        ? reviewStatuses.includes(String(raw.status) as ReviewStatus)
        : activityActionStatuses.includes(String(raw.status) as ActivityActionStatus);
    if (typeof raw.activity_id !== 'string' || !raw.activity_id.trim()
      || !['journal', 'task', 'project', 'daily_brief', 'personal_memory', 'capture', 'review'].includes(kind)
      || !validStatus
      || !isIsoDateTime(raw.occurred_at)) return null;
    if (raw.journal_date !== undefined && (typeof raw.journal_date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(raw.journal_date))) return null;
    if (raw.task_due_date !== undefined && raw.task_due_date !== null
      && (typeof raw.task_due_date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(raw.task_due_date))) return null;
    if (raw.task_status !== undefined && raw.task_status !== null
      && raw.task_status !== 'open' && raw.task_status !== 'completed') return null;
    if (raw.daily_brief_date !== undefined && (typeof raw.daily_brief_date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(raw.daily_brief_date))) return null;
    if (raw.project_id !== undefined && (typeof raw.project_id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(raw.project_id))) return null;
    if (raw.project_status !== undefined && !['active', 'paused', 'completed', 'archived', 'unknown'].includes(String(raw.project_status))) return null;
    items.push(raw as unknown as ActivityEvent);
  }
  if (!value.source.every((item) => ['journal', 'tasks', 'projects', 'daily_brief', 'personal_memory', 'capture', 'review'].includes(String(item)))) return null;
  return {
    status: value.status as ActivityResponse['status'], items,
    pagination: { limit: pagination.limit as number, offset: pagination.offset as number, has_more: pagination.has_more },
    source: value.source as ActivityResponse['source'],
    freshness: { checked_at: value.freshness.checked_at },
  };
}

async function loadPage(page: PageId, signal: AbortSignal, projectLimit = 50, projectOffset = 0, activityOffset = 0): Promise<unknown> {
  const path = page === 'projects'
    ? `/api/projects?limit=${projectLimit}&offset=${projectOffset}`
    : `/api/activity?limit=50&offset=${activityOffset}`;
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
    activity: { eyebrow: 'WORKSPACE / ACTIVITY', title: '动态', description: '按时间查看经过核验的业务活动。' },
    unavailable: '该页面数据暂不可用。请稍后重试。', unauthorized: '当前账户无权读取此页面数据。',
    notImplemented: 'BACKEND_NOT_IMPLEMENTED · 只读接口尚未进入 main。',
    projectsUnconfigured: 'NOT BUSINESS CLOSED · 尚未配置可信项目数据源。当前不会扫描文件目录或从收件箱推断项目。',
    projectsEmpty: '可信项目索引已读取，但当前没有项目记录。',
    projectsUnavailable: '可信项目数据源暂不可用。没有回退到目录扫描或推断。',
    projectPartial: '部分项目来源或关联未通过核验；仅展示 Core 已确认的记录。',
    projectStatuses: { active: '进行中', paused: '已暂停', completed: '已完成', archived: '已归档', unknown: '未知' },
    projectRecent: '最近活动', linkedNoteRefs: '已核验关联笔记引用',
    activityUnconfigured: '暂无可展示的 Core 操作动态。未读取 Hermes 会话或消息。',
    partial: '当前动态来源或时间范围不完整；以下仅展示 Core 已核实的条目。', empty: '暂无动态。',
    loadMore: '加载更多动态', loadingMore: '正在加载…', moreFailed: '更多动态暂时无法读取。', retryMore: '重试加载',
    retry: '重试', localPreview: '查看本地合成预览', hidePreview: '隐藏合成预览',
    local: 'LOCAL_CANDIDATE · SYNTHETIC FIXTURE', disclosure: '仅本地开发预览样例，不是你的真实业务数据。',
    projectStatus: '状态', next: '下一步', notes: '关联资料', journal: '日记操作', task: '待办操作',
    succeeded: '已完成', failed: '未完成', dueDate: '到期日期', taskStatus: '待办状态',
    happenedAt: '时间', checkedAt: '数据检查时间', source: '数据来源', briefDate: '简报日期',
    activityKinds: { journal: '日记操作', task: '待办操作', project: '项目更新', daily_brief: '每日简报', personal_memory: '个人记忆操作', capture: '采集状态', review: '审核状态' },
    activityStatuses: { succeeded: '已完成', failed: '未完成', updated: '已更新', created: '已创建', corrected: '已更正', revoked: '已撤销', expired: '已过期', pending: '待审核', deferred: '已暂缓', approved: '已批准', promoting: '处理中', promoted: '已发布' },
    captureStatuses: { pending: '待处理', prepared: '已准备', processing: '处理中', completed: '已完成', partial_success: '部分完成', failed: '失败' },
    sources: { journal: '日记', tasks: '待办', projects: '项目', daily_brief: '每日简报', personal_memory: '个人记忆', capture: '采集', review: '审核' },
  },
  en: {
    projects: { eyebrow: 'WORKSPACE / PROJECTS', title: 'Projects', description: 'Review project status, next actions, and related notes.' },
    activity: { eyebrow: 'WORKSPACE / ACTIVITY', title: 'Activity', description: 'Review verified business activity over time.' },
    unavailable: 'This page data is unavailable. Try again later.', unauthorized: 'This account cannot read this page.',
    notImplemented: 'BACKEND_NOT_IMPLEMENTED · The read-only API is not on main yet.',
    projectsUnconfigured: 'NOT BUSINESS CLOSED · No trusted project source is configured. Files are not scanned and projects are not inferred from Inbox.',
    projectsEmpty: 'The trusted project index was read successfully and contains no project records.',
    projectsUnavailable: 'The trusted project source is unavailable. No directory scan or inference was used as a fallback.',
    projectPartial: 'Some project sources or relations could not be verified; only Core-confirmed records are shown.',
    projectStatuses: { active: 'Active', paused: 'Paused', completed: 'Completed', archived: 'Archived', unknown: 'Unknown' },
    projectRecent: 'Recent activity', linkedNoteRefs: 'Verified linked note references',
    activityUnconfigured: 'No Core activity is available. Hermes sessions and messages were not read.',
    partial: 'Activity sources or the covered time range are incomplete; only Core-verified events are shown.', empty: 'No activity yet.',
    loadMore: 'Load more activity', loadingMore: 'Loading…', moreFailed: 'More activity could not be loaded.', retryMore: 'Retry loading',
    retry: 'Retry', localPreview: 'Show local synthetic preview', hidePreview: 'Hide synthetic preview',
    local: 'LOCAL_CANDIDATE · SYNTHETIC FIXTURE', disclosure: 'Local development preview only. This is not real business data.',
    projectStatus: 'Status', next: 'Next action', notes: 'Related notes', journal: 'Journal operation', task: 'Task operation',
    succeeded: 'Succeeded', failed: 'Failed', dueDate: 'Due date', taskStatus: 'Task status',
    happenedAt: 'Time', checkedAt: 'Data checked', source: 'Sources', briefDate: 'Brief date',
    activityKinds: { journal: 'Journal operation', task: 'Task operation', project: 'Project update', daily_brief: 'Daily Brief', personal_memory: 'Personal Memory operation', capture: 'Capture status', review: 'Review status' },
    activityStatuses: { succeeded: 'Succeeded', failed: 'Failed', updated: 'Updated', created: 'Created', corrected: 'Corrected', revoked: 'Revoked', expired: 'Expired', pending: 'Pending review', deferred: 'Deferred', approved: 'Approved', promoting: 'Processing', promoted: 'Promoted' },
    captureStatuses: { pending: 'Pending', prepared: 'Prepared', processing: 'Processing', completed: 'Completed', partial_success: 'Partial success', failed: 'Failed' },
    sources: { journal: 'Journal', tasks: 'Tasks', projects: 'Projects', daily_brief: 'Daily Brief', personal_memory: 'Personal Memory', capture: 'Capture', review: 'Review' },
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
  const [projectOffset, setProjectOffset] = useState(0);
  const [activityOffset, setActivityOffset] = useState(0);
  const [activityLoadingMore, setActivityLoadingMore] = useState(false);
  const [activityMoreFailed, setActivityMoreFailed] = useState(false);
  const requestedProjectId = page === 'projects' ? new URLSearchParams(window.location.search).get('project_id') : null;
  const targetProjectId = requestedProjectId && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(requestedProjectId) ? requestedProjectId : null;
  const projectLimit = 50;
  const load = useCallback(async (signal: AbortSignal) => {
    const appendingActivity = page === 'activity' && activityOffset > 0;
    if (appendingActivity) setActivityLoadingMore(true);
    else setState('loading');
    setActivityMoreFailed(false);
    try {
      const payload = await loadPage(page, signal, projectLimit, projectOffset, activityOffset);
      if (signal.aborted) return;
      if (page === 'projects') {
        const parsed = parseProjectsResponse(payload, projectLimit, projectOffset);
        if (!parsed) throw new Error('unavailable');
        setProjects(parsed);
        setState('loaded');
        return;
      }
      const parsed = parseActivityResponse(payload);
      if (!parsed) throw new Error('unavailable');
      setActivity((current) => {
        if (!appendingActivity || !current) return parsed;
        const seen = new Set(current.items.map((item) => item.activity_id));
        const items = [...current.items, ...parsed.items.filter((item) => {
          if (seen.has(item.activity_id)) return false;
          seen.add(item.activity_id);
          return true;
        })];
        return {
          ...parsed,
          status: current.status === 'partial' || parsed.status === 'partial' ? 'partial' : parsed.status,
          items,
          pagination: parsed.pagination,
        };
      });
      setState('loaded');
    } catch (error) {
      if (signal.aborted) return;
      const reason = error instanceof Error ? error.message : 'unavailable';
      if (page === 'activity' && activityOffset > 0) {
        if (reason === 'unauthorized') {
          setActivity(null);
          setActivityMoreFailed(false);
          setState('unauthorized');
        } else {
          setActivityMoreFailed(true);
        }
      } else {
        setState(reason === 'unauthorized' ? 'unauthorized' : reason === 'backend-not-implemented' ? 'backend-not-implemented' : 'unavailable');
      }
    } finally {
      if (page === 'activity' && activityOffset > 0) setActivityLoadingMore(false);
    }
  }, [page, projectLimit, projectOffset, activityOffset]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, revision]);

  const eventTitle = (event: ActivityEvent) => t.activityKinds[event.kind];
  const eventStatus = (event: ActivityEvent) => event.kind === 'capture'
    ? t.captureStatuses[event.status as CaptureLifecycleStatus]
    : t.activityStatuses[event.status as ActivityActionStatus];
  const formatTime = (value: string) => new Date(value).toLocaleString(locale === 'en' ? 'en-US' : 'zh-CN');

  return (
    <section className={`v1-readonly-page v1-readonly-page-${page}`} aria-labelledby={`${page}-title`}>
      <header className="v1-page-header">
        <div>
          <p className="eyebrow">SECONDBRAIN <span>/</span> {text.eyebrow}</p>
          <h1 id={`${page}-title`}>{text.title}</h1>
          <p className="workspace-subtitle">{text.description}</p>
        </div>
        <button type="button" className="v1-page-retry" onClick={() => {
          if (page === 'activity') {
            setActivityOffset(0);
            setActivityMoreFailed(false);
          }
          setRevision((value) => value + 1);
        }} disabled={state === 'loading' || activityLoadingMore}>{t.retry}</button>
      </header>

      {state === 'loading' ? <p className="v1-page-state" role="status">{locale === 'en' ? 'Loading…' : '正在加载…'}</p>
        : state === 'backend-not-implemented' ? <p className="v1-page-state is-unavailable" role="status">{t.notImplemented}</p>
          : state === 'unauthorized' ? <p className="v1-page-state is-unavailable" role="alert">{t.unauthorized}</p>
            : state === 'unavailable' ? <p className="v1-page-state is-unavailable" role="alert">{t.unavailable}</p>
              : page === 'projects' && projects?.status === 'not_configured' ? <p className="v1-page-state" role="status">{t.projectsUnconfigured}</p>
                : page === 'projects' && projects?.status === 'unavailable' ? <p className="v1-page-state is-unavailable" role="alert">{t.projectsUnavailable}</p>
                : page === 'projects' && projects?.status === 'empty' ? <>
                  <p className="v1-page-state" role="status">{t.projectsEmpty} · {locale === 'en' ? 'Checked' : '检查时间'} {new Date(projects.freshness.checked_at).toLocaleString(locale === 'en' ? 'en-US' : 'zh-CN')}</p>
                  <ProjectPagination locale={locale} offset={projectOffset} limit={projectLimit} hasMore={projects.pagination.has_more} onOffset={setProjectOffset} />
                </>
                    : page === 'projects' && projects ? <>
                      {projects.status === 'partial' && <p className="v1-page-state is-partial" role="status">{t.projectPartial}</p>}
                      <ProjectList items={projects.items} locale={locale} checkedAt={projects.freshness.checked_at} targetId={targetProjectId} />
                      <ProjectPagination locale={locale} offset={projectOffset} limit={projectLimit} hasMore={projects.pagination.has_more} onOffset={setProjectOffset} />
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
                              <div className="v1-data-card-heading"><h2>{eventTitle(event)}</h2><span className="v1-status-pill">{eventStatus(event)}</span></div>
                              <dl className="v1-activity-meta">
                                <div><dt>{t.source}</dt><dd>{t.sources[event.kind === 'task' ? 'tasks' : event.kind === 'project' ? 'projects' : event.kind]}</dd></div>
                                <div><dt>{t.happenedAt}</dt><dd><time>{formatTime(event.occurred_at)}</time></dd></div>
                                {event.journal_date && <div><dt>{t.journal}</dt><dd><time>{event.journal_date}</time></dd></div>}
                                {event.daily_brief_date && <div><dt>{t.briefDate}</dt><dd><time>{event.daily_brief_date}</time></dd></div>}
                                {event.project_status && <div><dt>{t.projectStatus}</dt><dd>{t.projectStatuses[event.project_status]}</dd></div>}
                                {event.task_due_date && <div><dt>{t.dueDate}</dt><dd><time>{event.task_due_date}</time></dd></div>}
                                {event.task_status && <div><dt>{t.taskStatus}</dt><dd>{event.task_status}</dd></div>}
                              </dl>
                            </div>
                          </li>
                        ))}
                      </ol>
                      {activityMoreFailed && <p className="v1-page-state is-unavailable" role="alert">{t.moreFailed} <button type="button" onClick={() => setRevision((value) => value + 1)} disabled={activityLoadingMore}>{t.retryMore}</button></p>}
                      {activity?.pagination.has_more && <nav className="v1-pagination" aria-label={locale === 'en' ? 'Activity pages' : '动态分页'}>
                        <span>{locale === 'en' ? `${activity.items.length} events loaded` : `已显示 ${activity.items.length} 条动态`}</span>
                        <button type="button" disabled={activityLoadingMore || activityMoreFailed} onClick={() => {
                          setActivityMoreFailed(false);
                          setActivityOffset(activity.pagination.offset + activity.pagination.limit);
                        }}>{activityLoadingMore ? t.loadingMore : t.loadMore}</button>
                      </nav>}
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
            <span className="v1-activity-marker" aria-hidden="true" /><div className="v1-activity-copy"><div className="v1-data-card-heading"><h2>{eventTitle(event)}</h2><span className="v1-status-pill">{eventStatus(event)}</span></div>
              <dl className="v1-activity-meta"><div><dt>{t.happenedAt}</dt><dd><time>{formatTime(event.occurred_at)}</time></dd></div></dl></div>
          </li>)}</ol>}
        </div>}
      </section>}
    </section>
  );
}

function ProjectPagination({ locale, offset, limit, hasMore, onOffset }: { locale: Locale; offset: number; limit: number; hasMore: boolean; onOffset: React.Dispatch<React.SetStateAction<number>> }) {
  return <nav className="v1-pagination" aria-label={locale === 'en' ? 'Project pages' : '项目分页'}>
    <button type="button" disabled={offset === 0} onClick={() => onOffset((value) => Math.max(0, value - limit))}>{locale === 'en' ? 'Previous projects' : '上一页项目'}</button>
    <span>{offset + 1}–{offset + limit}</span>
    <button type="button" disabled={!hasMore} onClick={() => onOffset((value) => value + limit)}>{locale === 'en' ? 'More projects' : '更多项目'}</button>
  </nav>;
}

function ProjectList({ items, locale, checkedAt, targetId }: { items: ProjectRecord[]; locale: Locale; checkedAt: string; targetId: string | null }) {
  const t = copy[locale];
  return <>
    <p className="calendar-source-note">{locale === 'en' ? 'Source checked' : '来源检查时间'} · {new Date(checkedAt).toLocaleString(locale === 'en' ? 'en-US' : 'zh-CN')}</p>
    <div className="v1-project-grid">
      {items.map((project) => <article id={project.id === targetId ? `project-${project.id}` : undefined} className={`v1-data-card v1-project-card${project.id === targetId ? ' is-brief-source' : ''}`} key={project.id}>
        <div className="v1-data-card-heading"><h2>{project.title}</h2><span className="v1-status-pill">{t.projectStatuses[project.status]}</span></div>
        {project.id === targetId && <p role="status">{locale === 'en' ? 'Referenced by this Daily Brief.' : '此项目被每日简报引用。'}</p>}
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
