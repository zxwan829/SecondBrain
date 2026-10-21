import React, { useCallback, useEffect, useRef, useState } from 'react';

type Task = {
  id: string; title: string; due_date: string | null; status: 'open' | 'completed';
  created_at: string; updated_at: string; source: string; original_command: string;
  history: { at: string; event: string; changes: Record<string, unknown> }[];
};
type Locale = 'zh-CN' | 'en';

export function TaskPage({ locale }: { locale: Locale }) {
  const en = locale === 'en';
  const requestedTaskId = new URLSearchParams(window.location.search).get('task_id');
  const targetTaskId = requestedTaskId && /^[0-9a-f]{32}$/i.test(requestedTaskId) ? requestedTaskId.toLowerCase() : null;
  const [status, setStatus] = useState<'open' | 'completed' | 'all'>(targetTaskId ? 'all' : 'open');
  const [dueDate, setDueDate] = useState('');
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState('');
  const [editing, setEditing] = useState<{ id: string; title: string; due_date: string } | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const activeLoad = useRef<AbortController | null>(null);
  const loadSequence = useRef(0);

  const load = useCallback(async (showLoading = true) => {
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
      setTasks(Array.isArray(body.tasks) ? body.tasks : []);
    } catch (cause) {
      if (controller.signal.aborted || sequence !== loadSequence.current) return;
      setTasks([]);
      setError(cause instanceof Error ? cause.message : (en ? 'Tasks could not be loaded.' : '待办暂时无法读取。'));
    } finally {
      if (sequence === loadSequence.current) {
        setLoading(false);
        if (activeLoad.current === controller) activeLoad.current = null;
      }
    }
  }, [dueDate, en, status]);

  useEffect(() => {
    void load();
    return () => {
      activeLoad.current?.abort();
      activeLoad.current = null;
      loadSequence.current += 1;
    };
  }, [load]);

  const update = async (task: Task, changes: Record<string, unknown>) => {
    if (savingId) return;
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

  return <div className="task-page">
    <header className="module-header"><div><p className="eyebrow">SECONDBRAIN / TODAY</p><h1>{en ? 'Today & Tasks' : '今日与待办'}</h1><p className="workspace-subtitle">{en ? 'Create a task in Chat with “Add task: …”. Add a due date with “due: YYYY-MM-DD”. Reminders are not enabled.' : '在 Chat 输入“添加待办：……”即可创建；可用“截止：YYYY-MM-DD”指定截止日。提醒通知尚未实现。'}</p></div>
      <button type="button" className="capture-secondary" disabled={loading} onClick={() => void load()}>{loading ? (en ? 'Loading…' : '读取中…') : (en ? 'Refresh' : '刷新')}</button></header>
    <section className="task-panel" aria-labelledby="task-list-heading">
      <div className="task-toolbar"><h2 id="task-list-heading">{en ? 'Tasks' : '待办'}</h2><div className="task-filters"><label>{en ? 'Due date' : '截止日期'} <input aria-label={en ? 'Filter by due date' : '按截止日期筛选'} type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} /></label><label>{en ? 'Status' : '状态'} <select value={status} onChange={(event) => setStatus(event.target.value as typeof status)}><option value="open">{en ? 'Open' : '未完成'}</option><option value="completed">{en ? 'Completed' : '已完成'}</option><option value="all">{en ? 'All' : '全部'}</option></select></label></div></div>
      {error && <p className="task-alert" role="alert">{error}</p>}{notice && <p role="status" className="task-notice">{notice}</p>}
      {loading ? <p role="status">{en ? 'Loading tasks…' : '正在读取待办…'}</p> : tasks.length === 0 ? <p className="task-empty">{en ? 'No tasks in this view.' : '此视图中暂无待办。'}</p> : <ol className="task-list">{tasks.map((task) => <li id={task.id === targetTaskId ? `task-${task.id}` : undefined} className={`task-item ${task.status}${task.id === targetTaskId ? ' is-brief-source' : ''}`} key={task.id}>
        {task.id === targetTaskId && <p role="status">{en ? 'Referenced by this Daily Brief.' : '此待办被每日简报引用。'}</p>}
        {editing?.id === task.id ? <div className="task-edit-form"><label>{en ? 'Title' : '标题'}<input value={editing.title} maxLength={4000} onChange={(event) => setEditing({ ...editing, title: event.target.value })} /></label><label>{en ? 'Due date' : '截止日期'}<input aria-label={en ? 'Edit due date' : '编辑截止日期'} type="date" value={editing.due_date} onChange={(event) => setEditing({ ...editing, due_date: event.target.value })} /></label><div className="task-actions"><button type="button" className="capture-primary" disabled={Boolean(savingId) || !editing.title.trim()} onClick={() => void update(task, { title: editing.title, due_date: editing.due_date || null })}>{savingId === task.id ? (en ? 'Saving…' : '保存中…') : (en ? 'Save' : '保存')}</button><button type="button" className="capture-secondary" onClick={() => setEditing(null)}>{en ? 'Cancel' : '取消'}</button></div></div>
          : <><div className="task-main"><div><h3>{task.title}</h3><p>{task.due_date ? `${en ? 'Due' : '截止'} ${task.due_date}` : (en ? 'No due date' : '未设截止日期')} · {en ? 'Updated' : '更新于'} {new Date(task.updated_at).toLocaleString(en ? 'en-US' : 'zh-CN')}</p></div><span className={`capture-status ${task.status === 'completed' ? 'status-completed' : ''}`}>{task.status === 'completed' ? (en ? 'Completed' : '已完成') : (en ? 'Open' : '未完成')}</span></div>
            <div className="task-actions"><button type="button" className="capture-secondary" disabled={Boolean(savingId)} onClick={() => setEditing({ id: task.id, title: task.title, due_date: task.due_date ?? '' })}>{en ? 'Edit' : '编辑'}</button><button type="button" className="capture-secondary" disabled={Boolean(savingId)} onClick={() => void update(task, { status: task.status === 'open' ? 'completed' : 'open' })}>{task.status === 'open' ? (en ? 'Complete' : '标记完成') : (en ? 'Reopen' : '恢复未完成')}</button></div>
            <details className="task-history"><summary>{en ? 'History' : '变更记录'}</summary><ol>{(task.history ?? []).map((event, index) => <li key={`${event.at}-${index}`}>{new Date(event.at).toLocaleString(en ? 'en-US' : 'zh-CN')} · {event.event === 'created' ? (en ? 'Created' : '创建') : JSON.stringify(event.changes)}</li>)}</ol>{task.original_command && <p>{en ? 'Original command: ' : '原始命令：'}{task.original_command}</p>}</details></>}
      </li>)}</ol>}
    </section>
  </div>;
}
