import React, { useEffect, useState } from 'react';

type Locale = 'zh-CN' | 'en';
type Suggestion = { id: string; category: 'task_due' | 'project_next_step'; title: string; reason: string; revision: number };
type Preferences = { revision: number; enabled: boolean; categories: string[] };

async function request(path: string, init?: RequestInit) {
  const response = await fetch(path, { ...init, credentials: 'same-origin', cache: 'no-store', headers: {
    ...(init?.headers ?? {}), ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
  } });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) { const error = new Error(String(body.detail ?? `HTTP ${response.status}`)) as Error & { status?: number }; error.status = response.status; throw error; }
  return body;
}

function parseSuggestions(value: unknown): Suggestion[] {
  if (!Array.isArray(value)) throw new Error('Companion suggestions are unavailable.');
  return value.map((entry): Suggestion => {
    if (!entry || typeof entry !== 'object') throw new Error('Companion suggestions are unavailable.');
    const item = entry as Record<string, unknown>;
    if (typeof item.id !== 'string' || !/^[a-f0-9]{32}$/.test(item.id)
      || (item.category !== 'task_due' && item.category !== 'project_next_step')
      || typeof item.title !== 'string' || typeof item.reason !== 'string'
      || item.state !== 'shown' || !Number.isSafeInteger(item.revision) || (item.revision as number) < 1
      || !item.source_ref || typeof item.source_ref !== 'object') throw new Error('Companion suggestions are unavailable.');
    return { id: item.id, category: item.category, title: item.title, reason: item.reason, revision: item.revision as number };
  });
}

export function CompanionSuggestionsPanel({ locale }: { locale: Locale }) {
  const en = locale === 'en';
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [items, setItems] = useState<Suggestion[]>([]);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<{ key: string; intent: string } | null>(null);
  const label = (value: string) => en ? value : value === 'disabled' ? '已关闭' : value === 'none' ? '暂无建议' : value === 'partial' ? '部分建议不可用' : '建议已更新';

  const load = async () => {
    setError(''); setItems([]);
    try {
      const [prefs, suggestions] = await Promise.all([
        request('/api/companion/preferences'), request('/api/companion/suggestions'),
      ]);
      if (!Number.isSafeInteger(prefs.revision) || typeof prefs.enabled !== 'boolean'
        || !Array.isArray(prefs.categories) || !prefs.categories.every((item: unknown) => item === 'task_due' || item === 'project_next_step')) {
        throw new Error(en ? 'Companion preferences are unavailable.' : '主动建议设置不可用。');
      }
      setPreferences({ revision: prefs.revision, enabled: prefs.enabled, categories: prefs.categories });
      setItems(parseSuggestions(suggestions.items)); setStatus(label(suggestions.status));
    } catch (cause) { setItems([]); setError(cause instanceof Error ? cause.message : 'Companion unavailable'); }
  };
  useEffect(() => { void load(); }, []);

  const save = async (enabled: boolean, categories: string[]) => {
    if (!preferences || busy) return;
    setBusy(true); setError('');
    const intent = JSON.stringify({ enabled, categories, expected_revision: preferences.revision });
    const idempotency = pending?.intent === intent ? pending.key : crypto.randomUUID().replaceAll('-', '');
    setPending({ key: idempotency, intent });
    try {
      const result = await request('/api/companion/preferences', { method: 'PUT', headers: { 'Idempotency-Key': idempotency }, body: JSON.stringify({ enabled, categories, expected_revision: preferences.revision }) });
      setPreferences({ revision: result.revision, enabled: result.enabled, categories: result.categories }); setPending(null);
      if (!enabled) { setItems([]); setStatus(en ? 'Disabled' : '已关闭'); }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Save failed'); }
    finally { setBusy(false); }
  };

  const evaluate = async () => {
    setBusy(true); setError(''); setItems([]);
    try { const result = await request('/api/companion/suggestions/evaluate', { method: 'POST', body: '{}' });
      setItems(parseSuggestions(result.items)); setStatus(label(result.status));
    } catch (cause) { setItems([]); setError(cause instanceof Error ? cause.message : 'Evaluation failed'); }
    finally { setBusy(false); }
  };
  const feedback = async (item: Suggestion, decision: 'accepted' | 'dismissed') => {
    setBusy(true); setError(''); const intent = JSON.stringify({ id: item.id, decision, expected_revision: item.revision });
    const idem = pending?.intent === intent ? pending.key : crypto.randomUUID().replaceAll('-', '');
    setPending({ key: idem, intent });
    try {
      const receipt = await request(`/api/companion/suggestions/${encodeURIComponent(item.id)}/feedback`, { method: 'POST', headers: { 'Idempotency-Key': idem }, body: JSON.stringify({ decision, expected_revision: item.revision }) });
      if (receipt.event !== 'companion.suggestion.feedback' || receipt.version !== 1 || receipt.id !== item.id
        || receipt.revision !== item.revision + 1 || receipt.state !== decision) throw new Error('Companion feedback receipt is invalid.');
      setItems((current) => current.filter((candidate) => candidate.id !== item.id));
      setPending(null);
    } catch (cause) {
      if ((cause as Error & { status?: number })?.status === 409) {
        await load(); setError(en ? 'This suggestion changed. The list has been refreshed; review it and try again.' : '建议已变化，列表已刷新；请检查后重试。');
      } else setError(cause instanceof Error ? cause.message : 'Feedback failed');
    }
    finally { setBusy(false); }
  };

  return <section className="task-panel" aria-label={en ? 'Companion suggestions' : '主动建议'}>
    <div className="task-toolbar"><h2>{en ? 'Suggestions' : '主动建议'}</h2><span role="status">{status}</span></div>
    <p>{en ? 'Suggestions are calculated only when you ask. Accepting records feedback and never starts a task or message.' : '仅在你点击时计算建议。采纳只记录反馈，不会启动任务或发送消息。'}</p>
    {error && <p role="alert">{error}</p>}
    {preferences && <fieldset disabled={busy}><legend>{en ? 'Sources' : '建议来源'}</legend>
      <label><input type="checkbox" checked={preferences.enabled} onChange={(event) => void save(event.target.checked, event.target.checked ? (preferences.categories.length ? preferences.categories : ['task_due']) : [])} />{en ? 'Enable suggestions' : '启用建议'}</label>
      {(['task_due', 'project_next_step'] as const).map((category) => <label key={category}><input type="checkbox" checked={preferences.categories.includes(category)} onChange={(event) => { const next = event.target.checked ? [...preferences.categories, category] : preferences.categories.filter((item) => item !== category); void save(preferences.enabled || event.target.checked, next); }} />{category === 'task_due' ? (en ? 'Due tasks' : '待办截止日期') : (en ? 'Project next steps' : '项目下一步')}</label>)}
      <button type="button" disabled={busy || !preferences.enabled} onClick={() => void evaluate()}>{busy ? (en ? 'Working…' : '处理中…') : (en ? 'Check now' : '立即计算')}</button>
    </fieldset>}
    <ul>{items.map((item) => <li key={item.id}><strong>{item.title}</strong><p>{item.reason}</p><button type="button" disabled={busy} onClick={() => void feedback(item, 'accepted')}>{en ? 'Accept' : '采纳'}</button><button type="button" disabled={busy} onClick={() => void feedback(item, 'dismissed')}>{en ? 'Dismiss' : '忽略'}</button></li>)}</ul>
  </section>;
}
