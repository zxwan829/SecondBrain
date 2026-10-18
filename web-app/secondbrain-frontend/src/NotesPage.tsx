import React, { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { MarkdownEditor } from './MarkdownEditor';
import { notesApi, type Note, type NoteCollection, type VisualAsset, type VisualKind } from './api/notes';
import { defaultExcalidraw, defaultMindMap, visualKindFromFilename, visualLink } from './visualAssets';

const VisualAssetDialog = lazy(() => import('./VisualAssetDialog').then((module) => ({ default: module.VisualAssetDialog })));

type State = '未保存' | '保存中…' | '已保存' | '保存失败' | '版本冲突';
const noteKey = (value: Note) => `${value.collection}:${value.path}`;

export function NotesPage({ onRegisterNavigationGuard, onOpenInboxSource }: { onRegisterNavigationGuard?: (guard: (() => boolean) | null) => void; onOpenInboxSource?: (collection: string, path: string) => void }) {
  const [collections, setCollections] = useState<NoteCollection[]>([]);
  const [collection, setCollection] = useState('drafts');
  const [items, setItems] = useState<{ path: string; title: string }[]>([]);
  const [note, setNote] = useState<Note | null>(null);
  const [content, setContent] = useState('');
  const [state, setState] = useState<State>('已保存');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [restorePreview, setRestorePreview] = useState<{ etag: string; content: string } | null>(null);
  const [visualAsset, setVisualAsset] = useState<VisualAsset | null>(null);
  const [unpersistedVisual, setUnpersistedVisual] = useState<{ note: Note; asset: VisualAsset } | null>(null);
  const [creatingVisual, setCreatingVisual] = useState(false);
  const [savingVisual, setSavingVisual] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  const viewRevision = useRef(0);
  const editSequence = useRef(0);
  const visualOpenSequence = useRef(0);
  const noteRef = useRef<Note | null>(null);
  const contentRef = useRef('');
  const savedContent = useRef('');
  const visualNavigationRisk = useRef(false);
  const saveQueue = useRef<Promise<void>>(Promise.resolve());
  const pendingSaves = useRef(0);

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
    setLoading(true); setMessage('');
    try {
      const loaded = await notesApi.read(targetCollection, path);
      if (viewRevision.current !== revision) return;
      setCurrent(loaded, loaded.content); setState('已保存');
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
      if (viewRevision.current === revision && editSequence.current === sequence) {
        const status = (error as Error & { status?: number }).status;
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
    contentRef.current = body;
    setContent(body); setState('未保存'); setMessage('');
    const target = noteRef.current;
    if (!target || target.read_only) return;
    window.clearTimeout(timer.current);
    const sequence = ++editSequence.current;
    const revision = viewRevision.current;
    timer.current = window.setTimeout(() => { void save(target, body, revision, sequence).catch(() => undefined); }, 900);
  };

  const createDraft = async () => {
    if (!protectUnsaved()) return;
    const revision = beginTransition();
    setLoading(true); setMessage('');
    try {
      const created = await notesApi.create('# 未命名笔记\n\n');
      if (viewRevision.current !== revision) return;
      setCollection('drafts'); setCurrent(created, created.content); setState('已保存');
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
    try {
      const result = await notesApi.history(target);
      if (!result.versions.length) { setMessage('暂无可恢复版本。'); return; }
      setRestorePreview(result.versions[result.versions.length - 1]);
      setMessage('已载入最近的历史版本预览；当前正文尚未改变。');
    } catch { setMessage('历史版本读取失败。'); }
  };
  const confirmRestore = () => {
    if (!restorePreview || !protectUnsaved()) return;
    change(restorePreview.content);
    setRestorePreview(null);
    setMessage('历史版本已放入编辑区，确认保存前仍可继续修改。');
  };

  return <main className="notes-page">
    <header className="module-header"><div><p className="eyebrow">SECONDBRAIN / NOTES</p><h1>笔记</h1><p className="workspace-subtitle">以 Markdown 文件为正文来源；普通目录仅显示已显式授权的范围。</p></div>
      <button type="button" onClick={() => void createDraft()} disabled={loading}>新建 Draft</button></header>
    <div className="notes-layout">
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
        </div>
        {restorePreview && <section className="notes-restore-preview" aria-label="历史版本预览">
          <h2>最近历史版本预览</h2><pre>{restorePreview.content}</pre>
          <button type="button" onClick={() => setRestorePreview(null)}>取消</button>
          <button type="button" onClick={confirmRestore}>使用此版本</button>
        </section>}
        {note ? note.read_only ? <>
          <div className="notes-safety" role="status">此文件含有当前富文本编辑器不能安全往返的语法（{note.safety_reasons.join('、')}），原始 Markdown 保留只读。</div>
          <pre className="notes-raw-source">{content}</pre>
        </> : <MarkdownEditor key={noteKey(note)} value={content} disabled={false} onChange={change} onImagePaste={pasteImage}
          onOpenVisualAsset={openVisual}
          assetBase={`/api/notes/${encodeURIComponent(note.collection)}/${note.path.split('/').map(encodeURIComponent).join('/')}`} /> : <p className="notes-empty">先选择一篇已授权 Markdown，或新建 Draft。</p>}
        {message && <p role="alert" className={state === '版本冲突' || state === '保存失败' ? 'notes-error' : 'notes-hint'}>{message}</p>}
        {unpersistedVisual && state === '保存失败' && note && noteKey(note) === noteKey(unpersistedVisual.note) &&
          <button type="button" onClick={() => void retryVisualReference()}>重试保存图形引用</button>}
      </section>
    </div>
    {visualAsset && <Suspense fallback={<p role="status">正在加载图形编辑器…</p>}>
      <VisualAssetDialog key={`${note ? noteKey(note) : ''}:${visualAsset.filename}`} kind={visualKindFromFilename(visualAsset.filename)!} asset={visualAsset}
        onSave={saveVisual} onClose={() => setVisualAsset(null)} onNavigationRiskChange={updateVisualNavigationRisk} canSave={state === '已保存'} />
    </Suspense>}
  </main>;
}
