import React, { useCallback, useEffect, useRef, useState } from 'react';
import { CompanionSuggestionsPanel } from './CompanionSuggestionsPanel';

type Task = {
  id: string; title: string; due_date: string | null; status: 'open' | 'completed';
  created_at: string; updated_at: string; source: string; original_command: string;
  history: { at: string; event: string; changes: Record<string, unknown> }[];
};
type Locale = 'zh-CN' | 'en';

type TaskCreateAttempt = { signature: string; key: string; title: string; dueDate: string };
const PENDING_CREATE_STORAGE_KEY = 'secondbrain.task.create.pending.v1';

function readPendingCreate(): TaskCreateAttempt | null {
  try {
    const raw = window.sessionStorage.getItem(PENDING_CREATE_STORAGE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<TaskCreateAttempt>;
    if (typeof value.key !== 'string' || !/^[0-9a-f-]{36}$/i.test(value.key)
      || typeof value.title !== 'string' || !value.title.trim()
      || typeof value.dueDate !== 'string'
      || typeof value.signature !== 'string'
      || value.signature !== JSON.stringify({ title: value.title, due_date: value.dueDate || null })) return null;
    return value as TaskCreateAttempt;
  } catch { return null; }
}

function storePendingCreate(attempt: TaskCreateAttempt) {
  try { window.sessionStorage.setItem(PENDING_CREATE_STORAGE_KEY, JSON.stringify(attempt)); } catch { /* Storage can be unavailable in restricted browser contexts. */ }
}

function clearPendingCreate(key: string) {
  try {
    const raw = window.sessionStorage.getItem(PENDING_CREATE_STORAGE_KEY);
    if (raw && (JSON.parse(raw) as Partial<TaskCreateAttempt>).key === key) window.sessionStorage.removeItem(PENDING_CREATE_STORAGE_KEY);
  } catch { /* Keep storage failures from changing the create result. */ }
}

export function TaskPage({ locale }: { locale: Locale }) {
  const en = locale === 'en';
  const requestedTaskId = new URLSearchParams(window.location.search).get('task_id');
  const targetTaskId = requestedTaskId && /^[0-9a-f]{32}$/i.test(requestedTaskId) ? requestedTaskId.toLowerCase() : null;
  const openCreateFromRoute = new URLSearchParams(window.location.search).get('create') === '1';
  const [initialAttempt] = useState(readPendingCreate);
  const [status, setStatus] = useState<'open' | 'completed' | 'all'>(targetTaskId ? 'all' : 'open');
  const [dueDate, setDueDate] = useState('');
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState('');
  const [editing, setEditing] = useState<{ id: string; title: string; due_date: string } | null>(null);
  const [createOpen, setCreateOpen] = useState(Boolean(initialAttempt) || openCreateFromRoute);
  const [newTitle, setNewTitle] = useState(initialAttempt?.title ?? '');
  const [newDueDate, setNewDueDate] = useState(initialAttempt?.dueDate ?? '');
  const [creating, setCreating] = useState(false);
  const [restoredAttempt, setRestoredAttempt] = useState(Boolean(initialAttempt));
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [showSuggestions, setShowSuggestions] = useState(false);
  const createAttempt = useRef<TaskCreateAttempt | null>(initialAttempt);
  const createInFlight = useRef(false);
  const mounted = useRef(false);
  const lifecycle = useRef(0);
  const confirmedCreates = useRef(new Map<string, Task>());
  const refreshAfterCreate = useRef(false);
  const activeLoad = useRef<AbortController | null>(null);
  const loadSequence = useRef(0);

  useEffect(() => {
    if (!openCreateFromRoute) return;
    const params = new URLSearchParams(window.location.search);
    params.delete('create');
    const search = params.toString();
    window.history.replaceState(window.history.state, '', `${window.location.pathname}${search ? `?${search}` : ''}${window.location.hash}`);
  }, [openCreateFromRoute]);

  const load = useCallback(async (showLoading = true, afterCreate = false) => {
    if (createInFlight.current && !afterCreate) return;
    activeLoad.current?.abort();
    const controller = new AbortController();
    activeLoad.current = controller;
    const sequence = ++loadSequence.current;
    if (showLoading) setLoading(true);
    setError('');
    if (showLoading) setTasks([]);
    try {
      const dateFilter = dueDate ? `&due_date=${encodeURIComponent(dueDate)}` : '';
      const response = await fetch(`/api/tasks?status=${status}${dateFilter}`, { credentials: 'same-origin', signal: controller.signal });
      const body = await response.json().catch(() => ({})) as { detail?: string; tasks?: Task[] };
      if (controller.signal.aborted || sequence !== loadSequence.current) return;
      if (!response.ok) {
        if (response.status === 401) window.location.reload();
        throw new Error(response.status === 503 && body.detail === 'Task is not enabled'
          ? (en ? 'Task storage is not enabled in this environment.' : '当前环境未启用 Task 存储。')
          : String(body.detail ?? `HTTP ${response.status}`));
      }
      if (!Array.isArray(body.tasks)) throw new Error(en ? 'The task list response was invalid.' : '待办列表回执格式无效。');
      const serverTasks = body.tasks;
      const serverIds = new Set(serverTasks.map((task) => task.id));
      for (const id of confirmedCreates.current.keys()) if (serverIds.has(id)) confirmedCreates.current.delete(id);
      const filterMatches = (task: Task) => (status === 'all' || task.status === status) && (!dueDate || task.due_date === dueDate);
      const knownButMissing = [...confirmedCreates.current.values()].filter(filterMatches);
      const visibleIds = new Set(serverTasks.map((task) => task.id));
      setTasks([...knownButMissing.filter((task) => !visibleIds.has(task.id)), ...serverTasks]);
    } catch (cause) {
      if (controller.signal.aborted || sequence !== loadSequence.current) return;
      if (!afterCreate) setTasks([]);
      const detail = cause instanceof Error ? cause.message : (en ? 'Tasks could not be loaded.' : '待办暂时无法读取。');
      setError(afterCreate
        ? (en ? `Task was created, but the list could not be refreshed: ${detail}` : `待办已创建，但列表刷新失败：${detail}`)
        : detail);
    } finally {
      if (sequence === loadSequence.current) {
        setLoading(false);
        if (activeLoad.current === controller) activeLoad.current = null;
      }
    }
  }, [dueDate, en, status]);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; lifecycle.current += 1; };
  }, []);

  useEffect(() => {
    const afterCreate = refreshAfterCreate.current;
    refreshAfterCreate.current = false;
    void load(!afterCreate, afterCreate);
    return () => {
      activeLoad.current?.abort();
      activeLoad.current = null;
      loadSequence.current += 1;
    };
  }, [load]);

  const update = async (task: Task, changes: Record<string, unknown>) => {
    if (savingId || createInFlight.current) return;
    setSavingId(task.id); setError(''); setNotice('');
    try {
      const response = await fetch(`/api/tasks/${encodeURIComponent(task.id)}`, {
        method: 'PATCH', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...changes, expected_updated_at: task.updated_at }),
      });
      const body = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) throw new Error(response.status === 409
        ? (en ? 'This task changed elsewhere. Reload it before editing.' : '任务已被其他操作更新，请刷新后再修改。')
        : String(body.detail ?? `HTTP ${response.status}`));
      setEditing(null); setNotice(en ? 'Task updated.' : '待办已更新。'); await load(false);
    } catch (cause) { setError(cause instanceof Error ? cause.message : (en ? 'Task update failed.' : '待办更新失败。')); }
    finally { setSavingId(''); }
  };

  const create = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (createInFlight.current || creating || savingId || !newTitle.trim()) return;
    const title = newTitle.trim();
    const dueDateValue = newDueDate || null;
    const signature = JSON.stringify({ title, due_date: dueDateValue });
    if (createAttempt.current?.signature !== signature) {
      createAttempt.current = { signature, key: crypto.randomUUID(), title, dueDate: newDueDate };
    }
    const attempt = createAttempt.current;
    const key = attempt.key;
    storePendingCreate(attempt);
    createInFlight.current = true;
    activeLoad.current?.abort();
    activeLoad.current = null;
    loadSequence.current += 1;
    setLoading(false);
    const requestLifecycle = lifecycle.current;
    const isCurrent = () => mounted.current && lifecycle.current === requestLifecycle && createAttempt.current?.key === key;
    setCreating(true); setError(''); setNotice('');
    try {
      const response = await fetch('/api/tasks', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
        body: JSON.stringify({ title, due_date: dueDateValue, original_command: 'Task page explicit create' }),
      });
      const body = await response.json().catch(() => ({})) as { detail?: string; status?: string; task?: Task };
      if (response.status === 401) { window.location.reload(); return; }
      if (!response.ok) {
        throw new Error(response.status === 409
          ? (en ? 'This create request conflicted. Your task is still here; refresh before trying a new task.' : '创建请求发生冲突，内容仍保留；请先刷新再创建新待办。')
          : response.status === 503 && body.detail === 'Task is not enabled'
            ? (en ? 'Task storage is not enabled in this environment. Your task is still here.' : '当前环境未启用待办存储，内容仍保留。')
            : String(body.detail ?? `HTTP ${response.status}`));
      }
      if ((body.status !== 'created' && body.status !== 'duplicate')
        || !body.task || typeof body.task.id !== 'string' || !/^[0-9a-f]{32}$/.test(body.task.id)
        || body.task.title !== title || body.task.due_date !== dueDateValue || body.task.status !== 'open'
        || body.task.source !== 'web_app_explicit_task' || !body.task.created_at || !body.task.updated_at) {
        throw new Error(en ? 'The save response could not be verified. Your task is still here; retry safely.' : '无法核实保存回执，内容仍保留；可安全重试。');
      }
      const savedTask = body.task;
      if (!isCurrent()) return;
      clearPendingCreate(key);
      confirmedCreates.current.set(savedTask.id, savedTask);
      createAttempt.current = null;
      setRestoredAttempt(false);
      setNewTitle(''); setNewDueDate(''); setCreateOpen(false);
      setNotice(en ? 'Task created.' : '待办已创建。');
      if (status !== 'open' || dueDate) {
        setTasks([savedTask]);
        refreshAfterCreate.current = true;
        setStatus('open'); setDueDate('');
      } else {
        setTasks((current) => [savedTask, ...current.filter((task) => task.id !== savedTask.id)]);
        await load(false, true);
      }
    } catch (cause) {
      if (isCurrent()) setError(cause instanceof Error ? cause.message : (en ? 'Task creation failed. Your task is still here.' : '待办创建失败，内容仍保留。'));
    } finally {
      createInFlight.current = false;
      // A verified receipt clears createAttempt before finally runs. Clear the
      // UI busy state for this mounted page even after that successful reset,
      // while still preventing an unmounted request from touching a new page.
      if (mounted.current && lifecycle.current === requestLifecycle) setCreating(false);
    }
  };

  const cancelCreate = () => {
    if (createInFlight.current) return;
    if (createAttempt.current) clearPendingCreate(createAttempt.current.key);
    setCreateOpen(false); setNewTitle(''); setNewDueDate('');
    createAttempt.current = null;
    setRestoredAttempt(false);
    setError('');
  };

  return <div className="task-page">
    <button type="button" className="capture-secondary" onClick={() => setShowSuggestions((value) => !value)}>{en ? 'Suggestions' : '主动建议'}</button>
    {showSuggestions && <CompanionSuggestionsPanel locale={locale} />}
    <header className="module-header"><div><p className="eyebrow">SECONDBRAIN / TODAY</p><h1>{en ? 'Today & Tasks' : '今日与待办'}</h1><p className="workspace-subtitle">{en ? 'Manage persisted tasks here or create one from Chat. Reminders are not enabled.' : '可直接管理待办，也可从 Chat 创建；提醒通知尚未实现。'}</p></div>
      <div className="task-header-actions"><button type="button" className="capture-primary" disabled={creating || Boolean(savingId)} onClick={() => { if (createOpen) cancelCreate(); else { setCreateOpen(true); setError(''); } }}>{createOpen ? (en ? 'Close form' : '收起') : (en ? 'New task' : '新建待办')}</button><button type="button" className="capture-secondary" disabled={loading || creating || Boolean(savingId)} onClick={() => void load()}>{loading ? (en ? 'Loading…' : '读取中…') : (en ? 'Refresh' : '刷新')}</button></div></header>
    <section className="task-panel" aria-labelledby="task-list-heading">
      <div className="task-toolbar"><h2 id="task-list-heading">{en ? 'Tasks' : '待办'}</h2><div className="task-filters"><label>{en ? 'Due date' : '截止日期'} <input aria-label={en ? 'Filter by due date' : '按截止日期筛选'} type="date" value={dueDate} disabled={creating} onChange={(event) => { if (!createInFlight.current) setDueDate(event.target.value); }} /></label><label>{en ? 'Status' : '状态'} <select value={status} disabled={creating} onChange={(event) => { if (!createInFlight.current) setStatus(event.target.value as typeof status); }}><option value="open">{en ? 'Open' : '未完成'}</option><option value="completed">{en ? 'Completed' : '已完成'}</option><option value="all">{en ? 'All' : '全部'}</option></select></label></div></div>
      {error && <p className="task-alert" role="alert">{error}</p>}{notice && <p role="status" className="task-notice">{notice}</p>}
      {createOpen && <form className="task-create-form" aria-label={en ? 'Create task' : '新建待办'} onSubmit={(event) => void create(event)}>
        {restoredAttempt && <p role="status">{en ? 'A previous create result is unconfirmed. Retry the same task safely or cancel it.' : '上次创建结果尚未确认；可用相同内容安全重试，或取消后重新创建。'}</p>}
        <label>{en ? 'Task title' : '待办内容'}<input autoFocus required maxLength={4000} disabled={creating} value={newTitle} onChange={(event) => setNewTitle(event.target.value)} /></label>
        <label>{en ? 'Due date (optional)' : '截止日期（可选）'}<input aria-label={en ? 'New task due date' : '新待办截止日期'} type="date" disabled={creating} value={newDueDate} onChange={(event) => setNewDueDate(event.target.value)} /></label>
        <div className="task-actions"><button type="submit" className="capture-primary" disabled={creating || !newTitle.trim()}>{creating ? (en ? 'Creating…' : '创建中…') : (en ? 'Create task' : '创建待办')}</button><button type="button" className="capture-secondary" disabled={creating} onClick={cancelCreate}>{en ? 'Cancel' : '取消'}</button></div>
      </form>}
      {loading ? <p role="status">{en ? 'Loading tasks…' : '正在读取待办…'}</p> : tasks.length === 0 ? <p className="task-empty">{en ? 'No tasks in this view.' : '此视图中暂无待办。'}</p> : <ol className="task-list">{tasks.map((task) => <li id={task.id === targetTaskId ? `task-${task.id}` : undefined} className={`task-item ${task.status}${task.id === targetTaskId ? ' is-brief-source' : ''}`} key={task.id}>
        {task.id === targetTaskId && <p role="status">{en ? 'Referenced by this Daily Brief.' : '此待办被每日简报引用。'}</p>}
        {editing?.id === task.id ? <div className="task-edit-form"><label>{en ? 'Title' : '标题'}<input value={editing.title} maxLength={4000} onChange={(event) => setEditing({ ...editing, title: event.target.value })} /></label><label>{en ? 'Due date' : '截止日期'}<input aria-label={en ? 'Edit due date' : '编辑截止日期'} type="date" value={editing.due_date} onChange={(event) => setEditing({ ...editing, due_date: event.target.value })} /></label><div className="task-actions"><button type="button" className="capture-primary" disabled={Boolean(savingId) || !editing.title.trim()} onClick={() => void update(task, { title: editing.title, due_date: editing.due_date || null })}>{savingId === task.id ? (en ? 'Saving…' : '保存中…') : (en ? 'Save' : '保存')}</button><button type="button" className="capture-secondary" onClick={() => setEditing(null)}>{en ? 'Cancel' : '取消'}</button></div></div>
          : <><div className="task-main"><div><h3>{task.title}</h3><p>{task.due_date ? `${en ? 'Due' : '截止'} ${task.due_date}` : (en ? 'No due date' : '未设截止日期')} · {en ? 'Updated' : '更新于'} {new Date(task.updated_at).toLocaleString(en ? 'en-US' : 'zh-CN')}</p></div><span className={`capture-status ${task.status === 'completed' ? 'status-completed' : ''}`}>{task.status === 'completed' ? (en ? 'Completed' : '已完成') : (en ? 'Open' : '未完成')}</span></div>
            <div className="task-actions"><button type="button" className="capture-secondary" disabled={Boolean(savingId) || creating} onClick={() => { if (!createInFlight.current) setEditing({ id: task.id, title: task.title, due_date: task.due_date ?? '' }); }}>{en ? 'Edit' : '编辑'}</button><button type="button" className="capture-secondary" disabled={Boolean(savingId) || creating} onClick={() => void update(task, { status: task.status === 'open' ? 'completed' : 'open' })}>{task.status === 'open' ? (en ? 'Complete' : '标记完成') : (en ? 'Reopen' : '恢复未完成')}</button></div>
            <details className="task-history"><summary>{en ? 'History' : '变更记录'}</summary><ol>{(task.history ?? []).map((event, index) => <li key={`${event.at}-${index}`}>{new Date(event.at).toLocaleString(en ? 'en-US' : 'zh-CN')} · {event.event === 'created' ? (en ? 'Created' : '创建') : JSON.stringify(event.changes)}</li>)}</ol>{task.original_command && <p>{en ? 'Original command: ' : '原始命令：'}{task.original_command}</p>}</details></>}
      </li>)}</ol>}
    </section>
  </div>;
}
