import React, { useCallback, useEffect, useRef, useState } from 'react';
import { MarkdownEditor } from './MarkdownEditor';
import { notesApi, type Note, type NoteCollection } from './api/notes';

type State = '未保存' | '保存中…' | '已保存' | '保存失败' | '版本冲突';
const noteKey = (value: Note) => `${value.collection}:${value.path}`;

export function NotesPage() {
  const [collections, setCollections] = useState<NoteCollection[]>([]);
  const [collection, setCollection] = useState('drafts');
  const [items, setItems] = useState<{ path: string; title: string }[]>([]);
  const [note, setNote] = useState<Note | null>(null);
  const [content, setContent] = useState('');
  const [state, setState] = useState<State>('已保存');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [restorePreview, setRestorePreview] = useState<{ etag: string; content: string } | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const viewRevision = useRef(0);
  const editSequence = useRef(0);
  const noteRef = useRef<Note | null>(null);
  const contentRef = useRef('');
  const savedContent = useRef('');
  const saveQueue = useRef<Promise<void>>(Promise.resolve());

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
  const protectUnsaved = () => {
    const dirty = !!noteRef.current && contentRef.current !== savedContent.current;
    return !dirty || window.confirm('当前笔记有尚未保存的修改。离开后这些修改可能丢失，仍要继续吗？');
  };
  const beginTransition = () => {
    window.clearTimeout(timer.current);
    viewRevision.current += 1;
    editSequence.current += 1;
    setRestorePreview(null);
    return viewRevision.current;
  };

  useEffect(() => {
    void notesApi.collections().then(({ collections: value }) => {
      setCollections(value); if (value.length) setCollection(value[0].id);
    }).catch(() => setMessage('Notes 尚未配置，或当前登录会话无效。'));
  }, []);
  useEffect(() => { if (collections.some((item) => item.id === collection)) void refresh(collection); }, [collection, collections, refresh]);
  useEffect(() => () => window.clearTimeout(timer.current), []);

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

  const save = useCallback((target: Note, body: string, revision: number, sequence: number) => {
    const key = noteKey(target);
    setState('保存中…');
    saveQueue.current = saveQueue.current.catch(() => undefined).then(async () => {
      // Use the most recently confirmed ETag for this note. An older response
      // always advances that ETag before a later queued body is sent.
      const current = noteRef.current;
      const basis = current && noteKey(current) === key ? current : target;
      const saved = await notesApi.save(basis, body);
      if (viewRevision.current !== revision || !noteRef.current || noteKey(noteRef.current) !== key) return;
      noteRef.current = saved;
      savedContent.current = saved.content;
      setNote(saved);
      if (contentRef.current === saved.content && editSequence.current === sequence) {
        setContent(saved.content); setState('已保存'); setMessage('');
      } else {
        setState('未保存');
      }
      void refresh(target.collection);
    }).catch((error: unknown) => {
      if (viewRevision.current !== revision || editSequence.current !== sequence) return;
      const status = (error as Error & { status?: number }).status;
      setState(status === 412 ? '版本冲突' : '保存失败');
      setMessage(status === 412 ? '文件已在其他位置修改。当前输入仍保留；请复制未保存内容后重新载入再合并。' : '保存失败。当前输入仍保留，可检查授权后重试。');
    });
  }, [refresh]);

  const change = (body: string) => {
    contentRef.current = body;
    setContent(body); setState('未保存'); setMessage('');
    const target = noteRef.current;
    if (!target || target.read_only) return;
    window.clearTimeout(timer.current);
    const sequence = ++editSequence.current;
    const revision = viewRevision.current;
    timer.current = window.setTimeout(() => save(target, body, revision, sequence), 900);
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
          assetBase={`/api/notes/${encodeURIComponent(note.collection)}/${note.path.split('/').map(encodeURIComponent).join('/')}`} /> : <p className="notes-empty">先选择一篇已授权 Markdown，或新建 Draft。</p>}
        {message && <p role="alert" className={state === '版本冲突' || state === '保存失败' ? 'notes-error' : 'notes-hint'}>{message}</p>}
      </section>
    </div>
  </main>;
}
