import React, { useEffect, useMemo, useRef, useState } from 'react';

type Locale = 'zh-CN' | 'en';
type RefKind = 'task' | 'project' | 'journal';
type SourceRef = { kind: RefKind; id: string; version: string };
type SourceChoice = { ref: SourceRef; label: string; detail: string };
type Step = { position: number; kind: 'review_source'; source_ref: SourceRef; reason: string; priority: 'unspecified'; depends_on: []; decision: 'pending' | 'approved' | 'rejected'; execution_status: 'not_started' | 'simulated' | 'failed' | 'retry_ready' };
type Candidate = { session_id: string; candidate_id: string; revision: number; expires_at: string; status: 'ready' | 'needs_review' | 'stale' | 'unavailable'; workflow_status: 'active' | 'paused' | 'cancelled' | 'partial' | 'completed'; objective: string; steps: Step[] };
type Retrospective = { revision: number; workflow_status: Candidate['workflow_status']; counts: { planned: number; approved: number; rejected: number; completed: number; failed: number; stale_sources: number }; steps: Array<{ position: number; source_state: 'verified' | 'stale' | 'unavailable'; decision: string; execution_status: string }>; feedback: 'useful' | 'not_useful' | null };
type CalendarWindow = { from: string; to: string; timezone: string };

const candidatePattern = /^[a-f0-9]{32}$/;
const shaPattern = /^[a-f0-9]{64}$/;

function record(value: unknown): value is Record<string, unknown> { return Boolean(value) && typeof value === 'object' && !Array.isArray(value); }
function integer(value: unknown, min = 0): value is number { return Number.isSafeInteger(value) && (value as number) >= min; }
function validRef(value: unknown): value is SourceRef {
  if (!record(value) || Object.keys(value).sort().join(',') !== 'id,kind,version'
    || (value.kind !== 'task' && value.kind !== 'project' && value.kind !== 'journal')
    || typeof value.id !== 'string' || typeof value.version !== 'string' || !shaPattern.test(value.version)) return false;
  if (value.kind === 'task') return /^[a-f0-9]{32}$/.test(value.id);
  if (value.kind === 'project') return /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value.id);
  return /^\d{4}-\d{2}-\d{2}:[a-f0-9]{64}$/.test(value.id);
}

function parseCandidate(value: unknown, sessionId: string, candidateId?: string): Candidate | null {
  if (!record(value) || value.event !== 'planning.preview' && value.event !== 'planning.candidate'
    || value.version !== 1 || value.session_id !== sessionId
    || typeof value.candidate_id !== 'string' || !candidatePattern.test(value.candidate_id)
    || (candidateId && value.candidate_id !== candidateId) || !integer(value.revision)
    || typeof value.expires_at !== 'string' || !Number.isFinite(Date.parse(value.expires_at))
    || !['ready', 'needs_review', 'stale', 'unavailable'].includes(String(value.status))
    || !['active', 'paused', 'cancelled', 'partial', 'completed'].includes(String(value.workflow_status))
    || typeof value.objective !== 'string' || !Array.isArray(value.steps) || value.steps.length > 20) return null;
  const steps: Step[] = [];
  for (const raw of value.steps) {
    if (!record(raw) || !integer(raw.position, 1) || raw.kind !== 'review_source' || !validRef(raw.source_ref)
      || typeof raw.reason !== 'string' || raw.priority !== 'unspecified' || !Array.isArray(raw.depends_on)
      || raw.depends_on.length !== 0 || !['pending', 'approved', 'rejected'].includes(String(raw.decision))
      || !['not_started', 'simulated', 'failed', 'retry_ready'].includes(String(raw.execution_status))) return null;
    steps.push(raw as unknown as Step);
  }
  if (steps.some((step, index) => step.position !== index + 1)) return null;
  return { session_id: sessionId, candidate_id: value.candidate_id, revision: value.revision,
    expires_at: value.expires_at, status: value.status as Candidate['status'],
    workflow_status: value.workflow_status as Candidate['workflow_status'], objective: value.objective, steps };
}

function parseRetrospective(value: unknown, sessionId: string, candidateId: string): Retrospective | null {
  if (!record(value) || value.event !== 'planning.retrospective' || value.version !== 1
    || value.session_id !== sessionId || value.candidate_id !== candidateId || !integer(value.revision)
    || !['active', 'paused', 'cancelled', 'partial', 'completed'].includes(String(value.workflow_status))
    || !record(value.counts) || !Array.isArray(value.steps)
    || !['useful', 'not_useful', null].includes(value.feedback as string | null)) return null;
  const counts = value.counts as Record<string, unknown>;
  const countKeys = ['planned', 'approved', 'rejected', 'completed', 'failed', 'stale_sources'] as const;
  if (countKeys.some((key) => !integer(counts[key]))) return null;
  if (value.steps.some((step) => !record(step) || !integer(step.position, 1)
    || !['verified', 'stale', 'unavailable'].includes(String(step.source_state)))) return null;
  return value as unknown as Retrospective;
}

function parseChoices(kind: RefKind, value: unknown): SourceChoice[] {
  if (kind === 'task') {
    if (!record(value) || !Array.isArray(value.tasks) || value.tasks.length > 1000) throw new Error('Task sources are unavailable.');
    return value.tasks.flatMap((task): SourceChoice[] => {
      if (!record(task) || !record(task.source_ref) || typeof task.source_ref.id !== 'string' || typeof task.source_ref.version !== 'string' || typeof task.title !== 'string'
        || !validRef({ kind: 'task', id: task.source_ref.id, version: task.source_ref.version })) return [];
      return [{ ref: { kind: 'task', id: task.source_ref.id, version: task.source_ref.version }, label: task.title,
        detail: `${String(task.status ?? '')}${task.due_date ? ` · ${String(task.due_date)}` : ''}` }];
    });
  }
  if (kind === 'project') {
    if (!record(value) || !Array.isArray(value.items) || value.items.length > 100) throw new Error('Project sources are unavailable.');
    if (value.status !== 'real' && value.status !== 'empty') throw new Error('Project sources are incomplete or unavailable.');
    return value.items.flatMap((project): SourceChoice[] => {
      if (!record(project) || !record(project.source_ref) || typeof project.source_ref.id !== 'string' || typeof project.source_ref.version !== 'string' || typeof project.title !== 'string'
        || !validRef({ kind: 'project', id: project.source_ref.id, version: project.source_ref.version })) return [];
      return [{ ref: { kind: 'project', id: project.source_ref.id, version: project.source_ref.version }, label: project.title,
        detail: String(project.status ?? '') }];
    });
  }
  if (!record(value) || !Array.isArray(value.items) || !['real', 'empty'].includes(String(value.status))) throw new Error('Journal source options are unavailable.');
  return value.items.flatMap((item): SourceChoice[] => {
    const ref = item && record(item) ? { kind: 'journal', id: item.id, version: item.version } : null;
    if (!ref || !validRef(ref) || typeof item.date !== 'string') return [];
    return [{ ref, label: item.date, detail: `${item.id.slice(-12)}` }];
  });
}

function statusText(status: Candidate['status'], en: boolean) {
  return ({ ready: en ? 'Ready for your review' : '来源已核验，等待你审核', needs_review: en ? 'Needs additional review' : '需要额外审核',
    stale: en ? 'Sources changed; no steps are actionable' : '来源已变化，步骤不可操作', unavailable: en ? 'Sources unavailable' : '来源不可用' })[status];
}

function validCalendarWindow(from: string, to: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(from) || !/^\d{4}-\d{2}-\d{2}$/.test(to)) return false;
  const start = new Date(`${from}T00:00:00Z`);
  const end = new Date(`${to}T00:00:00Z`);
  if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime())
    || start.toISOString().slice(0, 10) !== from || end.toISOString().slice(0, 10) !== to) return false;
  const days = (end.getTime() - start.getTime()) / 86_400_000;
  return days >= 0 && days < 31 && from.slice(0, 7) === to.slice(0, 7);
}

export function PlanningPanel({ locale, sessionId }: { locale: Locale; sessionId: string }) {
  const en = locale === 'en';
  const [open, setOpen] = useState(false);
  const [loadingSources, setLoadingSources] = useState(false);
  const [sourcesLoaded, setSourcesLoaded] = useState(false);
  const [sourceError, setSourceError] = useState('');
  const [objective, setObjective] = useState('');
  const [tasks, setTasks] = useState<SourceChoice[]>([]);
  const [projects, setProjects] = useState<SourceChoice[]>([]);
  const [journals, setJournals] = useState<SourceChoice[]>([]);
  const [journalDay, setJournalDay] = useState(new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date()));
  const [selectedRefs, setSelectedRefs] = useState<SourceRef[]>([]);
  const [includeCalendar, setIncludeCalendar] = useState(false);
  const [windowFrom, setWindowFrom] = useState('');
  const [windowTo, setWindowTo] = useState('');
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [retrospective, setRetrospective] = useState<Retrospective | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [storageWarning, setStorageWarning] = useState(false);
  const sequence = useRef(0);
  const sessionRef = useRef(sessionId);
  sessionRef.current = sessionId;
  const locatorKey = `secondbrain.planning.candidate:${sessionId}`;
  const selectedKeys = useMemo(() => new Set(selectedRefs.map((ref) => `${ref.kind}:${ref.id}`)), [selectedRefs]);

  const api = async (path: string, init?: RequestInit) => {
    const response = await fetch(path, { ...init, credentials: 'same-origin', cache: 'no-store', headers: {
      ...(init?.headers ?? {}), ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
    } });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) { const failure = new Error(String((body as Record<string, unknown>).detail ?? `HTTP ${response.status}`)) as Error & { status?: number }; failure.status = response.status; throw failure; }
    return body as unknown;
  };

  const refreshCandidate = async (id: string, currentSequence = sequence.current) => {
    const value = await api(`/api/chat/sessions/${encodeURIComponent(sessionId)}/planning/candidates/${encodeURIComponent(id)}`);
    if (currentSequence !== sequence.current || sessionRef.current !== sessionId) return;
    const parsed = parseCandidate(value, sessionId, id);
    if (!parsed) throw new Error(en ? 'Core returned an invalid planning preview.' : 'Core 返回的计划预览无法核验。');
    setCandidate(parsed); setError('');
    try { sessionStorage.setItem(locatorKey, id); setStorageWarning(false); } catch { setStorageWarning(true); }
    try {
      const recap = parseRetrospective(await api(`/api/chat/sessions/${encodeURIComponent(sessionId)}/planning/candidates/${encodeURIComponent(id)}/retrospective`), sessionId, id);
      if (currentSequence === sequence.current && sessionRef.current === sessionId && recap) setRetrospective(recap);
    } catch { /* Preview remains authoritative for actions; retrospective is a separate read-only projection. */ }
  };

  const openPanel = async () => {
    setOpen(true); setError(''); setNotice('');
    const id = (() => { try { return sessionStorage.getItem(locatorKey) ?? ''; } catch { return ''; } })();
    if (!candidate && candidatePattern.test(id)) {
      const currentSequence = ++sequence.current;
      setBusy(true);
      try { await refreshCandidate(id, currentSequence); }
      catch (cause) { if (currentSequence === sequence.current) setError(cause instanceof Error ? cause.message : 'Planning history is unavailable.'); }
      finally { if (currentSequence === sequence.current) setBusy(false); }
    }
  };

  useEffect(() => () => { sequence.current += 1; }, []);

  const loadSources = async () => {
    if (loadingSources || !sessionId) return;
    setLoadingSources(true); setSourceError(''); setSourcesLoaded(false); setTasks([]); setProjects([]);
    setSelectedRefs((current) => current.filter((ref) => ref.kind === 'journal'));
    try {
      const [taskValue, projectValue] = await Promise.all([
        api('/api/tasks?status=all'), api('/api/projects?limit=50&offset=0'),
      ]);
      const taskChoices = parseChoices('task', taskValue);
      const projectChoices = parseChoices('project', projectValue);
      if (sessionRef.current !== sessionId) return;
      setTasks(taskChoices); setProjects(projectChoices); setSourcesLoaded(true);
    } catch (cause) { setSourceError(cause instanceof Error ? cause.message : 'Sources could not be loaded.'); }
    finally { setLoadingSources(false); }
  };

  const loadJournals = async () => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(journalDay)) { setSourceError(en ? 'Choose a valid Journal date.' : '请选择有效的 Journal 日期。'); return; }
    setLoadingSources(true); setSourceError(''); setJournals([]);
    setSelectedRefs((current) => current.filter((ref) => ref.kind !== 'journal'));
    try {
      const params = new URLSearchParams({ date: journalDay, limit: '50' });
      const value = await api(`/api/daily-brief/source-options/journal?${params}`);
      const choices = parseChoices('journal', value);
      if (sessionRef.current === sessionId) setJournals(choices);
    } catch (cause) { setSourceError(cause instanceof Error ? cause.message : 'Journal sources could not be loaded.'); }
    finally { setLoadingSources(false); }
  };

  const toggleRef = (ref: SourceRef) => {
    const key = `${ref.kind}:${ref.id}`;
    setSelectedRefs((current) => current.some((item) => `${item.kind}:${item.id}` === key)
      ? current.filter((item) => `${item.kind}:${item.id}` !== key)
      : current.length >= 20 ? current : [...current, ref]);
  };

  const createCandidate = async () => {
    if (busy || !objective.trim() || selectedRefs.length < 1 || selectedRefs.length > 20) return;
    if (new TextEncoder().encode(objective.trim()).length > 500) { setError(en ? 'Objective must be at most 500 UTF-8 bytes.' : '计划目标不能超过 500 个 UTF-8 字节。'); return; }
    if (includeCalendar && !validCalendarWindow(windowFrom, windowTo)) {
      setError(en ? 'Choose valid dates in one month, with at most 31 days.' : '日期必须有效、属于同一月份且不超过 31 天。'); return;
    }
    setBusy(true); setError(''); setNotice(''); setCandidate(null); setRetrospective(null);
    const currentSequence = ++sequence.current;
    try {
      const calendarWindow: CalendarWindow | null = includeCalendar
        ? { from: windowFrom, to: windowTo, timezone: 'Asia/Shanghai' } : null;
      const value = await api(`/api/chat/sessions/${encodeURIComponent(sessionId)}/planning/candidates`, {
        method: 'POST', body: JSON.stringify({ objective: objective.trim(), source_refs: selectedRefs, calendar_window: calendarWindow }),
      });
      if (currentSequence !== sequence.current || sessionRef.current !== sessionId) return;
      const parsed = parseCandidate(value, sessionId);
      if (!parsed) throw new Error(en ? 'Core returned an invalid planning candidate.' : 'Core 返回的计划候选无法核验。');
      setCandidate(parsed);
      try { sessionStorage.setItem(locatorKey, parsed.candidate_id); setStorageWarning(false); } catch { setStorageWarning(true); }
      setNotice(parsed.status === 'ready' ? (en ? 'Created; this candidate still requires your review.' : '候选已创建，仍需你逐项审核。') : statusText(parsed.status, en));
      try { await refreshCandidate(parsed.candidate_id, currentSequence); }
      catch { setNotice(en ? 'Candidate creation was confirmed. Refresh the preview before taking another action.' : '候选创建已由 Core 确认；请刷新预览后再继续操作。'); }
    } catch (cause) { if (currentSequence === sequence.current) setError(cause instanceof Error ? cause.message : 'Planning candidate could not be created.'); }
    finally { if (currentSequence === sequence.current) setBusy(false); }
  };

  const mutate = async (operation: string, position: number, path: string, body: Record<string, unknown>, validate: (value: unknown) => boolean) => {
    const current = candidate;
    if (!current || busy) return;
    setBusy(true); setError(''); setNotice('');
    const currentSequence = ++sequence.current;
    const fullPath = `/api/chat/sessions/${encodeURIComponent(sessionId)}/planning/candidates/${encodeURIComponent(current.candidate_id)}${path}`;
    const intent = JSON.stringify({ path: fullPath, body });
    const pendingKey = `${locatorKey}:pending:${operation}:${position}`;
    let idem = '';
    try {
      const saved = (() => { try { return sessionStorage.getItem(pendingKey); } catch { return null; } })();
      const parsed = saved ? JSON.parse(saved) as Record<string, unknown> : null;
      if (parsed?.intent === intent && typeof parsed.key === 'string') idem = parsed.key;
      if (!idem) {
        idem = crypto.randomUUID().replaceAll('-', '');
        try { sessionStorage.setItem(pendingKey, JSON.stringify({ intent, key: idem })); }
        catch { throw new Error(en ? 'This tab cannot safely retain the retry key; no request was sent.' : '当前标签页无法安全保存重试键，本次没有发送请求。'); }
      }
      const value = await api(fullPath, { method: 'POST', headers: { 'Idempotency-Key': idem }, body: JSON.stringify(body) });
      if (currentSequence !== sequence.current || sessionRef.current !== sessionId) return;
      if (!validate(value)) throw new Error(en ? 'Core returned an invalid planning receipt.' : 'Core 返回的计划回执无法核验。');
      try { sessionStorage.removeItem(pendingKey); } catch { /* Saved key remains harmless; exact replay is safe. */ }
      setNotice(en ? 'Core recorded the exact synthetic workflow action.' : 'Core 已记录该合成工作流操作。');
      try { await refreshCandidate(current.candidate_id, currentSequence); }
      catch { setNotice(en ? 'Core confirmed the action. The latest preview could not be refreshed; refresh it before continuing.' : 'Core 已确认该操作，但最新预览刷新失败；请先手动刷新预览再继续。'); }
    } catch (cause) {
      if (currentSequence !== sequence.current) return;
      const status = (cause as Error & { status?: number }).status;
      if (status === 409) {
        try { await refreshCandidate(current.candidate_id, currentSequence); } catch { /* Keep the original conflict visible. */ }
        setError(en ? 'The candidate changed or its source versions are stale. The latest preview was refreshed; review it before continuing.' : '候选版本或来源已变化。已刷新最新预览，请检查后再继续。');
      } else setError(cause instanceof Error ? cause.message : 'Planning action failed; retry the same action if its result is unknown.');
    } finally { if (currentSequence === sequence.current) setBusy(false); }
  };

  const decide = (step: Step, decision: 'approved' | 'rejected') => {
    if (!candidate) return;
    const body = { decision, expected_revision: candidate.revision };
    const path = `/steps/${step.position}/decision`;
    void mutate(`decision-${decision}`, step.position, path, body, (value) => record(value)
      && value.event === 'planning.step-decision' && value.version === 1 && value.session_id === sessionId
      && value.candidate_id === candidate.candidate_id && value.revision === candidate.revision + 1
      && value.position === step.position && value.decision === decision && value.execution_status === 'not_started');
  };

  const execute = (step: Step) => {
    if (!candidate) return;
    const body = { expected_revision: candidate.revision };
    void mutate('execute', step.position, `/steps/${step.position}/execute`, body, (value) => record(value)
      && value.event === 'planning.step-execution' && value.version === 1 && value.session_id === sessionId
      && value.candidate_id === candidate.candidate_id && value.revision === candidate.revision + 1
      && value.position === step.position && value.execution_mode === 'synthetic' && value.effect === 'none'
      && ['simulated', 'failed'].includes(String(value.status)));
  };

  const control = (command: 'pause' | 'resume' | 'cancel' | 'retry') => {
    if (!candidate) return;
    const body = { command, expected_revision: candidate.revision };
    void mutate(`control-${command}`, 0, '/control', body, (value) => record(value)
      && value.event === 'planning.workflow-control' && value.version === 1 && value.session_id === sessionId
      && value.candidate_id === candidate.candidate_id && value.revision === candidate.revision + 1
      && value.command === command && Array.isArray(value.steps));
  };

  const submitFeedback = (rating: 'useful' | 'not_useful') => {
    if (!candidate) return;
    const body = { rating, expected_revision: candidate.revision };
    void mutate(`feedback-${rating}`, 0, '/retrospective/feedback', body, (value) => record(value)
      && value.event === 'planning.feedback' && value.version === 1 && value.session_id === sessionId
      && value.candidate_id === candidate.candidate_id && value.revision === candidate.revision + 1 && value.rating === rating);
  };

  if (!sessionId) return null;
  return <section className="chat-context-preview planning-panel" aria-label={en ? 'Planning' : '规划'}>
    <div className="chat-context-preview-heading"><h3>{en ? 'Plan with selected sources' : '基于所选来源制定计划'}</h3>
      <button type="button" onClick={() => { if (open) { setOpen(false); return; } void openPanel(); }} disabled={busy}>{open ? (en ? 'Hide planning' : '收起计划') : (en ? 'Open planning' : '开始规划')}</button></div>
    {!open && <p>{en ? 'No sources are read until you open this panel and explicitly load choices.' : '只有展开面板并显式加载候选来源后才读取来源列表。'}</p>}
    {open && <>
      <p className="chat-context-preview-note">{en ? 'Sources are rechecked by Core. Approval and synthetic execution are separate explicit actions. Synthetic execution has effect=none and never writes business records.' : 'Core 会重新核验来源。逐项批准与合成执行是分开的显式操作；合成执行 effect=none，不写入业务记录。'}</p>
      {storageWarning && <p role="alert">{en ? 'This tab cannot retain the candidate locator. Keep this tab open to review it.' : '当前标签页无法保存候选定位符，请保持本标签页打开。'}</p>}
      {!candidate && <>
        <label htmlFor="planning-objective">{en ? 'Objective' : '计划目标'}</label>
        <textarea id="planning-objective" value={objective} onChange={(event) => setObjective(event.target.value)} maxLength={500} placeholder={en ? 'Describe what you want to review' : '描述你希望规划或复盘的目标'} />
        <button type="button" disabled={loadingSources} onClick={() => void loadSources()}>{loadingSources ? (en ? 'Loading…' : '正在读取…') : (sourcesLoaded ? (en ? 'Refresh Task and Project choices' : '刷新待办和项目候选') : (en ? 'Load Task and Project choices' : '读取待办和项目候选'))}</button>
        {sourcesLoaded && <div className="planning-source-groups">
          {([["task", tasks], ["project", projects]] as Array<[RefKind, SourceChoice[]]>).map(([kind, choices]) => <fieldset key={kind} disabled={busy}>
            <legend>{kind === 'task' ? (en ? 'Tasks' : '待办') : (en ? 'Projects' : '项目')}</legend>
            {!choices.length && <p>{en ? 'No selectable sources.' : '没有可选来源。'}</p>}
          {choices.map((choice) => { const key = `${choice.ref.kind}:${choice.ref.id}`; return <label key={key}>
              <input type="checkbox" checked={selectedKeys.has(key)} onChange={() => toggleRef(choice.ref)} />
              <span>{choice.label}<small>{choice.detail}</small></span>
            </label>; })}
          </fieldset>)}
          <fieldset disabled={busy || loadingSources}>
            <legend>{en ? 'Journal' : '日记'}</legend>
            <label>{en ? 'Date' : '日期'}<input type="date" value={journalDay} onChange={(event) => setJournalDay(event.target.value)} /></label>
            <button type="button" disabled={loadingSources} onClick={() => void loadJournals()}>{journals.length ? (en ? 'Refresh approved Journal source refs' : '刷新获准 Journal 来源') : (en ? 'Load approved Journal source refs' : '读取获准 Journal 来源')}</button>
            {!journals.length && <p>{en ? 'Journal choices are not loaded.' : '尚未读取 Journal 候选。'}</p>}
            {journals.map((choice) => { const key = `${choice.ref.kind}:${choice.ref.id}`; return <label key={key}>
              <input type="checkbox" checked={selectedKeys.has(key)} onChange={() => toggleRef(choice.ref)} />
              <span>{choice.label}<small>{choice.detail}</small></span>
            </label>; })}
          </fieldset>
        </div>}
        <label className="planning-calendar-choice"><input type="checkbox" checked={includeCalendar} onChange={(event) => setIncludeCalendar(event.target.checked)} />{en ? 'Include a bounded Calendar window' : '加入有界 Calendar 日期范围'}</label>
        {includeCalendar && <div className="planning-calendar-dates"><label>{en ? 'From' : '开始'}<input type="date" value={windowFrom} onChange={(event) => setWindowFrom(event.target.value)} /></label><label>{en ? 'To' : '结束'}<input type="date" value={windowTo} onChange={(event) => setWindowTo(event.target.value)} /></label><small>{en ? 'At most 31 days within one calendar month.' : '最多 31 天，且必须在同一月份。'}</small></div>}
        <p>{selectedRefs.length}/20 {en ? 'selected source refs' : '个来源已选择'}</p>
        {sourceError && <p role="alert">{sourceError}</p>}
        <button type="button" disabled={busy || !sourcesLoaded || !objective.trim() || selectedRefs.length === 0 || (includeCalendar && (!windowFrom || !windowTo))} onClick={() => void createCandidate()}>{en ? 'Create review candidate' : '创建待审核计划'}</button>
      </>}
      {candidate && <>
        <p role="status">{statusText(candidate.status, en)} · {candidate.workflow_status} · revision {candidate.revision}</p>
        <p>{candidate.objective}</p>
        <p>{en ? 'Expires' : '过期时间'}: {candidate.expires_at}</p>
        {!candidate.steps.length && <p>{en ? 'Core returned no actionable steps.' : 'Core 未返回可操作步骤。'}</p>}
        <ol className="planning-step-list">{candidate.steps.map((step) => <li key={step.position}>
          <strong>{step.reason.replaceAll('_', ' ')}</strong>
          <small>{step.source_ref.kind} · {step.source_ref.id} · v{step.source_ref.version.slice(0, 12)}…</small>
          <span>{step.decision} · {step.execution_status}</span>
          {step.decision === 'pending' && candidate.status !== 'stale' && candidate.status !== 'unavailable' && candidate.workflow_status === 'active' && <div>
            <button type="button" disabled={busy} onClick={() => decide(step, 'approved')}>{en ? 'Approve this step' : '批准此步骤'}</button>
            <button type="button" disabled={busy} onClick={() => decide(step, 'rejected')}>{en ? 'Reject this step' : '拒绝此步骤'}</button>
          </div>}
          {step.decision === 'approved' && ['not_started', 'retry_ready'].includes(step.execution_status)
            && candidate.workflow_status === 'active' && <button type="button" disabled={busy} onClick={() => execute(step)}>{en ? 'Run synthetic check (effect=none)' : '执行合成检查（effect=none）'}</button>}
        </li>)}</ol>
        <div className="planning-workflow-controls">
          {candidate.workflow_status === 'active' && <button type="button" disabled={busy} onClick={() => control('pause')}>{en ? 'Pause' : '暂停'}</button>}
          {candidate.workflow_status === 'paused' && <button type="button" disabled={busy} onClick={() => control('resume')}>{en ? 'Resume' : '恢复'}</button>}
          {['active', 'paused', 'partial'].includes(candidate.workflow_status) && <button type="button" disabled={busy} onClick={() => control('cancel')}>{en ? 'Cancel' : '取消'}</button>}
          {candidate.workflow_status === 'partial' && candidate.steps.some((step) => step.execution_status === 'failed') && <button type="button" disabled={busy} onClick={() => control('retry')}>{en ? 'Mark failed step retry-ready' : '将失败步骤标为可重试'}</button>}
        </div>
        <button type="button" disabled={busy} onClick={() => { setBusy(true); const currentSequence = ++sequence.current; void refreshCandidate(candidate.candidate_id, currentSequence).catch((cause) => setError(cause instanceof Error ? cause.message : 'Refresh failed')).finally(() => { if (currentSequence === sequence.current) setBusy(false); }); }}>{en ? 'Refresh and recheck sources' : '刷新并复核来源'}</button>
        {retrospective && <section className="planning-retrospective" aria-label={en ? 'Planning retrospective' : '计划复盘'}>
          <h4>{en ? 'Retrospective' : '复盘'}</h4>
          <p>{en ? 'Read-only source status and recorded synthetic outcomes.' : '只读来源状态与已记录的合成结果。'}</p>
          <p>{en ? 'Planned' : '计划'} {retrospective.counts.planned} · {en ? 'Approved' : '已批准'} {retrospective.counts.approved} · {en ? 'Completed' : '完成'} {retrospective.counts.completed} · {en ? 'Failed' : '失败'} {retrospective.counts.failed} · {en ? 'Stale sources' : '失效来源'} {retrospective.counts.stale_sources}</p>
          {retrospective.feedback && <p>{en ? 'Your feedback' : '你的反馈'}: {retrospective.feedback}</p>}
          {!retrospective.feedback && <div><button type="button" disabled={busy} onClick={() => submitFeedback('useful')}>{en ? 'Useful' : '有帮助'}</button><button type="button" disabled={busy} onClick={() => submitFeedback('not_useful')}>{en ? 'Not useful' : '帮助不大'}</button></div>}
        </section>}
        <button type="button" disabled={busy} onClick={() => { setCandidate(null); setRetrospective(null); setError(''); }}>{en ? 'Start a different plan' : '新建另一计划'}</button>
      </>}
      {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}{busy && <p role="status">{en ? 'Checking with Core…' : '正在与 Core 核验…'}</p>}
    </>}
  </section>;
}
