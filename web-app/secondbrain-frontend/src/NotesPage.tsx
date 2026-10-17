import React, { useCallback, useEffect, useRef, useState } from 'react';
import { MarkdownEditor } from './MarkdownEditor';
import { notesApi, type Note, type NoteCollection } from './api/notes';

type State = '未保存' | '保存中…' | '已保存' | '保存失败' | '版本冲突';

export function NotesPage() {
  const [collections, setCollections] = useState<NoteCollection[]>([]);
  const [collection, setCollection] = useState('drafts');
  const [items, setItems] = useState<{ path: string; title: string }[]>([]);
  const [note, setNote] = useState<Note | null>(null);
  const [content, setContent] = useState('');
  const [state, setState] = useState<State>('已保存');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  const sequence = useRef(0);

  const refresh = useCallback(async (target = collection) => {
    try { const result = await notesApi.list(target); setItems(result.items); }
    catch { setItems([]); setMessage('笔记列表暂时无法读取，请检查登录会话和目录授权。'); }
  }, [collection]);

  useEffect(() => {
    void notesApi.collections().then(({ collections: value }) => {
      setCollections(value); if (value.length) setCollection(value[0].id);
    }).catch(() => setMessage('Notes 尚未配置，或当前登录会话无效。'));
  }, []);
  useEffect(() => { if (collections.some((item) => item.id === collection)) void refresh(collection); }, [collection, collections, refresh]);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const open = async (path: string) => {
    setLoading(true); setMessage(''); window.clearTimeout(timer.current);
    try {
      const loaded = await notesApi.read(collection, path);
      setNote(loaded); setContent(loaded.content); setState('已保存');
      setMessage(loaded.read_only ? `此文件含有当前富文本编辑器不能安全往返的语法（${loaded.safety_reasons.join('、')}），已保留原文并设为只读。` : '');
    } catch { setMessage('笔记读取失败，原有内容未更改。'); }
    finally { setLoading(false); }
  };

  const save = useCallback(async (target: Note, body: string, ticket: number) => {
    setState('保存中…');
    try {
      const saved = await notesApi.save(target, body);
      if (sequence.current !== ticket) return;
      setNote(saved); setContent(saved.content); setState('已保存'); setMessage('');
      void refresh(target.collection);
    } catch (error) {
      if (sequence.current !== ticket) return;
      const status = (error as Error & { status?: number }).status;
      setState(status === 412 ? '版本冲突' : '保存失败');
      setMessage(status === 412 ? '文件已在其他位置修改。当前输入仍保留；请复制未保存内容后重新载入再合并。' : '保存失败。当前输入仍保留，可检查授权后重试。');
    }
  }, [refresh]);

  const change = (body: string) => {
    setContent(body); setState('未保存'); setMessage('');
    if (!note || note.read_only) return;
    window.clearTimeout(timer.current);
    const ticket = ++sequence.current;
    timer.current = window.setTimeout(() => void save(note, body, ticket), 900);
  };

  const createDraft = async () => {
    setLoading(true); setMessage('');
    try {
      const created = await notesApi.create('# 未命名笔记\n\n');
      setCollection('drafts'); setNote(created); setContent(created.content); setState('已保存');
      void refresh('drafts');
    } catch { setMessage('Drafts 尚未配置，或创建失败；没有创建笔记。'); }
    finally { setLoading(false); }
  };

  const pasteImage = async (file: File) => {
    if (!note) throw new Error('请先创建或打开一篇笔记');
    try { const uploaded = await notesApi.upload(note, file); return uploaded.url; }
    catch { setMessage('图片附件未保存；正文仍保留。'); throw new Error('图片上传失败'); }
  };

  const restore = async () => {
    if (!note) return;
    try {
      const result = await notesApi.history(note);
      if (!result.versions.length) { setMessage('暂无可恢复版本。'); return; }
      change(result.versions[result.versions.length - 1].content);
    } catch { setMessage('历史版本读取失败。'); }
  };

  return <main className="notes-page">
    <header className="module-header"><div><p className="eyebrow">SECONDBRAIN / NOTES</p><h1>笔记</h1><p className="workspace-subtitle">以 Markdown 文件为正文来源；普通目录仅显示已显式授权的范围。</p></div>
      <button type="button" onClick={() => void createDraft()} disabled={loading}>新建 Draft</button></header>
    <div className="notes-layout">
      <aside className="notes-sidebar" aria-label="笔记目录">
        <label htmlFor="notes-collection">笔记目录</label>
        <select id="notes-collection" value={collection} onChange={(event) => { setCollection(event.target.value); setNote(null); setContent(''); }}>
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
        {note ? note.read_only ? <>
          <div className="notes-safety" role="status">此文件含有当前富文本编辑器不能安全往返的语法（{note.safety_reasons.join('、')}），原始 Markdown 保留只读。</div>
          <pre className="notes-raw-source">{content}</pre>
        </> : <MarkdownEditor value={content} disabled={false} onChange={change} onImagePaste={pasteImage}
          assetBase={`/api/notes/${encodeURIComponent(note.collection)}/${note.path.split('/').map(encodeURIComponent).join('/')}`} /> : <p className="notes-empty">先选择一篇已授权 Markdown，或新建 Draft。</p>}
        {message && <p role="alert" className={state === '版本冲突' || state === '保存失败' ? 'notes-error' : 'notes-hint'}>{message}</p>}
      </section>
    </div>
  </main>;
}
