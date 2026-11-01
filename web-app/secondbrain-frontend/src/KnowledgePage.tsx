import React, { useEffect, useRef, useState } from 'react';
import { knowledgeApi, KnowledgeApiError, type KnowledgeBrowseItem, type KnowledgeBrowseResult, type KnowledgeDetail, type KnowledgeFolder, type KnowledgeSearchItem, type KnowledgeSource } from './api/knowledge';
import { ReviewMarkdown } from './ReviewMarkdown';

type Locale = 'zh-CN' | 'en';
type SearchStatus = 'idle' | 'loading' | 'ready' | 'error';
type DetailStatus = 'idle' | 'loading' | 'ready' | 'error';
type SourceStatus = 'idle' | 'loading' | 'ready' | 'error';
type BrowseStatus = 'idle' | 'loading' | 'ready' | 'error';
type SelectedKnowledgeItem = Pick<KnowledgeSearchItem, 'id' | 'title' | 'updated'> & Partial<Pick<KnowledgeSearchItem, 'snippet' | 'match' | 'provenance_status'>>;

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
  const [selected, setSelected] = useState<SelectedKnowledgeItem | null>(null);
  const [detail, setDetail] = useState<KnowledgeDetail | null>(null);
  const [source, setSource] = useState<KnowledgeSource | null>(null);
  const [sourceStatus, setSourceStatus] = useState<SourceStatus>('idle');
  const [searchStatus, setSearchStatus] = useState<SearchStatus>('idle');
  const [detailStatus, setDetailStatus] = useState<DetailStatus>('idle');
  const [partial, setPartial] = useState(false);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [folderPath, setFolderPath] = useState('');
  const [folderTree, setFolderTree] = useState<Record<string, KnowledgeFolder[]>>({});
  const [folderTreePartial, setFolderTreePartial] = useState<Record<string, boolean>>({});
  const [folderTreeError, setFolderTreeError] = useState<number | null>(null);
  const [expandedFolders, setExpandedFolders] = useState<string[]>([]);
  const [browse, setBrowse] = useState<KnowledgeBrowseResult | null>(null);
  const [browseStatus, setBrowseStatus] = useState<BrowseStatus>('idle');
  const [browseError, setBrowseError] = useState<number | null>(null);
  const [browseTags, setBrowseTags] = useState<string[]>([]);
  const [tagMatch, setTagMatch] = useState<'and' | 'or'>('and');
  const [browseOffset, setBrowseOffset] = useState(0);
  const activeRequest = useRef<AbortController | null>(null);
  const requestSequence = useRef(0);
  const browseRequest = useRef<AbortController | null>(null);
  const browseSequence = useRef(0);

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

  useEffect(() => () => {
    invalidateRequests();
    browseRequest.current?.abort();
    browseSequence.current += 1;
  }, []);

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

  async function openItem(item: SelectedKnowledgeItem) {
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
        setBrowse(null);
        setBrowseStatus('error');
        setBrowseError(status);
        setSearchStatus('idle');
      }
    }
  }

  async function loadFolder(path: string, tags = browseTags, match = tagMatch, offset = 0) {
    invalidateRequests();
    browseRequest.current?.abort();
    const controller = new AbortController();
    browseRequest.current = controller;
    const sequence = ++browseSequence.current;
    setFolderPath(path);
    setBrowseTags(tags);
    setTagMatch(match);
    setBrowseOffset(offset);
    setBrowse(null);
    setBrowseStatus('loading');
    setBrowseError(null);
    setSelected(null);
    setDetail(null);
    setSource(null);
    setDetailStatus('idle');
    setSourceStatus('idle');
    try {
      const [folders, result] = await Promise.all([
        knowledgeApi.folders(path, controller.signal),
        knowledgeApi.browse(path, tags, match, offset, controller.signal),
      ]);
      if (sequence !== browseSequence.current || controller.signal.aborted) return;
      setFolderTree((current) => ({ ...current, [path]: folders.folders }));
      setFolderTreePartial((current) => ({ ...current, [path]: folders.status === 'partial' }));
      setBrowse(result);
      setBrowseStatus('ready');
    } catch (error) {
      if (sequence !== browseSequence.current || controller.signal.aborted) return;
      setBrowse(null);
      setBrowseStatus('error');
      setBrowseError(error instanceof KnowledgeApiError ? error.status : null);
      if (error instanceof KnowledgeApiError && [401, 403, 503].includes(error.status)) {
        setFolderTree({});
        setItems([]);
        setSearchStatus('idle');
        setErrorStatus(error.status);
      }
    }
  }

  function selectFolder(path: string) {
    void loadFolder(path, [], 'and', 0);
  }

  async function toggleFolder(path: string) {
    if (expandedFolders.includes(path)) {
      setExpandedFolders((current) => current.filter((item) => item !== path));
      return;
    }
    setExpandedFolders((current) => [...current, path]);
    if (folderTree[path]) return;
    const controller = new AbortController();
    try {
      const result = await knowledgeApi.folders(path, controller.signal);
      setFolderTree((current) => ({ ...current, [path]: result.folders }));
      setFolderTreePartial((current) => ({ ...current, [path]: result.status === 'partial' }));
      setFolderTreeError(null);
    } catch (error) {
      const status = error instanceof KnowledgeApiError ? error.status : null;
      setFolderTreeError(status === 401 || status === 403 || status === 503 ? null : status);
      if (status === 401 || status === 403 || status === 503) {
        setFolderTree({});
        setFolderTreePartial({});
        setFolderTreePartial({});
        setBrowse(null);
        setBrowseStatus('error');
        setBrowseError(status);
        setItems([]);
        setSelected(null);
        setDetail(null);
        setSearchStatus('idle');
        setErrorStatus(status);
      }
    }
  }

  function toggleTag(tag: string) {
    const next = browseTags.includes(tag) ? browseTags.filter((item) => item !== tag) : [...browseTags, tag];
    void loadFolder(folderPath, next, tagMatch, 0);
  }

  useEffect(() => { void loadFolder(''); }, []);

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

  function renderFolderTree(parent: string): React.ReactNode {
    return (folderTree[parent] ?? []).map((folder) => <div className="knowledge-folder-node" key={folder.path}>
      <div className="knowledge-folder-row">
        <button type="button" aria-expanded={expandedFolders.includes(folder.path)} aria-label={`${expandedFolders.includes(folder.path) ? 'Collapse' : 'Expand'} ${folder.name}`} onClick={() => void toggleFolder(folder.path)}>{expandedFolders.includes(folder.path) ? '−' : '+'}</button>
        <button type="button" aria-current={folderPath === folder.path ? 'page' : undefined} onClick={() => selectFolder(folder.path)}>{folder.name}</button>
      </div>
      {expandedFolders.includes(folder.path) && <div className="knowledge-folder-children">{renderFolderTree(folder.path)}</div>}
    </div>);
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

    <section className="knowledge-browser" aria-label={en ? 'Browse Knowledge folders and tags' : '按文件夹和标签浏览知识'}>
      <header><div><h2>{en ? 'Browse folders' : '浏览文件夹'}</h2><p>{en ? 'Folders and tags come from configured Knowledge Markdown.' : '文件夹和标签来自已配置知识库中的 Markdown。'}</p></div></header>
      <div className="knowledge-browser-grid">
        <nav className="knowledge-folder-tree" aria-label={en ? 'Knowledge folders' : '知识库文件夹'}>
          <button type="button" aria-current={folderPath === '' ? 'page' : undefined} onClick={() => selectFolder('')}>{en ? 'All Knowledge' : '全部知识'}</button>
          {renderFolderTree('')}
          {folderTreeError !== null && <p className="knowledge-error" role="alert">{failureMessage(folderTreeError, locale)}</p>}
        </nav>
        <div className="knowledge-browser-content">
          {browseStatus === 'loading' && <p role="status" className="knowledge-notice">{en ? 'Loading folder…' : '正在读取文件夹…'}</p>}
          {browseStatus === 'error' && <div className="knowledge-error" role="alert"><p>{failureMessage(browseError, locale)}</p><button type="button" onClick={() => void loadFolder(folderPath, browseTags, tagMatch, browseOffset)}>{en ? 'Retry' : '重试'}</button></div>}
          {browse?.status === 'partial' && <p role="status" className="knowledge-notice">{en ? 'Some metadata or counts are incomplete because of unreadable files or safety limits.' : '部分元数据或计数不完整，原因可能是文件不可读或达到安全扫描上限。'}</p>}
          {folderTreePartial[folderPath] && <p role="status" className="knowledge-notice">{en ? 'The folder list is incomplete because of unreadable entries or a safety limit.' : '文件夹列表因不可读条目或安全扫描上限而不完整。'}</p>}
          {browse && <>
            <div className="knowledge-folder-heading"><h3>{folderPath || (en ? 'All Knowledge' : '全部知识')}</h3><span>{browse.total_complete ? browse.total : `${browse.total}+`}</span></div>
            <div className="knowledge-tag-bar" aria-label={en ? 'Filter by tags' : '按标签筛选'}>
              <strong>{en ? 'Tags' : '标签'}</strong>
              {browse.tag_facets.length === 0 && <span>{en ? 'No frontmatter tags found.' : '没有发现 Frontmatter 标签。'}</span>}
              {browse.tag_facets.map((facet) => <label key={facet.name}>
                <input type="checkbox" checked={browseTags.includes(facet.name)} onChange={() => toggleTag(facet.name)} />
                <span>{facet.name}</span><small>{facet.count_complete ? facet.count : `${facet.count}+`}</small>
              </label>)}
              {browseTags.length > 1 && <label className="knowledge-match-mode">{en ? 'Match' : '匹配'}
                <select value={tagMatch} onChange={(event) => void loadFolder(folderPath, browseTags, event.target.value as 'and' | 'or', 0)}>
                  <option value="and">AND</option><option value="or">OR</option>
                </select>
              </label>}
            </div>
            {browse.items.length === 0 ? <p className="knowledge-empty" role="status">{en ? 'No documents match this folder and tag selection.' : '此文件夹及标签条件下没有匹配文档。'}</p> : <ul className="knowledge-browse-list">
              {browse.items.map((item: KnowledgeBrowseItem) => <li key={item.id}>
                <button type="button" className={`knowledge-result${selected?.id === item.id ? ' is-selected' : ''}`} aria-pressed={selected?.id === item.id} onClick={() => void openItem(item)}>
                  <strong>{item.title}</strong><span>{item.path}</span><small>{item.updated}</small>
                  <small>{item.metadata_status === 'unsupported' ? (en ? 'Tags unavailable: unsupported metadata' : '标签不可用：元数据格式不支持') : item.tags.join(' · ') || (en ? 'No tags' : '无标签')}</small>
                </button>
              </li>)}
            </ul>}
            <div className="knowledge-pagination">
              <button type="button" disabled={browseOffset === 0 || browseStatus === 'loading'} onClick={() => void loadFolder(folderPath, browseTags, tagMatch, Math.max(0, browseOffset - browse.limit))}>{en ? 'Previous' : '上一页'}</button>
              <span>{browse.total_complete ? `${browseOffset + (browse.items.length ? 1 : 0)}–${browseOffset + browse.items.length} / ${browse.total}` : `${browseOffset + 1}–${browseOffset + browse.items.length} / ${browse.total}+`}</span>
              <button type="button" disabled={browse.next_offset === null || browseStatus === 'loading'} onClick={() => browse.next_offset !== null && void loadFolder(folderPath, browseTags, tagMatch, browse.next_offset)}>{en ? 'Next' : '下一页'}</button>
            </div>
          </>}
        </div>
      </div>
    </section>

    {searchStatus === 'loading' && <p className="knowledge-notice" role="status">{en ? 'Searching Knowledge…' : '正在搜索知识库…'}</p>}
    {searchStatus === 'error' && <p className="knowledge-error" role="alert">{failureMessage(errorStatus, locale)}</p>}
    {partial && <p className="knowledge-notice" role="status">{en ? 'Results are partial because the search reached a safety limit.' : '搜索受安全上限约束，当前结果不完整。'}</p>}
    {searchStatus === 'ready' && detailStatus !== 'error' && items.length === 0 && <p className="knowledge-empty" role="status">{en ? 'No matching Knowledge found.' : '没有找到匹配的知识条目。'}</p>}
    {detailStatus === 'error' && !selected && <p className="knowledge-error" role="alert">{failureMessage(errorStatus, locale)}</p>}

    {(items.length > 0 || (selected !== null && !items.some((item) => item.id === selected.id))) && <div className={`knowledge-results-grid${items.length === 0 ? ' knowledge-selected-only' : ''}`}>
      {items.length > 0 && <>
      <section className="knowledge-results" aria-label={en ? 'Search results' : '搜索结果'}>
        <h2>{en ? 'Results' : '搜索结果'} <span>{items.length}</span></h2>
        <ul>
          {items.map((item) => <li key={item.id}>
            <button type="button" className={`knowledge-result${selected?.id === item.id ? ' is-selected' : ''}`}
              aria-pressed={selected?.id === item.id} onClick={() => { void openItem(item); }}>
              <strong>{item.title}</strong>
              {item.snippet && <span>{item.snippet}</span>}
              <small>{item.match ? `${item.match === 'title' ? (en ? 'Title match' : '标题匹配') : (en ? 'Content match' : '正文匹配')} · ` : ''}{item.updated}</small>
              {item.provenance_status && <small className={`knowledge-provenance is-${item.provenance_status}`}>{provenanceLabel(item.provenance_status, locale)}</small>}
            </button>
          </li>)}
        </ul>
      </section>
      </>}

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
