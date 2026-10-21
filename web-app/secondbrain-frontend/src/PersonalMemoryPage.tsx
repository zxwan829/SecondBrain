import React, { useCallback, useEffect, useRef, useState } from 'react';
import { correctPersonalMemory, fetchPersonalMemories, fetchPersonalMemoryHistory, revokePersonalMemory,
  type MemoryChange, type PersonalMemory } from './personal-memory';

type Locale = 'zh-CN' | 'en';
type PendingChange = { attempt: MemoryChange; kind: 'correct' | 'revoke'; text?: string };

export function PersonalMemoryPage({ locale }: { locale: Locale }) {
  const en = locale === 'en';
  const [items, setItems] = useState<PersonalMemory[]>([]);
  const [history, setHistory] = useState<Record<string, PersonalMemory[]>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<PendingChange | null>(null);
  const [retryOnly, setRetryOnly] = useState(false);
  const [lastReceipt, setLastReceipt] = useState<PersonalMemory | null>(null);
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const sequence = useRef(0);
  const listAbort = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    listAbort.current?.abort();
    const controller = new AbortController(); listAbort.current = controller;
    const request = ++sequence.current; setLoading(true); setError('');
    try {
      const result = await fetchPersonalMemories(controller.signal);
      if (!controller.signal.aborted && request === sequence.current) {
        setItems(result); setDrafts(Object.fromEntries(result.map((item) => [item.memory_id, item.content.text])));
      }
    } catch (cause) {
      if (!controller.signal.aborted && request === sequence.current) {
        const status = (cause as Error & { status?: number }).status;
        setError(status === 401 ? (en ? 'Sign in again to manage Personal Memory.' : '请重新登录后管理个人记忆。')
          : status === 403 ? (en ? 'Personal Memory access was denied.' : '个人记忆权限不足。')
            : en ? 'Could not safely load Personal Memory.' : '无法安全读取个人记忆。');
      }
    } finally { if (request === sequence.current) setLoading(false); }
  }, [en]);

  useEffect(() => { void load(); return () => { sequence.current += 1; listAbort.current?.abort(); }; }, [load]);

  const showHistory = async (id: string) => {
    setError('');
    try {
      const revisions = await fetchPersonalMemoryHistory(id);
      setHistory((current) => ({ ...current, [id]: revisions }));
    }
    catch (cause) {
      const status = (cause as Error & { status?: number }).status;
      setError(status === 404 ? (en ? 'This memory no longer exists.' : '该记忆已不存在。')
        : status === 403 ? (en ? 'History access was denied.' : '无权读取记忆历史。')
          : en ? 'History could not be verified.' : '无法核验记忆历史。');
    }
  };

  const begin = (item: PersonalMemory, kind: PendingChange['kind']) => {
    const key = crypto.randomUUID();
    setLastReceipt(null);
    setPending({ kind, text: kind === 'correct' ? (drafts[item.memory_id] ?? item.content.text) : undefined,
      attempt: { memory_id: item.memory_id, expected_revision: item.revision, idempotency_key: key,
        source_type: 'user_confirmed', source_ref: `web-personal-memory-confirmation/${key}` } });
    setConfirm(''); setError(''); setRetryOnly(false);
  };

  const submit = async () => {
    if (!pending || confirm !== (en ? 'CONFIRM' : '确认') || busy) return;
    if (pending.kind === 'correct' && (!pending.text?.trim() || pending.text.length > 4000)) {
      setError(en ? 'Enter a replacement value up to 4000 characters.' : '请输入不超过 4000 字的更正内容。'); return;
    }
    setBusy(true); setError('');
    try {
      const receipt = pending.kind === 'correct'
        ? await correctPersonalMemory({ ...pending.attempt, content: { text: pending.text!.trim() } })
        : await revokePersonalMemory(pending.attempt);
      setLastReceipt(receipt); setPending(null); setConfirm(''); setRetryOnly(false); await load();
    } catch (cause) {
      const status = (cause as Error & { status?: number }).status;
      if (status === 409) {
        setPending(null); setConfirm(''); setRetryOnly(false); await load();
        setError(en ? 'This memory changed since it was loaded. Review the latest revision before trying again.'
          : '此记忆在读取后已变化。请先核对最新版本后再操作。');
      } else {
        // Keep the exact payload and idempotency key so the user can retry safely.
        setRetryOnly(true);
        setError(en ? 'The result is unconfirmed. Retry the same request with its original key.'
          : '操作结果尚未确认；重试会复用原请求和幂等键。');
      }
    } finally { setBusy(false); }
  };

  return <section className="personal-memory-page">
    <header className="page-header"><div><p className="eyebrow">SECONDBRAIN / PERSONAL MEMORY</p>
      <h1>{en ? 'Personal Memory' : '个人记忆'}</h1>
      <p>{en ? 'Review, correct, or revoke explicit memories. This page does not learn from model replies.'
        : '查看、更正或撤销明确记录的记忆。本页不会从模型回复中自动学习。'}</p></div>
      <button type="button" onClick={() => void load()} disabled={loading || busy}>{en ? 'Refresh' : '刷新'}</button></header>
    <p className="chat-context-preview-note">{en
      ? 'Actions require an explicit confirmation. A successful save is shown only after Core returns the matching next revision. Changes apply to later reads; this page does not inject memory into Chat.'
      : '每项更改都需要明确确认。只有 Core 返回匹配的新版本后才显示成功；更改会影响后续读取，本页不会把记忆注入对话。'}</p>
    {loading && <p role="status">{en ? 'Loading authorized memories…' : '正在读取获准的记忆…'}</p>}
    {error && <p role="alert">{error}</p>}
    {lastReceipt && <section className="personal-memory-receipt" role="status">
      <strong>{en ? 'Core confirmed the saved revision' : 'Core 已确认保存此版本'}</strong>
      <span>{lastReceipt.memory_id} · r{lastReceipt.revision} · {lastReceipt.status}</span>
      <button type="button" onClick={() => void showHistory(lastReceipt.memory_id)}>{en ? 'Read revision history' : '读取版本历史'}</button>
      {history[lastReceipt.memory_id] && <ol>{history[lastReceipt.memory_id].map((revision) =>
        <li key={`${revision.memory_id}:${revision.revision}`}>r{revision.revision} · {revision.revision_status ?? revision.status} · {revision.content.text}</li>)}</ol>}
    </section>}
    {!loading && !error && items.length === 0 && <p role="status">{en ? 'No active memories.' : '没有有效记忆。'}</p>}
    <ul className="personal-memory-list">{items.map((item) => <li key={item.memory_id}>
      <article aria-label={en ? 'Personal memory item' : '个人记忆条目'}>
        <header><strong>{item.category}</strong><span>{item.fact_kind} · r{item.revision}</span></header>
        <p>{item.content.text}</p>
        <small>{en ? 'Recorded' : '记录时间'}: {item.recorded_at}{item.expires_at ? ` · ${en ? 'Expires' : '到期'}: ${item.expires_at}` : ''}</small>
        {item.source && <small>{en ? 'Source' : '来源'}: {item.source.type} · {item.source.ref}</small>}
        <div className="personal-memory-actions">
          <button type="button" onClick={() => void showHistory(item.memory_id)}>{en ? 'Revision history' : '版本历史'}</button>
          <button type="button" disabled={busy || item.fact_kind === 'inference'} onClick={() => begin(item, 'correct')}>{en ? 'Correct' : '更正'}</button>
          <button type="button" disabled={busy || item.fact_kind === 'inference'} onClick={() => begin(item, 'revoke')}>{en ? 'Revoke' : '撤销'}</button>
        </div>
        {history[item.memory_id] && <ol aria-label={en ? 'Memory revision history' : '记忆版本历史'}>{history[item.memory_id].map((revision) =>
          <li key={`${revision.memory_id}:${revision.revision}`}>r{revision.revision} · {revision.revision_status ?? revision.status} · {revision.content.text}</li>)}</ol>}
      </article>
    </li>)}</ul>
    {pending && <section className="personal-memory-confirm" aria-label={en ? 'Confirm memory change' : '确认记忆更改'}>
      <h2>{pending.kind === 'correct' ? (en ? 'Review correction' : '核对更正') : (en ? 'Revoke memory' : '撤销记忆')}</h2>
      {pending.kind === 'correct' ? <label>{en ? 'Replacement text' : '更正后的内容'}
        <textarea maxLength={4000} value={pending.text ?? ''} disabled={busy || retryOnly}
          onChange={(event) => setPending({ ...pending, text: event.target.value })} /></label>
        : <p>{en ? 'This memory will stop appearing in active recall. Its history remains available.' : '该记忆将不再参与有效召回，历史记录仍保留。'}</p>}
      <label>{en ? 'Type CONFIRM' : '输入“确认”'}
        <input value={confirm} disabled={busy || retryOnly} onChange={(event) => setConfirm(event.target.value)} autoComplete="off" /></label>
      <button type="button" onClick={() => void submit()} disabled={busy || confirm !== (en ? 'CONFIRM' : '确认')}>{busy ? (en ? 'Saving…' : '正在保存…') : (en ? 'Confirm change' : '确认更改')}</button>
      {error && <button type="button" disabled={busy || !pending} onClick={() => void submit()}>{en ? 'Retry same request' : '使用同一请求重试'}</button>}
      <button type="button" onClick={() => { setPending(null); setConfirm(''); setError(''); setRetryOnly(false); }} disabled={busy}>{en ? 'Cancel' : '取消'}</button>
    </section>}
  </section>;
}
