import React, { useEffect, useRef, useState } from 'react';
import { fetchGroundingCandidates, type GroundingCandidates } from './chat-grounding-candidates';

export function ChatGroundingCandidates({ sessionId, query, locale, disabled }: {
  sessionId: string; query: string; locale: 'zh-CN' | 'en'; disabled: boolean;
}) {
  const en = locale === 'en';
  const [result, setResult] = useState<GroundingCandidates | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    request.current?.abort(); request.current = null;
    setResult(null); setError(''); setBusy(false);
    return () => { request.current?.abort(); request.current = null; };
  }, [sessionId, query]);
  const check = async () => {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setResult(null); setError('');
    try { setResult(await fetchGroundingCandidates(sessionId, query, controller.signal)); }
    catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : (en ? 'Knowledge is unavailable.' : 'Knowledge 暂不可用。'));
    } finally { if (!controller.signal.aborted) setBusy(false); }
  };
  const status = result?.status;
  return <section className="chat-context-preview" aria-label={en ? 'Knowledge references' : '检索参考'}>
    <div className="chat-context-preview-heading"><h3>{en ? 'Knowledge references' : '检索参考'}</h3>
      <button type="button" disabled={disabled || busy || !sessionId || !query.trim()} onClick={() => void check()}>
        {busy ? (en ? 'Checking…' : '正在核验…') : (en ? 'Check Knowledge sources' : '核对 Knowledge 来源')}
      </button></div>
    <p className="chat-context-preview-note">{en
      ? 'Core returns verified source metadata only. This does not mean the answer used these sources.'
      : 'Core 只返回已核验的来源元数据；这不表示对话回答使用了这些来源。'}</p>
    {busy && <p role="status">{en ? 'Checking authorized sources…' : '正在核验获准来源…'}</p>}
    {error && <p role="alert">{en ? 'Knowledge references could not be verified. ' : '检索参考核验失败：'}{error}</p>}
    {result && <><p role="status">{result.status === 'none' ? (en ? 'No matching source.' : '没有匹配来源。')
      : result.status === 'partial' ? (en ? 'Some sources changed or were incomplete.' : '部分来源已变化或不完整。')
        : result.status === 'unavailable' ? (en ? 'Sources are unavailable.' : '来源暂不可用。')
          : result.status === 'needs_review' ? (en ? 'Multiple sources need review.' : '找到多个来源，需要人工复核。')
            : (en ? 'A verified source is available.' : '找到已核验来源。')} · {en ? 'Answer attribution' : '回答归因'}: {result.answer_attribution}</p>
      {result.items.length > 0 && <ul>{result.items.map((item) => <li key={item.citation_id}>
        <strong>{item.title}</strong><dl><dt>SHA-256</dt><dd>{item.sha256}</dd>
          <dt>{en ? 'Knowledge status' : 'Knowledge 状态'}</dt><dd>{item.knowledge_status}</dd>
          <dt>{en ? 'Provenance' : '来源验证'}</dt><dd>{item.provenance_status}</dd></dl>
      </li>)}</ul>}</>}
  </section>;
}
