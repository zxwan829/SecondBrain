import React, { useEffect, useRef, useState } from 'react';

type Entry = { id: string; created_at: string; source: string; original_text: string };

function parseEntries(value: unknown): Entry[] | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const entries = (value as { entries?: unknown }).entries;
  if (!Array.isArray(entries)) return null;
  const parsed: Entry[] = [];
  for (const entry of entries) {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return null;
    const row = entry as Record<string, unknown>;
    if (typeof row.id !== 'string' || !row.id || typeof row.created_at !== 'string' || !Number.isFinite(Date.parse(row.created_at))
      || typeof row.source !== 'string' || typeof row.original_text !== 'string') return null;
    parsed.push({ id: row.id, created_at: row.created_at, source: row.source, original_text: row.original_text });
  }
  return parsed;
}

function todayInShanghai() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
}

export function JournalPage() {
  const params = new URLSearchParams(window.location.search);
  const requestedDate = params.get('date');
  const initialDay = requestedDate && /^\d{4}-\d{2}-\d{2}$/.test(requestedDate) ? requestedDate : todayInShanghai();
  const requestedEntryId = params.get('entry_id');
  const targetEntryId = requestedEntryId && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(requestedEntryId) ? requestedEntryId : null;
  const [day, setDay] = useState(initialDay);
  const [text, setText] = useState('');
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [refreshError, setRefreshError] = useState('');
  const [retryKey, setRetryKey] = useState<string | null>(null);
  const loadRevision = useRef(0);
  const activeLoad = useRef<AbortController | null>(null);
  const currentDay = useRef(initialDay);

  const load = async (date: string) => {
    activeLoad.current?.abort();
    const controller = new AbortController();
    activeLoad.current = controller;
    const revision = ++loadRevision.current;
    setLoading(true); setRefreshError('');
    if (currentDay.current === date) setEntries([]);
    try {
      const response = await fetch(`/api/journal/${date}`, { credentials: 'same-origin', cache: 'no-store', signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = parseEntries(await response.json());
      if (!data) throw new Error('invalid Journal response');
      if (loadRevision.current === revision && currentDay.current === date) setEntries(data);
    } catch {
      if (!controller.signal.aborted && loadRevision.current === revision && currentDay.current === date) setRefreshError('无法刷新 Journal 列表；已保存的记录不会因此撤销。');
    } finally {
      if (loadRevision.current === revision) setLoading(false);
      if (activeLoad.current === controller) activeLoad.current = null;
    }
  };

  useEffect(() => { void load(day); }, [day]);
  useEffect(() => () => { activeLoad.current?.abort(); loadRevision.current += 1; }, []);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setSaving(true); setError(''); setNotice('');
    const key = retryKey ?? crypto.randomUUID();
    setRetryKey(key);
    try {
      const submittedDay = day;
      const submittedText = text;
      const response = await fetch('/api/journal/entries', {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
        body: JSON.stringify({ date: submittedDay, text: submittedText }),
      });
      const result = await response.json().catch(() => ({})) as { status?: string };
      if (!response.ok) throw new Error(response.status === 409 ? 'Journal 来源状态已变化，请刷新后重试。' : `Journal 保存未获成功回执（HTTP ${response.status}）。`);
      if (!['created', 'duplicate'].includes(String(result.status))) throw new Error('Journal 保存回执无法核验；请使用相同请求重试。');
      if (currentDay.current === submittedDay && text === submittedText) setText('');
      setRetryKey(null);
      setNotice(result.status === 'duplicate' ? '这条请求已保存，未重复追加。' : '已追加到当日日记。');
      if (currentDay.current === submittedDay) await load(submittedDay);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Journal 保存失败。请重试。');
    } finally { setSaving(false); }
  };

  return <div className="journal-page">
    <header className="module-header"><div><p className="eyebrow">SECONDBRAIN / JOURNAL</p><h1>日记</h1><p className="workspace-subtitle">只保存明确以“记一下”或“写日记”开头的原话。</p></div></header>
    <section className="journal-panel">
      <form onSubmit={submit}>
        <label htmlFor="journal-date">日期</label>
        <input id="journal-date" type="date" value={day} onChange={(event) => { currentDay.current = event.target.value; setDay(event.target.value); setNotice(''); setRefreshError(''); }} required />
        <label htmlFor="journal-text">自然语言记录</label>
        <textarea id="journal-text" value={text} onChange={(event) => { setText(event.target.value); setRetryKey(null); }} placeholder="记一下：今天完成了……" maxLength={16000} required />
        <p className="journal-hint">输入明确的记录意图并提交；普通聊天不会写入日记。保存后只追加，不覆盖已有记录。</p>
        <button type="submit" disabled={saving || loading || !text.trim()}>{saving ? '正在保存…' : '追加原话'}</button>
      </form>
      {notice && <p role="status" className="journal-notice">{notice}</p>}
      {error && <p role="alert" className="journal-error">{error}</p>}
      {refreshError && <p role="alert" className="journal-error">{refreshError}</p>}
    </section>
    <section className="journal-panel" aria-labelledby="journal-entries-heading">
      <div className="journal-list-heading"><h2 id="journal-entries-heading">{day} 的记录</h2><button type="button" onClick={() => void load(day)} disabled={loading}>{loading ? '读取中…' : '刷新'}</button></div>
      {loading && <p role="status">正在读取…</p>}
      {!loading && !refreshError && entries.length === 0 && <p className="journal-hint">当天还没有记录。</p>}
      <ol className="journal-entry-list">{entries.map((entry) => {
        // Daily Brief and Planning source refs use a date-qualified Journal ID
        // (`YYYY-MM-DD:<entry ID>`); older/direct links may carry the bare ID.
        const isRequestedSource = targetEntryId === entry.id || targetEntryId === `${day}:${entry.id}`;
        return <li id={isRequestedSource ? `journal-entry-${entry.id}` : undefined} className={isRequestedSource ? 'is-brief-source' : undefined} key={entry.id}><time>{new Date(entry.created_at).toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit' })}</time>{isRequestedSource && <span role="status">此记录被简报引用</span>}<p>{entry.original_text}</p></li>;
      })}</ol>
    </section>
  </div>;
}
