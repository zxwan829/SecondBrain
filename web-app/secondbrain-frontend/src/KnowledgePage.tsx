import React, { useEffect, useRef, useState } from 'react';
import { knowledgeApi, KnowledgeApiError, type KnowledgeDetail, type KnowledgeSearchItem, type KnowledgeSource } from './api/knowledge';
import { ReviewMarkdown } from './ReviewMarkdown';

type Locale = 'zh-CN' | 'en';
type SearchStatus = 'idle' | 'loading' | 'ready' | 'error';
type DetailStatus = 'idle' | 'loading' | 'ready' | 'error';
type SourceStatus = 'idle' | 'loading' | 'ready' | 'error';

function failureMessage(status: number | null, locale: Locale): string {
  if (status === 401) return locale === 'en' ? 'Your session has expired. Sign in again to search Knowledge.' : '登录状态已失效，请重新登录后搜索知识库。';
  if (status === 403) return locale === 'en' ? 'The Knowledge request was not authorized. Check your sign-in or request security policy.' : 'Knowledge 请求未获授权；请检查登录状态或请求安全策略。';
  if (status === 404) return locale === 'en' ? 'This result is no longer available. Search again for a current result.' : '该条目已不可用，请重新搜索获取最新结果。';
  if (status === 409) return locale === 'en' ? 'This document changed after search. Search again before opening it.' : '文档在搜索后发生变化，请重新搜索再打开。';
  if (status === 413 || status === 422) return locale === 'en' ? 'This document cannot be displayed.' : '该文档无法安全显示。';
  if (status === 429) return locale === 'en' ? 'Too many requests. Please wait and try again.' : '请求过于频繁，请稍后重试。';
  if (status === 503) return locale === 'en' ? 'Knowledge is currently unavailable.' : '知识库当前不可用。';
  return locale === 'en' ? 'Knowledge could not be loaded. Please try again.' : '知识库加载失败，请重试。';
}

function provenanceLabel(status: KnowledgeSearchItem['provenance_status'], locale: Locale): string {
  if (status === 'verified') return locale === 'en' ? 'Verified source' : '来源已验证';
  if (status === 'unverified') return locale === 'en' ? 'Source claim is unverified' : '来源声明不可验证';
  return locale === 'en' ? 'No verified source recorded' : '没有已验证的来源记录';
}

export function KnowledgePage({ locale }: { locale: Locale }) {
  const en = locale === 'en';
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<KnowledgeSearchItem[]>([]);
  const [selected, setSelected] = useState<KnowledgeSearchItem | null>(null);
  const [detail, setDetail] = useState<KnowledgeDetail | null>(null);
  const [source, setSource] = useState<KnowledgeSource | null>(null);
  const [sourceStatus, setSourceStatus] = useState<SourceStatus>('idle');
  const [searchStatus, setSearchStatus] = useState<SearchStatus>('idle');
  const [detailStatus, setDetailStatus] = useState<DetailStatus>('idle');
  const [partial, setPartial] = useState(false);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const activeRequest = useRef<AbortController | null>(null);
  const requestSequence = useRef(0);

  function beginRequest() {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    const sequence = ++requestSequence.current;
    return { controller, sequence };
  }

  function invalidateRequests() {
    requestSequence.current += 1;
    activeRequest.current?.abort();
    activeRequest.current = null;
  }

  useEffect(() => () => invalidateRequests(), []);

  async function search(term = query) {
    const normalized = term.trim();
    if (!normalized) return;
    const { controller, sequence } = beginRequest();
    setSearchStatus('loading');
    setDetailStatus('idle');
    setItems([]);
    setSelected(null);
    setDetail(null);
    setSource(null);
    setSourceStatus('idle');
    setPartial(false);
    setErrorStatus(null);
    try {
      const result = await knowledgeApi.search(normalized, controller.signal);
      if (sequence !== requestSequence.current || controller.signal.aborted) return;
      setItems(result.items);
      setPartial(result.status === 'truncated');
      setSearchStatus('ready');
    } catch (error) {
      if (sequence !== requestSequence.current || controller.signal.aborted) return;
      setItems([]);
      setSelected(null);
      setDetail(null);
      setSearchStatus('error');
      setErrorStatus(error instanceof KnowledgeApiError ? error.status : null);
    }
  }

  async function openItem(item: KnowledgeSearchItem) {
    const { controller, sequence } = beginRequest();
    setSelected(item);
    setDetail(null);
    setSource(null);
    setSourceStatus('idle');
    setDetailStatus('loading');
    setErrorStatus(null);
    try {
      const result = await knowledgeApi.detail(item.id, controller.signal);
      if (sequence !== requestSequence.current || controller.signal.aborted) return;
      setDetail(result);
      setDetailStatus('ready');
    } catch (error) {
      if (sequence !== requestSequence.current || controller.signal.aborted) return;
      const status = error instanceof KnowledgeApiError ? error.status : null;
      setDetail(null);
      setDetailStatus('error');
      setErrorStatus(status);
      if (status === 401 || status === 403 || status === 503) {
        setItems([]);
        setSelected(null);
      }
    }
  }

  async function checkSource() {
    if (!selected || sourceStatus === 'loading') return;
    const { controller, sequence } = beginRequest();
    setSource(null);
    setSourceStatus('loading');
    setErrorStatus(null);
    try {
      const result = await knowledgeApi.source(selected.id, controller.signal);
      if (sequence !== requestSequence.current || controller.signal.aborted) return;
      setSource(result);
      setSourceStatus('ready');
    } catch (error) {
      if (sequence !== requestSequence.current || controller.signal.aborted) return;
      setSource(null);
      setSourceStatus('error');
      setErrorStatus(error instanceof KnowledgeApiError ? error.status : null);
    }
  }

  function clearQuery() {
    invalidateRequests();
    setQuery('');
    setItems([]);
    setSelected(null);
    setDetail(null);
    setSource(null);
    setSourceStatus('idle');
    setSearchStatus('idle');
    setDetailStatus('idle');
    setPartial(false);
    setErrorStatus(null);
  }

  const canSearch = Boolean(query.trim());
  const showSearchAgain = (errorStatus === 404 || errorStatus === 409) && detailStatus === 'error';

  function backToResults() {
    invalidateRequests();
    setSelected(null);
    setDetail(null);
    setSource(null);
    setSourceStatus('idle');
    setDetailStatus('idle');
    setErrorStatus(null);
  }

  return <section className="knowledge-page" aria-labelledby="knowledge-page-title">
    <header className="knowledge-page-header">
      <div>
        <p className="eyebrow">SECONDBRAIN <span>/</span> KNOWLEDGE</p>
        <h1 id="knowledge-page-title">{en ? 'Knowledge' : '知识库'}</h1>
        <p className="workspace-subtitle">{en ? 'Search approved knowledge and open one result at a time.' : '搜索已整理的知识，并逐条打开查看。'}</p>
      </div>
    </header>

    <form className="knowledge-search" onSubmit={(event) => { event.preventDefault(); void search(); }}>
      <label htmlFor="knowledge-query">{en ? 'Search terms' : '搜索关键词'}</label>
      <div className="knowledge-search-controls">
        <input id="knowledge-query" type="search" value={query} maxLength={200}
          placeholder={en ? 'Enter a keyword' : '输入关键词'}
          onChange={(event) => setQuery(event.target.value)} />
        <button type="submit" disabled={!canSearch}>{searchStatus === 'loading' ? (en ? 'Searching…' : '正在搜索…') : (en ? 'Search' : '搜索')}</button>
        <button type="button" className="knowledge-clear" onClick={clearQuery} disabled={!query && items.length === 0}>
          {en ? 'Clear' : '清空'}
        </button>
      </div>
      <p>{en ? 'A search starts only when you submit a non-empty query.' : '仅在提交非空关键词后才会搜索。'}</p>
    </form>

    {searchStatus === 'loading' && <p className="knowledge-notice" role="status">{en ? 'Searching Knowledge…' : '正在搜索知识库…'}</p>}
    {searchStatus === 'error' && <p className="knowledge-error" role="alert">{failureMessage(errorStatus, locale)}</p>}
    {partial && <p className="knowledge-notice" role="status">{en ? 'Results are partial because the search reached a safety limit.' : '搜索受安全上限约束，当前结果不完整。'}</p>}
    {searchStatus === 'ready' && detailStatus !== 'error' && items.length === 0 && <p className="knowledge-empty" role="status">{en ? 'No matching Knowledge found.' : '没有找到匹配的知识条目。'}</p>}
    {detailStatus === 'error' && !selected && <p className="knowledge-error" role="alert">{failureMessage(errorStatus, locale)}</p>}

    {items.length > 0 && <div className="knowledge-results-grid">
      <section className="knowledge-results" aria-label={en ? 'Search results' : '搜索结果'}>
        <h2>{en ? 'Results' : '搜索结果'} <span>{items.length}</span></h2>
        <ul>
          {items.map((item) => <li key={item.id}>
            <button type="button" className={`knowledge-result${selected?.id === item.id ? ' is-selected' : ''}`}
              aria-pressed={selected?.id === item.id} onClick={() => { void openItem(item); }}>
              <strong>{item.title}</strong>
              <span>{item.snippet}</span>
              <small>{item.match === 'title' ? (en ? 'Title match' : '标题匹配') : (en ? 'Content match' : '正文匹配')} · {item.updated}</small>
              <small className={`knowledge-provenance is-${item.provenance_status}`}>{provenanceLabel(item.provenance_status, locale)}</small>
            </button>
          </li>)}
        </ul>
      </section>

      <section className="knowledge-detail" aria-label={en ? 'Selected Knowledge' : '知识详情'} aria-live="polite">
        {!selected && <p className="knowledge-detail-empty">{en ? 'Select a result to open its Markdown.' : '选择一条结果以打开 Markdown 正文。'}</p>}
        {selected && <>
          <div className="knowledge-detail-heading">
            <div>
              <p className="eyebrow">{en ? 'SELECTED KNOWLEDGE' : '已选择的知识条目'}</p>
              <h2>{selected.title}</h2>
            </div>
            <button type="button" className="knowledge-back" onClick={backToResults}>
              {en ? 'Back to results' : '返回结果'}
            </button>
          </div>
          {detailStatus === 'loading' && <p role="status" className="knowledge-notice">{en ? 'Loading document…' : '正在读取正文…'}</p>}
          {detailStatus === 'error' && <div className="knowledge-error" role="alert">
            <p>{failureMessage(errorStatus, locale)}</p>
            {showSearchAgain && <button type="button" onClick={() => { void search(); }}>{en ? 'Search again' : '重新搜索'}</button>}
          </div>}
          {detail && <>
            <p className={`knowledge-source-status is-${detail.provenance_status}`}>
              {provenanceLabel(detail.provenance_status, locale)}
              {detail.provenance_status === 'unverified' && <span>{en ? '; no verified source link is available.' : '；没有可验证的来源链接。'}</span>}
            </p>
            <section className="knowledge-source-trace" aria-label={en ? 'Verified source trace' : '来源回溯'}>
              <button type="button" onClick={() => void checkSource()} disabled={sourceStatus === 'loading'}>
                {sourceStatus === 'loading' ? (en ? 'Checking source…' : '正在核验来源…') : (en ? 'Check source trace' : '检查来源回溯')}
              </button>
              {sourceStatus === 'error' && <p className="knowledge-error" role="alert">{failureMessage(errorStatus, locale)}</p>}
              {sourceStatus === 'loading' && <p role="status">{en ? 'Requesting Core source verification…' : '正在请求 Core 来源验证结果…'}</p>}
              {source?.status === 'available' && source.provenance_status === 'verified' && <div className="knowledge-source-trace-result">
                <p className="knowledge-source-status is-verified">{en ? 'Core verified the Review source.' : 'Core 已验证此 Review 来源。'}</p>
                <dl>
                  <dt>{en ? 'Review reference' : 'Review 来源路径'}</dt><dd>{source.source.ref}</dd>
                  <dt>{en ? 'Review SHA-256' : 'Review 来源 SHA-256'}</dt><dd><code>{source.source.sha256}</code></dd>
                  <dt>{en ? 'Promote operation' : '入库操作 ID'}</dt><dd><code>{source.source.request_id}</code></dd>
                </dl>
                <a href={`/review?${new URLSearchParams({ review_path: source.source.ref })}`}>
                  {en ? 'Open verified source Review' : '打开已验证的来源 Review'}
                </a>
              </div>}
              {source?.status === 'unavailable' && <p className="knowledge-source-status is-unverified" role="status">
                {en ? 'Core could not verify the source. No source link is available.' : 'Core 无法验证该来源；不提供来源链接。'}
              </p>}
              {source?.status === 'missing' && <p className="knowledge-source-status is-missing" role="status">
                {en ? 'No source reference is recorded for this item.' : '此条目没有来源记录。'}
              </p>}
            </section>
            <div className="knowledge-markdown"><ReviewMarkdown source={detail.content} /></div>
          </>}
        </>}
      </section>
    </div>}
  </section>;
}
