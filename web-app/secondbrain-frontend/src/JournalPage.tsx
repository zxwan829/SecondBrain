import React, { useEffect, useRef, useState } from 'react';

type Entry = { id: string; created_at: string; source: string; original_text: string };

function todayInShanghai() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
}

export function JournalPage() {
  const [day, setDay] = useState(todayInShanghai);
  const [text, setText] = useState('');
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [retryKey, setRetryKey] = useState<string | null>(null);
  const loadRevision = useRef(0);

  const load = async (date: string) => {
    const revision = ++loadRevision.current;
    setLoading(true); setError('');
    try {
      const response = await fetch(`/api/journal/${date}`, { credentials: 'same-origin' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json() as { entries: Entry[] };
      if (loadRevision.current === revision) setEntries(data.entries);
    } catch {
      if (loadRevision.current === revision) { setEntries([]); setError('无法读取 Journal。请检查 Core 会话和 Journal 测试目录配置。'); }
    } finally { if (loadRevision.current === revision) setLoading(false); }
  };

  useEffect(() => { void load(day); }, [day]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setSaving(true); setError(''); setNotice('');
    const key = retryKey ?? crypto.randomUUID();
    setRetryKey(key);
    try {
      const response = await fetch('/api/journal/entries', {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
        body: JSON.stringify({ date: day, text }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
      setText(''); setRetryKey(null);
      setNotice(result.status === 'duplicate' ? '这条请求已保存，未重复追加。' : '已追加到当日日记。');
      await load(day);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Journal 保存失败。请重试。');
    } finally { setSaving(false); }
  };

  return <div className="journal-page">
    <header className="module-header"><div><p className="eyebrow">SECONDBRAIN / JOURNAL</p><h1>日记</h1><p className="workspace-subtitle">只保存明确以“记一下”或“写日记”开头的原话。</p></div></header>
    <section className="journal-panel">
      <form onSubmit={submit}>
        <label htmlFor="journal-date">日期</label>
        <input id="journal-date" type="date" value={day} onChange={(event) => { setDay(event.target.value); setNotice(''); }} required />
        <label htmlFor="journal-text">自然语言记录</label>
        <textarea id="journal-text" value={text} onChange={(event) => { setText(event.target.value); setRetryKey(null); }} placeholder="记一下：今天完成了……" maxLength={16000} required />
        <p className="journal-hint">输入明确的记录意图并提交；普通聊天不会写入日记。保存后只追加，不覆盖已有记录。</p>
        <button type="submit" disabled={saving || loading || !text.trim()}>{saving ? '正在保存…' : '追加原话'}</button>
      </form>
      {notice && <p role="status" className="journal-notice">{notice}</p>}
      {error && <p role="alert" className="journal-error">{error}</p>}
    </section>
    <section className="journal-panel" aria-labelledby="journal-entries-heading">
      <div className="journal-list-heading"><h2 id="journal-entries-heading">{day} 的记录</h2><button type="button" onClick={() => void load(day)} disabled={loading}>{loading ? '读取中…' : '刷新'}</button></div>
      {loading && <p role="status">正在读取…</p>}
      {!loading && entries.length === 0 && <p className="journal-hint">当天还没有记录。</p>}
      <ol className="journal-entry-list">{entries.map((entry) => <li key={entry.id}><time>{new Date(entry.created_at).toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit' })}</time><p>{entry.original_text}</p></li>)}</ol>
    </section>
  </div>;
}
