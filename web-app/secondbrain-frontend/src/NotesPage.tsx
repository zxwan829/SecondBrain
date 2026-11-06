import React, { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { MarkdownEditor } from './MarkdownEditor';
import { NotePropertiesPanel } from './NotePropertiesPanel';
import { notesApi, type Note, type NoteCollection, type NotesTrashItem, type VisualAsset, type VisualKind } from './api/notes';
import { defaultExcalidraw, defaultMindMap, visualKindFromFilename, visualLink } from './visualAssets';

const VisualAssetDialog = lazy(() => import('./VisualAssetDialog').then((module) => ({ default: module.VisualAssetDialog })));
const BlockSuiteMarkdownEditor = lazy(() => import('./BlockSuiteMarkdownEditor').then((module) => ({ default: module.BlockSuiteMarkdownEditor })));

type State = '未保存' | '保存中…' | '已保存' | '保存失败' | '版本冲突';
const noteKey = (value: Note) => `${value.collection}:${value.path}`;
const hasOpaqueFrontmatter = (value: string) => /^\ufeff?---\r?\n/.test(value);

export function NotesPage({ onRegisterNavigationGuard, onOpenInboxSource }: { onRegisterNavigationGuard?: (guard: (() => boolean) | null) => void; onOpenInboxSource?: (collection: string, path: string) => void }) {
  const [collections, setCollections] = useState<NoteCollection[]>([]);
  const [collection, setCollection] = useState('drafts');
  const [items, setItems] = useState<{ path: string; title: string }[]>([]);
  const [note, setNote] = useState<Note | null>(null);
  const [content, setContent] = useState('');
  const [editorMode, setEditorMode] = useState<'blocksuite' | 'legacy'>('legacy');
  const [state, setState] = useState<State>('已保存');
  const [message, setMessage] = useState('');
  const blockSuiteFallbackReason = useRef<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [trashView, setTrashView] = useState(false);
  const [trashItems, setTrashItems] = useState<NotesTrashItem[]>([]);
  const [trashLoading, setTrashLoading] = useState(false);
  const [trashOffset, setTrashOffset] = useState(0);
  const [trashHasMore, setTrashHasMore] = useState(false);
  const [restorePreview, setRestorePreview] = useState<{ etag: string; content: string } | null>(null);
  const [visualAsset, setVisualAsset] = useState<VisualAsset | null>(null);
  const [unpersistedVisual, setUnpersistedVisual] = useState<{ note: Note; asset: VisualAsset } | null>(null);
  const [creatingVisual, setCreatingVisual] = useState(false);
  const [savingVisual, setSavingVisual] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  const viewRevision = useRef(0);
  const editSequence = useRef(0);
  const conflictedSave = useRef<{ key: string; revision: number } | null>(null);
  const visualOpenSequence = useRef(0);
  const noteRef = useRef<Note | null>(null);
  const contentRef = useRef('');
  const savedContent = useRef('');
  const visualNavigationRisk = useRef(false);
  const saveQueue = useRef<Promise<void>>(Promise.resolve());
  const pendingSaves = useRef(0);
  const trashIdempotencyKeys = useRef<Record<string, string>>({});

  const setCurrent = (next: Note | null, body = '') => {
    noteRef.current = next;
    contentRef.current = body;
    savedContent.current = body;
    setNote(next); setContent(body);
  };
  const refresh = useCallback(async (target = collection) => {
    try { const result = await notesApi.list(target); setItems(result.items); }
    catch { setItems([]); setMessage('笔记列表暂时无法读取，请检查登录会话和目录授权。'); }
  }, [collection]);
  const canNavigateAway = useCallback(() => {
    if (pendingSaves.current > 0) {
      setMessage('当前笔记正在保存，请等待保存完成后再切换。');
      return false;
    }
    const dirty = (!!noteRef.current && contentRef.current !== savedContent.current)
      || visualNavigationRisk.current || unpersistedVisual !== null;
    return !dirty || window.confirm('当前笔记或图形有尚未保存的修改。离开后这些修改可能丢失，仍要继续吗？');
  }, [unpersistedVisual]);
  const protectUnsaved = canNavigateAway;
  const updateVisualNavigationRisk = useCallback((risk: boolean) => { visualNavigationRisk.current = risk; }, []);
  const beginTransition = () => {
    window.clearTimeout(timer.current);
    viewRevision.current += 1;
    conflictedSave.current = null;
    editSequence.current += 1;
    visualOpenSequence.current += 1;
    setCreatingVisual(false);
    setRestorePreview(null);
    setVisualAsset(null);
    setUnpersistedVisual(null);
    return viewRevision.current;
  };

  useEffect(() => {
    void notesApi.collections().then(({ collections: value }) => {
      setCollections(value); if (value.length) setCollection(value[0].id);
    }).catch(() => setMessage('Notes 尚未配置，或当前登录会话无效。'));
  }, []);
  useEffect(() => {
    onRegisterNavigationGuard?.(canNavigateAway);
    return () => onRegisterNavigationGuard?.(null);
  }, [canNavigateAway, onRegisterNavigationGuard]);
  useEffect(() => { if (collections.some((item) => item.id === collection)) void refresh(collection); }, [collection, collections, refresh]);
  useEffect(() => () => {
    window.clearTimeout(timer.current);
    viewRevision.current += 1;
  }, []);

  const open = async (path: string) => {
    if (!protectUnsaved()) return;
    const revision = beginTransition();
    const targetCollection = collection;
    setLoading(true); setMessage(''); blockSuiteFallbackReason.current = null;
    try {
      const loaded = await notesApi.read(targetCollection, path);
      if (viewRevision.current !== revision) return;
      setCurrent(loaded, loaded.content); setState('已保存'); setEditorMode('legacy');
      setMessage(loaded.read_only ? `此文件含有当前富文本编辑器不能安全往返的语法（${loaded.safety_reasons.join('、')}），已保留原文并设为只读。` : '');
    } catch { if (viewRevision.current === revision) setMessage('笔记读取失败，原有内容未更改。'); }
    finally { if (viewRevision.current === revision) setLoading(false); }
  };

  const save = useCallback((target: Note, body: string, revision: number, sequence: number): Promise<Note | null> => {
    const key = noteKey(target);
    pendingSaves.current += 1;
    setState('保存中…');
    const request = saveQueue.current.catch(() => undefined).then(async () => {
      // A navigation can happen while this save waits behind another request.
      // Never dispatch a queued write for a document that is no longer active.
      if (viewRevision.current !== revision || !noteRef.current || noteKey(noteRef.current) !== key) return null;
      const conflict = conflictedSave.current;
      if (conflict?.revision === revision && conflict.key === key) return null;
      // Use the most recently confirmed ETag for this note. An older response
      // always advances that ETag before a later queued body is sent.
      const current = noteRef.current;
      const basis = current && noteKey(current) === key ? current : target;
      const saved = await notesApi.save(basis, body);
      if (viewRevision.current !== revision || !noteRef.current || noteKey(noteRef.current) !== key) return null;
      noteRef.current = saved;
      savedContent.current = saved.content;
      setNote(saved);
      if (contentRef.current === saved.content && editSequence.current === sequence) {
        setContent(saved.content); setState('已保存'); setMessage('');
      } else {
        setState(pendingSaves.current > 1 ? '保存中…' : '未保存');
      }
      void refresh(target.collection);
      return saved;
    }).catch((error: unknown) => {
      const status = (error as Error & { status?: number }).status;
      const stillViewingNote = viewRevision.current === revision
        && noteRef.current !== null
        && noteKey(noteRef.current) === key;
      // A 412 is authoritative for this note/revision even if BlockSuite
      // emitted another debounced projection while the request was in flight.
      if (stillViewingNote && (status === 412 || editSequence.current === sequence)) {
        if (status === 412) {
          conflictedSave.current = { key, revision };
          window.clearTimeout(timer.current);
        }
        setState(status === 412 ? '版本冲突' : '保存失败');
        setMessage(status === 412 ? '文件已在其他位置修改。当前输入仍保留；请复制未保存内容后重新载入再合并。' : '保存失败。当前输入仍保留，可检查授权后重试。');
      }
      throw error;
    }).finally(() => {
      pendingSaves.current = Math.max(0, pendingSaves.current - 1);
    });
    saveQueue.current = request.then(() => undefined, () => undefined);
    return request;
  }, [refresh]);

  const change = (body: string) => {
    const target = noteRef.current;
    const conflict = conflictedSave.current;
    const alreadyConflicted = !!target
      && conflict?.revision === viewRevision.current
      && conflict.key === noteKey(target);
    contentRef.current = body;
    setContent(body);
    if (alreadyConflicted) return;
    setState('未保存'); setMessage('');
    if (!target || target.read_only) return;
    window.clearTimeout(timer.current);
    const sequence = ++editSequence.current;
    const revision = viewRevision.current;
    timer.current = window.setTimeout(() => { void save(target, body, revision, sequence).catch(() => undefined); }, 900);
  };

  const createDraft = async () => {
    if (!protectUnsaved()) return;
    const revision = beginTransition();
    setLoading(true); setMessage(''); blockSuiteFallbackReason.current = null;
    try {
      const created = await notesApi.create('# 未命名笔记\n\n');
      if (viewRevision.current !== revision) return;
      setCollection('drafts'); setCurrent(created, created.content); setState('已保存'); setEditorMode('legacy');
      void refresh('drafts');
    } catch { if (viewRevision.current === revision) setMessage('Drafts 尚未配置，或创建失败；没有创建笔记。'); }
    finally { if (viewRevision.current === revision) setLoading(false); }
  };

  const selectCollection = (next: string) => {
    if (next === collection || !protectUnsaved()) return;
    beginTransition(); setCollection(next); setCurrent(null); setState('已保存'); setMessage('');
  };
  const pasteImage = async (file: File) => {
    const target = noteRef.current;
    if (!target) throw new Error('请先创建或打开一篇笔记');
    try { const uploaded = await notesApi.upload(target, file); return uploaded.url; }
    catch { setMessage('图片附件未保存；正文仍保留。'); throw new Error('图片上传失败'); }
  };

  const createVisual = async (kind: VisualKind) => {
    const target = noteRef.current;
    if (!target || target.read_only || creatingVisual || state !== '已保存') return;
    const revision = viewRevision.current;
    const body = kind === 'mindmap' ? defaultMindMap() : defaultExcalidraw();
    pendingSaves.current += 1;
    setCreatingVisual(true);
    setMessage('正在创建图形附件…');
    try {
      const created = await notesApi.createVisualAsset(target, kind, body);
      if (viewRevision.current !== revision || !noteRef.current || noteKey(noteRef.current) !== noteKey(target)) return;
      const reference = visualLink(kind, created.filename);
      const current = contentRef.current;
      const nextContent = `${current.trimEnd()}${current.trim() ? '\n\n' : ''}${reference}\n`;
      window.clearTimeout(timer.current);
      contentRef.current = nextContent;
      setContent(nextContent);
      setState('未保存');
      const asset = { filename: created.filename, etag: created.etag, content: body };
      setUnpersistedVisual({ note: target, asset });
      const sequence = ++editSequence.current;
      const saved = await save(target, nextContent, revision, sequence);
      if (!saved) throw new Error('笔记已切换，图形附件已创建但引用尚未保存；请返回原笔记检查。');
      if (viewRevision.current !== revision || !noteRef.current || noteKey(noteRef.current) !== noteKey(target)) {
        throw new Error('笔记已切换，图形附件引用的保存结果未应用到当前页面。');
      }
      setUnpersistedVisual(null);
      setVisualAsset(asset);
      setMessage('图形源文件与 Markdown 相对引用均已保存。');
    } catch (error) {
      if (viewRevision.current === revision) {
        setMessage(error instanceof Error
          ? `图形源文件已创建，但 Markdown 引用未确认保存；正文保留在编辑区。${error.message}`
          : '图形源文件已创建，但 Markdown 引用未确认保存；正文保留在编辑区。');
      }
    } finally {
      pendingSaves.current = Math.max(0, pendingSaves.current - 1);
      if (viewRevision.current === revision) setCreatingVisual(false);
    }
  };

  const retryVisualReference = async () => {
    const pending = unpersistedVisual;
    if (!pending || state !== '保存失败' || !noteRef.current || noteKey(noteRef.current) !== noteKey(pending.note)) return;
    const revision = viewRevision.current;
    try {
      const saved = await save(pending.note, contentRef.current, revision, editSequence.current);
      if (!saved) throw new Error('笔记已切换，保存结果未应用到当前页面。');
      if (viewRevision.current !== revision || !noteRef.current || noteKey(noteRef.current) !== noteKey(pending.note)) {
        throw new Error('笔记已切换，保存结果未应用到当前页面。');
      }
      setUnpersistedVisual(null);
      setVisualAsset(pending.asset);
      setMessage('图形源文件与 Markdown 相对引用均已保存。');
    } catch { /* save() retains the unsaved Markdown and reports the failure. */ }
  };

  const openTrash = async () => {
    if (!protectUnsaved()) return;
    beginTransition();
    setCurrent(null);
    setTrashView(true);
    setMessage('');
    setTrashOffset(0);
    setTrashLoading(true);
    try {
      const result = await notesApi.listTrash(0);
      setTrashItems(result.items);
      setTrashHasMore(result.pagination.has_more);
      if (result.status === 'partial') setMessage('回收站包含待恢复项目；请联系管理员检查恢复状态。');
    } catch (error) {
      setTrashItems([]);
      const status = (error as Error & { status?: number }).status;
      setMessage(status === 501
        ? '回收站尚未配置。笔记未被删除；请先配置隔离的 Trash 存储位置。'
        : status === 401 ? '登录状态已失效，请重新登录后查看回收站。'
          : status === 403 ? '当前登录会话没有读取回收站的权限。'
            : '回收站暂时无法读取；笔记未被删除，请稍后重试。');
    } finally { setTrashLoading(false); }
  };

  const changeTrashPage = async (offset: number) => {
    if (offset < 0 || trashLoading) return;
    setTrashLoading(true); setMessage('');
    try {
      const result = await notesApi.listTrash(offset);
      setTrashItems(result.items);
      setTrashOffset(result.pagination.offset);
      setTrashHasMore(result.pagination.has_more);
      if (result.status === 'partial') setMessage('回收站包含待恢复项目；请联系管理员检查恢复状态。');
    } catch {
      setMessage('回收站页暂时无法读取；当前列表保持不变，请重试。');
    } finally { setTrashLoading(false); }
  };

  const closeTrash = () => {
    beginTransition();
    setTrashView(false);
    setMessage('');
    void refresh(collection);
  };

  const trashSelectedNote = async () => {
    const target = note;
    if (!target || state !== '已保存' || loading || creatingVisual || savingVisual) return;
    const confirmed = window.confirm(`将“${target.path}”移到回收站？笔记可从回收站恢复；共享附件不会删除。`);
    if (!confirmed) return;
    const key = noteKey(target);
    const idempotencyKey = trashIdempotencyKeys.current[key] ?? globalThis.crypto.randomUUID();
    trashIdempotencyKeys.current[key] = idempotencyKey;
    setLoading(true); setMessage(''); blockSuiteFallbackReason.current = null;
    try {
      await notesApi.trash(target, idempotencyKey);
      delete trashIdempotencyKeys.current[key];
      setCurrent(null);
      setMessage('笔记已移到回收站，可在回收站恢复；共享附件未删除。');
      void refresh(target.collection);
    } catch (error) {
      const status = (error as Error & { status?: number }).status;
      setMessage(status === 501 ? '回收站尚未配置，笔记未被删除。'
        : status === 401 ? '登录状态已失效，笔记未被删除。'
          : status === 403 ? '当前会话没有删除此笔记的权限，笔记未被删除。'
            : status === 409 ? '笔记已变化或请求状态不一致，笔记未被覆盖；请刷新后检查。'
              : '移入回收站未能确认完成；笔记内容和附件均未执行清理。请检查回收站后再重试。');
    } finally { setLoading(false); }
  };

  const restoreTrashItem = async (item: NotesTrashItem) => {
    if (item.status !== 'trashed' || trashLoading) return;
    if (!window.confirm(`将“${item.path}”恢复到原目录 ${item.collection}？如果目标已存在，系统会拒绝覆盖。`)) return;
    setTrashLoading(true); setMessage('');
    try {
      await notesApi.restoreTrash(item.trash_id);
      setTrashItems((current) => current.filter((row) => row.trash_id !== item.trash_id));
      setMessage('笔记已恢复到原目录；共享附件未删除。');
      void refresh(item.collection);
    } catch (error) {
      const status = (error as Error & { status?: number }).status;
      setMessage(status === 409 ? '恢复目标已存在，未覆盖任何文件。请先处理同名目标后再重试。'
        : status === 401 ? '登录状态已失效，笔记仍保留在回收站。'
          : status === 403 ? '当前会话没有恢复权限，笔记仍保留在回收站。'
            : status === 503 ? '恢复状态需要检查；没有自动覆盖或清理文件，请联系管理员处理。'
              : '恢复未能确认完成；笔记仍受回收站保护，请刷新状态后重试。');
    } finally { setTrashLoading(false); }
  };

  const openVisual = async (filename: string) => {
    const target = noteRef.current;
    const kind = visualKindFromFilename(filename);
    if (!target || !kind || target.read_only) return;
    const revision = viewRevision.current;
    const sequence = ++visualOpenSequence.current;
    try {
      const asset = await notesApi.readVisualAsset(target, filename);
      if (viewRevision.current !== revision || visualOpenSequence.current !== sequence || !noteRef.current || noteKey(noteRef.current) !== noteKey(target)) return;
      setVisualAsset(asset);
      setMessage('');
    } catch (error) {
      setMessage(error instanceof Error ? `图形附件无法读取：${error.message}` : '图形附件无法读取。');
    }
  };

  const saveVisual = async (body: string) => {
    const target = noteRef.current;
    const asset = visualAsset;
    if (!target || !asset) throw new Error('当前笔记或图形附件已切换，请重新打开附件。');
    const revision = viewRevision.current;
    pendingSaves.current += 1;
    setSavingVisual(true);
    try {
      const result = await notesApi.saveVisualAsset(target, asset, body);
      if (viewRevision.current !== revision || !noteRef.current || noteKey(noteRef.current) !== noteKey(target) || visualAsset?.filename !== asset.filename) {
        throw new Error('笔记或图形附件已切换，保存结果未应用到当前编辑器；请重新打开原笔记核实。');
      }
      setVisualAsset({ ...asset, content: body, etag: result.etag });
      setMessage('图形已保存，可关闭后再次打开继续编辑。');
    } finally {
      pendingSaves.current = Math.max(0, pendingSaves.current - 1);
      if (viewRevision.current === revision) setSavingVisual(false);
    }
  };

  const restore = async () => {
    const target = noteRef.current;
    if (!target) return;
    const targetKey = noteKey(target);
    const revision = viewRevision.current;
    setRestorePreview(null);
    try {
      const result = await notesApi.history(target);
      if (viewRevision.current !== revision || !noteRef.current || noteKey(noteRef.current) !== targetKey) return;
      if (!Array.isArray(result.versions)) throw new Error('历史版本响应格式无效。');
      if (!result.versions.length) { setMessage('暂无可恢复版本。'); return; }
      setRestorePreview(result.versions[result.versions.length - 1]);
      setMessage('已载入最近的历史版本预览；当前正文尚未改变。');
    } catch (reason) {
      const status = typeof reason === 'object' && reason !== null && 'status' in reason
        ? Number((reason as { status?: unknown }).status) : undefined;
      const message = status === 401 ? '登录状态已失效，请重新登录后重试。'
        : status === 403 ? '当前会话没有读取此笔记历史的权限。'
          : status === 404 ? '笔记或历史目标已不存在，请刷新笔记后重试。'
            : status !== undefined && status >= 500 ? '历史服务暂时不可用，请稍后重试。'
              : '无法连接历史服务或响应格式无效，请检查连接后重试。';
      if (viewRevision.current === revision && noteRef.current && noteKey(noteRef.current) === targetKey) setMessage(message);
    }
  };
  const confirmRestore = () => {
    if (!restorePreview || !protectUnsaved()) return;
    change(restorePreview.content);
    setRestorePreview(null);
    setMessage('历史版本已放入编辑区，确认保存前仍可继续修改。');
  };

  return <main className="notes-page">
    <header className="module-header"><div><p className="eyebrow">SECONDBRAIN / NOTES</p><h1>笔记</h1><p className="workspace-subtitle">以 Markdown 文件为正文来源；普通目录仅显示已显式授权的范围。</p></div>
      <div className="notes-header-actions">
        <button type="button" onClick={() => trashView ? closeTrash() : void openTrash()} disabled={trashLoading}>{trashView ? '返回笔记' : '回收站'}</button>
        {!trashView && <button type="button" onClick={() => void createDraft()} disabled={loading}>新建 Draft</button>}
      </div></header>
    {trashView ? <section className="notes-trash" aria-label="回收站">
      <h2>回收站</h2>
      <p>笔记保留在原目录信息中，可恢复到原位置；恢复时不会覆盖已存在的文件，共享附件不会被删除。此处不提供永久删除。</p>
      {trashLoading && <p role="status">正在读取回收站…</p>}
      {trashItems.length === 0 && !trashLoading && !message && <p>回收站为空。</p>}
      <ul>{trashItems.map((item) => <li key={item.trash_id}>
        <div><strong>{item.path}</strong><span>{item.collection} · {new Date(item.trashed_at).toLocaleString()} · {item.status}</span></div>
        {item.status === 'trashed'
          ? <button type="button" onClick={() => void restoreTrashItem(item)} disabled={trashLoading}>恢复到原目录</button>
          : <span role="status">需要检查，暂不可恢复</span>}
      </li>)}</ul>
      <nav aria-label="回收站分页" className="notes-trash-pagination">
        <button type="button" onClick={() => void changeTrashPage(trashOffset - 50)} disabled={trashLoading || trashOffset === 0}>上一页</button>
        <span>第 {Math.floor(trashOffset / 50) + 1} 页</span>
        <button type="button" onClick={() => void changeTrashPage(trashOffset + 50)} disabled={trashLoading || !trashHasMore}>下一页</button>
      </nav>
      {message && <p role="alert">{message}</p>}
    </section> : <div className="notes-layout">
      <aside className="notes-sidebar" aria-label="笔记目录">
        <label htmlFor="notes-collection">笔记目录</label>
        <select id="notes-collection" value={collection} onChange={(event) => selectCollection(event.target.value)}>
          {collections.map((item) => <option key={item.id} value={item.id}>{item.kind === 'drafts' ? 'Drafts' : item.id}</option>)}
        </select>
        <ul>{items.map((item) => <li key={item.path}><button type="button" onClick={() => void open(item.path)}>{item.title}</button></li>)}</ul>
      </aside>
      <section className="notes-document" aria-label="Markdown 笔记编辑区">
        <div className="notes-document-heading">
          <span>{note ? `${note.collection} / ${note.path}` : '选择笔记或新建 Draft'}</span>
          <span role="status" aria-live="polite">{state}</span>
          {note && !note.read_only && <>
            <button type="button" disabled={state !== '已保存' || creatingVisual || savingVisual} onClick={() => void createVisual('mindmap')}>插入思维导图</button>
            <button type="button" disabled={state !== '已保存' || creatingVisual || savingVisual} onClick={() => void createVisual('excalidraw')}>插入自由画板</button>
          </>}
          {note && note.collection === 'drafts' && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(note.path) && onOpenInboxSource && <button type="button" onClick={() => { if (protectUnsaved()) onOpenInboxSource(note.collection, note.path); }}>单来源 Inbox 审批</button>}
          {note && <button type="button" onClick={() => void restore()}>查看可恢复版本</button>}
          {note && <button type="button" onClick={() => void trashSelectedNote()} disabled={state !== '已保存' || loading || creatingVisual || savingVisual || visualAsset !== null || unpersistedVisual !== null}>移到回收站</button>}
        </div>
        {note && !note.read_only && editorMode === 'legacy' && <div className="notes-editor-mode" role="group" aria-label="Markdown 编辑器">
          <button type="button" onClick={() => { blockSuiteFallbackReason.current = null; setMessage(''); setEditorMode('blocksuite'); }}>BlockSuite 编辑器</button>
        </div>}
        {restorePreview && <section className="notes-restore-preview" aria-label="历史版本预览">
          <h2>最近历史版本预览</h2><pre>{restorePreview.content}</pre>
          <button type="button" onClick={() => setRestorePreview(null)}>取消</button>
          <button type="button" onClick={confirmRestore}>使用此版本</button>
        </section>}
        {note && state === '已保存' && !loading && <NotePropertiesPanel key={noteKey(note)} note={note} onSaved={(saved) => {
          setCurrent(saved, saved.content); setState('已保存'); setMessage(''); void refresh(saved.collection);
        }} />}
        {note ? note.read_only || (editorMode === 'legacy' && hasOpaqueFrontmatter(content)) ? <>
          <div className="notes-safety" role="status">{note.read_only
            ? `此文件含有当前富文本编辑器不能安全往返的语法（${note.safety_reasons.join('、')}），原始 Markdown 保留只读。`
            : '此笔记含有不透明 YAML Frontmatter；旧版编辑器保持只读，请切换 BlockSuite 以安全编辑正文。'}</div>
          <pre className="notes-raw-source">{content}</pre>
        </> : editorMode === 'blocksuite' ? <Suspense fallback={<p role="status">正在加载 BlockSuite 编辑器…</p>}><BlockSuiteMarkdownEditor key={`blocksuite:${noteKey(note)}`} value={content} disabled={state === '保存中…' || state === '版本冲突' || state === '保存失败'} onChange={change}
          onFallback={(reason) => { blockSuiteFallbackReason.current = reason ?? null; setEditorMode('legacy'); setMessage('BlockSuite 不支持安全往返此笔记，已保留原文并切回旧版编辑器。'); }} /></Suspense>
          : <MarkdownEditor key={`legacy:${noteKey(note)}`} value={content} disabled={false} onChange={change} onImagePaste={pasteImage}
            onOpenVisualAsset={openVisual}
            assetBase={`/api/notes/${encodeURIComponent(note.collection)}/${note.path.split('/').map(encodeURIComponent).join('/')}`} /> : <p className="notes-empty">先选择一篇已授权 Markdown，或新建 Draft。</p>}
        {message && <p role="alert" data-fallback-reason={blockSuiteFallbackReason.current ?? undefined} className={state === '版本冲突' || state === '保存失败' ? 'notes-error' : 'notes-hint'}>{message}</p>}
        {unpersistedVisual && state === '保存失败' && note && noteKey(note) === noteKey(unpersistedVisual.note) &&
          <button type="button" onClick={() => void retryVisualReference()}>重试保存图形引用</button>}
      </section>
    </div>}
    {visualAsset && <Suspense fallback={<p role="status">正在加载图形编辑器…</p>}>
      <VisualAssetDialog key={`${note ? noteKey(note) : ''}:${visualAsset.filename}`} kind={visualKindFromFilename(visualAsset.filename)!} asset={visualAsset}
        onSave={saveVisual} onClose={() => setVisualAsset(null)} onNavigationRiskChange={updateVisualNavigationRisk} canSave={state === '已保存'} />
    </Suspense>}
  </main>;
}
