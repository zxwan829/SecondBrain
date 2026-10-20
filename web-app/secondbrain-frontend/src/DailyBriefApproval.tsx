import React, { useMemo, useRef, useState } from 'react';
import { parseProjectsResponse, type ProjectRecord } from './projects-brief-wire';

type Locale = 'zh-CN' | 'en';
type SourceRef = { kind: 'task' | 'project'; id: string; version: string };
type SourceChoice = { key: string; label: string; ref: SourceRef };
type WriteReceipt = { status: 'created' | 'duplicate'; brief_id: string; date: string; timezone: 'Asia/Shanghai'; record_version: string; operation_id: string };
type Phase = 'idle' | 'loading-sources' | 'editing' | 'confirming' | 'submitting' | 'unknown' | 'done';

const text = {
  'zh-CN': {
    start: '手动准备简报', cancel: '取消', loading: '正在读取可核验的任务与项目…',
    title: '手动创建每日简报', sourceHeading: '选择本次简报来源',
    journalBlocked: 'Journal 来源暂不可选：当前 Core 只读接口没有提供可核验的 Journal 源版本。本页面不会读取 Journal 正文或自行计算/伪造引用。',
    summary: '简报正文（由你编写并确认）', summaryPlaceholder: '仅填写基于下方已选来源的内容；不会调用模型。',
    categories: '分类（逗号分隔）', categoriesPlaceholder: '今日任务', prepare: '预览并确认',
    confirmationTitle: '确认要保存这份简报？', confirmationBody: '这是你手动编写的文本；只有点击下面的确认按钮后，页面才会提交一次保存请求。',
    confirm: '确认并创建简报', submitting: '正在保存…', retry: '用同一请求安全重试',
    saved: '简报已保存。正在重新读取 Core 当前状态。', duplicate: '这项操作此前已保存；没有创建第二条简报。',
    noSources: '当前没有可核验的任务或项目来源。', loadFailed: '来源读取失败；没有提交简报。',
    invalid: '请至少选择一个可核验来源，并填写正文。',
    conflict: 'Core 检测到同日或同幂等键冲突。请刷新简报状态；没有覆盖已有记录。',
    auth: '登录或写入权限已失效。请重新登录；本次没有被确认保存。',
    invalidRequest: '请求未通过 Core 校验。请重新检查来源与内容。',
    unavailable: 'Core 暂不可用。结果尚未确认；可用同一请求安全重试。',
    unknown: '暂时无法确认保存结果。请用同一请求安全重试，勿修改内容。',
  },
  en: {
    start: 'Prepare a brief manually', cancel: 'Cancel', loading: 'Loading verifiable Tasks and Projects…',
    title: 'Create a daily brief manually', sourceHeading: 'Select sources for this brief',
    journalBlocked: 'Journal is unavailable as a source: Core does not expose a verifiable Journal source version. This page will not read Journal text or invent a reference.',
    summary: 'Brief text (written and confirmed by you)', summaryPlaceholder: 'Use only the selected sources. No model is called.',
    categories: 'Categories (comma-separated)', categoriesPlaceholder: 'Today’s tasks', prepare: 'Review and confirm',
    confirmationTitle: 'Save this brief?', confirmationBody: 'You wrote this text. The page sends one save request only after you confirm below.',
    confirm: 'Confirm and create brief', submitting: 'Saving…', retry: 'Retry the same request safely',
    saved: 'Brief saved. Reloading the current Core state.', duplicate: 'This operation was already saved; no second brief was created.',
    noSources: 'No verifiable Task or Project sources are available.', loadFailed: 'Could not read sources; no brief was submitted.',
    invalid: 'Select at least one verifiable source and enter the brief text.',
    conflict: 'Core reported a same-day or idempotency conflict. Refresh the brief state; no record was overwritten.',
    auth: 'Sign-in or write permission expired. Sign in again; this save was not confirmed.',
    invalidRequest: 'Core rejected the request. Review the sources and text.',
    unavailable: 'Core is unavailable. The result is unconfirmed; retry with the same request.',
    unknown: 'The save result is unconfirmed. Retry the same request without changing its contents.',
  },
} as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function shanghaiDate(now = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}

async function taskReference(task: Record<string, unknown>): Promise<SourceRef | null> {
  const keys = ['created_at', 'due_date', 'id', 'source', 'status', 'title', 'updated_at'];
  if (keys.some((key) => !Object.hasOwn(task, key))) return null;
  if (typeof task.id !== 'string' || !/^[0-9a-f]{32}$/.test(task.id)
    || typeof task.title !== 'string' || !task.title.trim()
    || (task.due_date !== null && typeof task.due_date !== 'string')
    || (task.status !== 'open' && task.status !== 'completed')
    || task.source !== 'web_app_explicit_task'
    || typeof task.created_at !== 'string' || typeof task.updated_at !== 'string') return null;
  const canonical = JSON.stringify(Object.fromEntries(keys.map((key) => [key, task[key]])));
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical));
  const version = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
  return { kind: 'task', id: task.id, version };
}

function parseReceipt(value: unknown, expectedDate: string): WriteReceipt | null {
  const keys = ['status', 'brief_id', 'date', 'timezone', 'record_version', 'operation_id'];
  if (!isRecord(value) || Object.keys(value).length !== keys.length || Object.keys(value).some((key) => !keys.includes(key))
    || (value.status !== 'created' && value.status !== 'duplicate')
    || typeof value.brief_id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value.brief_id)
    || value.date !== expectedDate || value.timezone !== 'Asia/Shanghai'
    || typeof value.record_version !== 'string' || !/^[a-f0-9]{64}$/.test(value.record_version)
    || typeof value.operation_id !== 'string' || !/^dbi-[a-f0-9]{64}$/.test(value.operation_id)) return null;
  return value as WriteReceipt;
}

async function loadSources(): Promise<SourceChoice[]> {
  const [taskResponse, projectResponse] = await Promise.all([
    fetch('/api/tasks?status=all', { credentials: 'same-origin', headers: { Accept: 'application/json' } }),
    fetch('/api/projects?limit=50&offset=0', { credentials: 'same-origin', headers: { Accept: 'application/json' } }),
  ]);
  if (!taskResponse.ok || !projectResponse.ok) throw new Error('source_read_failed');
  const [taskPayload, projectPayload] = await Promise.all([taskResponse.json(), projectResponse.json()]);
  if (!isRecord(taskPayload) || !Array.isArray(taskPayload.tasks) || taskPayload.tasks.length > 200) throw new Error('source_read_failed');
  const projects = parseProjectsResponse(projectPayload, 50, 0);
  if (!projects || projects.pagination.has_more || !['real', 'empty'].includes(projects.status)) throw new Error('source_read_failed');
  const tasks: SourceChoice[] = [];
  for (const item of taskPayload.tasks) {
    if (!isRecord(item)) continue;
    const ref = await taskReference(item);
    if (ref) tasks.push({ key: `${ref.kind}:${ref.id}`, label: item.title as string, ref });
  }
  const projectChoices = projects.items.map((project: ProjectRecord) => ({
    key: `project:${project.id}`, label: project.title,
    ref: { kind: 'project' as const, id: project.source_ref.id, version: project.source_ref.version },
  }));
  return [...tasks, ...projectChoices];
}

export function DailyBriefApproval({ locale, onSaved }: { locale: Locale; onSaved: () => void }) {
  const copy = text[locale];
  const [phase, setPhase] = useState<Phase>('idle');
  const [sources, setSources] = useState<SourceChoice[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [summary, setSummary] = useState('');
  const [categories, setCategories] = useState('');
  const [error, setError] = useState('');
  const [receipt, setReceipt] = useState<WriteReceipt | null>(null);
  const [requestKey, setRequestKey] = useState('');
  const [savedRequest, setSavedRequest] = useState<Record<string, unknown> | null>(null);
  const submitting = useRef(false);
  const currentDate = useMemo(() => shanghaiDate(), []);

  async function begin() {
    setPhase('loading-sources'); setError(''); setReceipt(null); setSelected([]); setRequestKey(''); setSavedRequest(null);
    try { const values = await loadSources(); setSources(values); setPhase('editing'); }
    catch { setError(copy.loadFailed); setPhase('idle'); }
  }

  function updateSummary(value: string) { setSummary(value); setRequestKey(''); setSavedRequest(null); }
  function updateCategories(value: string) { setCategories(value); setRequestKey(''); setSavedRequest(null); }
  function toggleSource(key: string) {
    setSelected((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key]);
    setRequestKey(''); setSavedRequest(null);
  }

  function confirmDraft() {
    if (!summary.trim() || summary.length > 20000 || selected.length < 1 || selected.length > 50) { setError(copy.invalid); return; }
    const categoryList = categories.split(',').map((item) => item.trim()).filter(Boolean);
    if (categoryList.length > 30 || categoryList.some((item) => item.length > 80)) { setError(copy.invalid); return; }
    setError(''); setPhase('confirming');
  }

  async function submit() {
    if (submitting.current) return;
    submitting.current = true;
    const refs = sources.filter((source) => selected.includes(source.key)).map((source) => source.ref);
    if (!requestKey) setRequestKey(`ui-${crypto.randomUUID()}`);
    const key = requestKey || `ui-${crypto.randomUUID()}`;
    const body = savedRequest ?? {
      mode: 'manual_generate', date: currentDate, timezone: 'Asia/Shanghai', idempotency_key: key,
      categories: categories.split(',').map((item) => item.trim()).filter(Boolean),
      summary, source_refs: refs, approved: true,
    };
    setSavedRequest(body); setPhase('submitting'); setError('');
    try {
      const response = await fetch('/api/daily-brief', {
        method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (response.status === 401 || response.status === 403) { submitting.current = false; setError(copy.auth); setPhase('editing'); return; }
      if (response.status === 409) { submitting.current = false; setError(copy.conflict); setPhase('editing'); return; }
      if (response.status === 422) { submitting.current = false; setError(copy.invalidRequest); setPhase('editing'); return; }
      if (!response.ok) { submitting.current = false; setError(response.status === 503 ? copy.unavailable : copy.unknown); setPhase('unknown'); return; }
      const parsed = parseReceipt(await response.json(), currentDate);
      if (!parsed) { submitting.current = false; setError(copy.unknown); setPhase('unknown'); return; }
      setReceipt(parsed); setPhase('done'); onSaved();
    } catch { submitting.current = false; setError(copy.unknown); setPhase('unknown'); }
  }

  return <section className="daily-brief-approval" aria-label={copy.title}>
    {phase === 'idle' && <button type="button" onClick={() => void begin()}>{copy.start}</button>}
    {phase === 'loading-sources' && <p role="status">{copy.loading}</p>}
    {phase !== 'idle' && phase !== 'loading-sources' && phase !== 'done' && <>
      <h2>{copy.title}</h2>
      <button type="button" onClick={() => { setPhase('idle'); setError(''); }} disabled={phase === 'submitting'}>{copy.cancel}</button>
      {phase === 'editing' && <>
        <h3>{copy.sourceHeading}</h3>
        {sources.length === 0 && <p role="status">{copy.noSources}</p>}
        {sources.map((source) => <label key={source.key}>
          <input type="checkbox" checked={selected.includes(source.key)} onChange={() => toggleSource(source.key)} />
          {source.ref.kind === 'task' ? 'Task' : 'Project'} · {source.label}
        </label>)}
        <p>{copy.journalBlocked}</p>
        <label>{copy.summary}<textarea value={summary} maxLength={20000} onChange={(event) => updateSummary(event.target.value)} placeholder={copy.summaryPlaceholder} /></label>
        <label>{copy.categories}<input value={categories} onChange={(event) => updateCategories(event.target.value)} placeholder={copy.categoriesPlaceholder} /></label>
        <button type="button" onClick={confirmDraft}>{copy.prepare}</button>
      </>}
      {phase === 'confirming' && <>
        <h3>{copy.confirmationTitle}</h3><p>{copy.confirmationBody}</p>
        <p><strong>{summary}</strong></p>
        <p>{selected.map((key) => sources.find((source) => source.key === key)?.label).filter(Boolean).join(' · ')}</p>
        <button type="button" onClick={() => void submit()}>{copy.confirm}</button>
      </>}
      {phase === 'submitting' && <p role="status">{copy.submitting}</p>}
      {phase === 'unknown' && <button type="button" onClick={() => void submit()}>{copy.retry}</button>}
      {error && <p role="alert">{error}</p>}
    </>}
    {phase === 'done' && receipt && <p role="status">{receipt.status === 'duplicate' ? copy.duplicate : copy.saved}</p>}
  </section>;
}
