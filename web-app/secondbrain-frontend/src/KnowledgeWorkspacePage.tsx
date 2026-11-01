import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { notesApi, type NoteCollection, type NotesBrowseItem, type NotesBrowseResult, type NotesFoldersResult } from './api/notes';
import { ReviewMarkdown } from './ReviewMarkdown';
import { KnowledgePage } from './KnowledgePage';

type Locale = 'zh-CN' | 'en';
type Source = 'knowledge' | 'notes' | 'drafts';
type Failure = Error & { status?: number };

function statusOf(error: unknown): number | null {
  return error && typeof error === 'object' && Number.isInteger((error as Failure).status)
    ? (error as Failure).status! : null;
}

function noteError(status: number | null, locale: Locale): string {
  const en = locale === 'en';
  if (status === 401) return en ? 'Your session expired. Sign in again.' : '登录会话已失效，请重新登录。';
  if (status === 403) return en ? 'This source is not authorized. Its cached contents were cleared.' : '此来源未获授权，已清除该来源的缓存内容。';
  if (status === 404) return en ? 'This folder or note is no longer available.' : '目录或笔记已不可用。';
  if (status === 503) return en ? 'This source is temporarily unavailable. Its cached contents were cleared.' : '此来源暂不可用，已清除该来源的缓存内容。';
  if (status === 502) return en ? 'The source returned an invalid response.' : '来源返回了无法校验的数据。';
  return en ? 'The source could not be loaded. Please retry.' : '来源加载失败，请重试。';
}

function isCollections(value: unknown): value is { collections: NoteCollection[] } {
  if (!value || typeof value !== 'object' || !Array.isArray((value as { collections?: unknown }).collections)) return false;
  return (value as { collections: unknown[] }).collections.every((item) => item && typeof item === 'object'
    && typeof (item as NoteCollection).id === 'string' && (item as NoteCollection).id.length > 0
    && ((item as NoteCollection).kind === 'drafts' || (item as NoteCollection).kind === 'authorized'));
}

function isNote(value: unknown, collection: string, path: string): value is { collection: string; path: string; content: string } {
  if (!value || typeof value !== 'object') return false;
  const note = value as { collection?: unknown; path?: unknown; content?: unknown; read_only?: unknown };
  return note.collection === collection && note.path === path && typeof note.content === 'string' && typeof note.read_only === 'boolean';
}

export function KnowledgeWorkspacePage({ locale, onGlobalAuthFailure }: { locale: Locale; onGlobalAuthFailure: () => void }) {
  const en = locale === 'en';
  const [source, setSource] = useState<Source>('knowledge');
  const [collections, setCollections] = useState<NoteCollection[]>([]);
  const [collectionId, setCollectionId] = useState('');
  const [path, setPath] = useState('');
  const [browseOffset, setBrowseOffset] = useState(0);
  const [folders, setFolders] = useState<NotesFoldersResult | null>(null);
  const [browse, setBrowse] = useState<NotesBrowseResult | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tagMatch, setTagMatch] = useState<'and' | 'or'>('and');
  const [showAllTags, setShowAllTags] = useState(false);
  const [selected, setSelected] = useState<NotesBrowseItem | null>(null);
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<number | null>(null);
  const [detailError, setDetailError] = useState<number | null>(null);
  const controller = useRef<AbortController | null>(null);
  const sequence = useRef(0);
  const detailController = useRef<AbortController | null>(null);
  const detailSequence = useRef(0);

  const invalidate = useCallback(() => {
    sequence.current += 1;
    controller.current?.abort();
    controller.current = null;
    detailSequence.current += 1;
    detailController.current?.abort();
    detailController.current = null;
  }, []);

  const clearSource = useCallback(() => {
    invalidate();
    setCollections([]); setCollectionId(''); setPath('');
    setBrowseOffset(0);
    setFolders(null); setBrowse(null); setSelected(null); setContent('');
    setSelectedTags([]); setTagMatch('and'); setShowAllTags(false);
    setBusy(false); setError(null); setDetailError(null);
  }, [invalidate]);

  useEffect(() => () => invalidate(), [invalidate]);

  const collection = useMemo(() => collections.find((item) => item.id === collectionId &&
    (source === 'drafts' ? item.kind === 'drafts' : item.kind === 'authorized')), [collections, collectionId, source]);

  const loadCollections = useCallback(async () => {
    invalidate(); clearSource();
    const current = ++sequence.current;
    const request = new AbortController(); controller.current = request;
    setBusy(true);
    try {
      const result: unknown = await notesApi.collections(request.signal);
      if (request.signal.aborted || current !== sequence.current) return;
      if (!isCollections(result)) throw Object.assign(new Error('Invalid collection response'), { status: 502 });
      const matches = result.collections.filter((item) => source === 'drafts' ? item.kind === 'drafts' : item.kind === 'authorized');
      setCollections(result.collections); setCollectionId(matches[0]?.id ?? ''); setError(null);
    } catch (reason) {
      if (request.signal.aborted || current !== sequence.current) return;
      const status = statusOf(reason); setCollections([]); setError(status);
      if (status === 401) onGlobalAuthFailure();
    } finally {
      if (!request.signal.aborted && current === sequence.current) setBusy(false);
    }
  }, [clearSource, invalidate, onGlobalAuthFailure, source]);

  useEffect(() => {
    clearSource();
    if (source !== 'knowledge') void loadCollections();
    return () => invalidate();
  }, [source, clearSource, loadCollections, invalidate]);

  const loadFolder = useCallback(async (targetPath: string, targetCollection = collectionId, offset = 0,
    tags: string[] = [], match: 'and' | 'or' = 'and') => {
    if (!targetCollection) return;
    controller.current?.abort(); detailController.current?.abort();
    detailSequence.current += 1; detailController.current = null;
    const request = new AbortController(); controller.current = request;
    const current = ++sequence.current;
    setBusy(true); setPath(targetPath); setFolders(null); setBrowse(null); setSelected(null); setContent('');
    setBrowseOffset(offset);
    setSelectedTags(tags); setTagMatch(match);
    setError(null); setDetailError(null);
    try {
      const [folderResult, browseResult] = await Promise.all([
        notesApi.folders(targetCollection, targetPath, request.signal),
        notesApi.browse(targetCollection, targetPath, offset, request.signal, tags, match),
      ]);
      if (request.signal.aborted || current !== sequence.current) return;
      setFolders(folderResult); setBrowse(browseResult);
    } catch (reason) {
      if (request.signal.aborted || current !== sequence.current) return;
      const status = statusOf(reason); setFolders(null); setBrowse(null); setError(status);
      if (status === 401) { clearSource(); onGlobalAuthFailure(); }
      else if (status === 403 || status === 503) { setSelected(null); setContent(''); }
    } finally {
      if (!request.signal.aborted && current === sequence.current) setBusy(false);
    }
  }, [clearSource, collectionId, onGlobalAuthFailure]);

  const loadNewFolder = (targetPath: string, targetCollection = collectionId) => {
    setShowAllTags(false);
    void loadFolder(targetPath, targetCollection, 0, [], 'and');
  };

  const toggleTag = (tag: string) => {
    const next = selectedTags.includes(tag) ? selectedTags.filter((item) => item !== tag) : [...selectedTags, tag];
    if (next.length > 12) return;
    void loadFolder(path, collectionId, 0, next, tagMatch);
  };

  const changeCollection = (nextCollection: string) => {
    if (nextCollection === collectionId) return;
    invalidate();
    setCollectionId(nextCollection); setPath(''); setBrowseOffset(0);
    setFolders(null); setBrowse(null); setSelected(null); setContent('');
    setSelectedTags([]); setTagMatch('and'); setShowAllTags(false);
    setError(null); setDetailError(null); setBusy(true);
  };

  useEffect(() => {
    if (source !== 'knowledge' && collection) void loadFolder('', collection.id);
  }, [source, collection?.id, loadFolder]);

  const openNote = async (item: NotesBrowseItem) => {
    if (!collection) return;
    detailController.current?.abort();
    const request = new AbortController(); detailController.current = request;
    const current = ++detailSequence.current;
    setSelected(item); setContent(''); setDetailError(null);
    try {
      const result: unknown = await notesApi.read(collection.id, item.path, request.signal);
      if (request.signal.aborted || current !== detailSequence.current) return;
      if (!isNote(result, collection.id, item.path)) throw Object.assign(new Error('Invalid note response'), { status: 502 });
      setContent(result.content);
    } catch (reason) {
      if (request.signal.aborted || current !== detailSequence.current) return;
      const status = statusOf(reason); setSelected(null); setContent(''); setDetailError(status);
      if (status === 401) { clearSource(); onGlobalAuthFailure(); }
      else if (status === 403 || status === 503) { setBrowse(null); setFolders(null); }
    }
  };

  const tabs: Array<{ id: Source; label: string }> = [
    { id: 'knowledge', label: en ? 'Knowledge' : '知识库' },
    { id: 'notes', label: en ? 'Notes' : '普通笔记' },
    { id: 'drafts', label: en ? 'Drafts' : '草稿' },
  ];

  return <section className="knowledge-workspace">
    <header className="knowledge-workspace-header">
      <div><p className="eyebrow">{en ? 'LIBRARY' : '资料库'}</p><h1>{en ? 'Knowledge workspace' : '知识工作区'}</h1>
        <p>{en ? 'Browse each source within its own access and write boundary.' : '各来源保持独立的身份、权限与写入边界。'}</p></div>
      <nav className="knowledge-workspace-tabs" aria-label={en ? 'Library source' : '资料来源'}>
        {tabs.map((tab) => <button key={tab.id} type="button" aria-pressed={source === tab.id} onClick={() => { if (source !== tab.id) { clearSource(); setSource(tab.id); } }}>{tab.label}</button>)}
      </nav>
    </header>
    {source === 'knowledge' ? <KnowledgePage locale={locale} onGlobalAuthFailure={onGlobalAuthFailure} /> : <section className="notes-read-browser">
      <header className="notes-read-header">
        <div><h2>{source === 'drafts' ? (en ? 'Drafts' : '草稿') : (en ? 'Authorized Notes' : '已授权笔记')}</h2>
          <p>{en ? 'Read-only. Selection and content are not persisted.' : '只读浏览；选中项与正文不会被持久化。'}</p></div>
        {source === 'notes' && collections.filter((item) => item.kind === 'authorized').length > 1 && <label>{en ? 'Collection' : '目录'}
          <select value={collectionId} onChange={(event) => changeCollection(event.target.value)}>
            {collections.filter((item) => item.kind === 'authorized').map((item) => <option key={item.id} value={item.id}>{item.id}</option>)}
          </select></label>}
      </header>
      {error !== null && <div role="alert" className="knowledge-error"><p>{noteError(error, locale)}</p><button type="button" onClick={() => collection ? void loadFolder(path, collection.id, browseOffset, selectedTags, tagMatch) : void loadCollections()}>{en ? 'Retry' : '重试'}</button></div>}
      {!error && !collection && !busy && <p className="knowledge-empty">{source === 'drafts' ? (en ? 'No Drafts source is available.' : '当前没有可浏览的草稿来源。') : (en ? 'No authorized Notes source is available.' : '当前没有已授权的普通笔记来源。')}</p>}
      {busy && <p role="status">{en ? 'Loading source…' : '正在读取来源…'}</p>}
      {collection && <div className="notes-read-grid">
        <aside className="notes-read-folders" aria-label={en ? 'Folders' : '文件夹'}>
          <button type="button" aria-current={path === '' ? 'page' : undefined} onClick={() => loadNewFolder('')}>{en ? 'Root' : '根目录'}</button>
          {folders?.folders.map((folder) => <button key={folder.path} type="button" aria-current={path === folder.path ? 'page' : undefined} onClick={() => loadNewFolder(folder.path)}>{folder.name}</button>)}
          {folders?.status === 'partial' && <small role="status">{en ? 'Folder listing is partial.' : '目录列表不完整。'}</small>}
        </aside>
        <section className="notes-read-content" aria-label={en ? 'Notes' : '笔记列表'}>
          <nav className="notes-read-breadcrumb" aria-label={en ? 'Current folder' : '当前位置'}>
            <button type="button" onClick={() => loadNewFolder('')}>{en ? 'Root' : '根目录'}</button>
            {path.split('/').filter(Boolean).map((segment, index, parts) => {
              const target = parts.slice(0, index + 1).join('/');
              return <React.Fragment key={target}><span aria-hidden="true">/</span><button type="button" aria-current={index === parts.length - 1 ? 'page' : undefined} onClick={() => loadNewFolder(target)}>{segment}</button></React.Fragment>;
            })}
          </nav>
          {browse?.status === 'partial' && <p role="status" className="knowledge-notice">{browse.scan.complete
            ? (en ? 'Some note metadata or tag counts are incomplete; unsupported notes remain visible.' : '部分笔记元数据或标签计数不完整；无法识别元数据的笔记仍会显示。')
            : (en ? 'This bounded folder scan is partial; document totals may be incomplete.' : '本次有界目录扫描不完整，文档总数可能不完整。')}</p>}
          {browse && source === 'notes' && <>
            <div className="knowledge-folder-heading"><h3>{path || (en ? 'All Notes' : '全部普通笔记')}</h3>
              <span>{browse.total_complete ? browse.total : `${browse.total}+`}</span></div>
            <div className="knowledge-tag-bar" aria-label={en ? 'Filter Notes by tags' : '按标签筛选普通笔记'}>
              <strong>{en ? 'Tags' : '标签'}</strong>
              {browse.tag_facets.length === 0 && <span>{en ? 'No supported frontmatter tags found.' : '没有发现可识别的 Frontmatter 标签。'}</span>}
              {(showAllTags ? browse.tag_facets : browse.tag_facets.slice(0, 10)).map((facet) => <label key={facet.name}>
                <input type="checkbox" checked={selectedTags.includes(facet.name)} disabled={!selectedTags.includes(facet.name) && selectedTags.length >= 12}
                  onChange={() => toggleTag(facet.name)} />
                <span>{facet.name}</span><small>{facet.count_complete ? facet.count : `${facet.count}+`}</small>
              </label>)}
              {browse.tag_facets.length > 10 && <button type="button" onClick={() => setShowAllTags((current) => !current)}>
                {showAllTags ? (en ? 'Show fewer' : '收起标签') : (en ? `Show all (${browse.tag_facets.length})` : `显示全部（${browse.tag_facets.length}）`)}
              </button>}
              {browse.tag_facets_complete === false && <small role="status">{en ? 'Tag list is incomplete.' : '标签列表不完整。'}</small>}
              {selectedTags.length > 1 && <label className="knowledge-match-mode">{en ? 'Match' : '匹配'}
                <select aria-label={en ? 'Tag match mode' : '标签匹配方式'} value={tagMatch}
                  onChange={(event) => void loadFolder(path, collection.id, 0, selectedTags, event.target.value as 'and' | 'or')}>
                  <option value="and">AND</option><option value="or">OR</option>
                </select>
              </label>}
            </div>
          </>}
          {browse?.items.map((item) => <button className="notes-read-item" key={`${source}:${collection.id}:${item.path}`} type="button" aria-pressed={selected?.path === item.path} onClick={() => void openNote(item)}>
            <strong>{item.title}</strong><small>{item.path}</small>
            {source === 'notes' && <small>{item.metadata_status === 'unsupported' ? (en ? 'Tags unavailable: unsupported metadata' : '标签不可用：元数据格式不支持') : item.tags?.join(' · ') || (en ? 'No tags' : '无标签')}</small>}
          </button>)}
          {browse && browse.items.length === 0 && <p className="knowledge-empty">{en ? 'No readable Markdown files in this folder.' : '此目录没有可读取的 Markdown 文件。'}</p>}
          {browse?.next_offset !== null && browse?.next_offset !== undefined && <button type="button" onClick={() => void loadFolder(path, collection.id, browse.next_offset!, selectedTags, tagMatch)}>{en ? 'Next page' : '下一页'}</button>}
          {detailError !== null && <div role="alert" className="knowledge-error">{noteError(detailError, locale)}</div>}
          {selected && content && <article className="notes-read-detail"><h3>{selected.title}</h3><p>{selected.path}</p><ReviewMarkdown source={content} preserveLines /></article>}
        </section>
      </div>}
    </section>}
  </section>;
}
