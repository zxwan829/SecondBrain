import React, { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { NotePropertiesPanel } from './NotePropertiesPanel';
import { notesApi, type BlockSuiteResource, type BlockSuiteResourceKind, type BlockSuiteSnapshotDetail, type BlockSuiteSnapshotEntry, type BlockSuiteSnapshots, type Note, type NoteCollection, type NotesTrashItem, type VisualAsset, type VisualKind } from './api/notes';
import { defaultExcalidraw, defaultMindMap, visualKindFromFilename, visualLink } from './visualAssets';

const VisualAssetDialog = lazy(() => import('./VisualAssetDialog').then((module) => ({ default: module.VisualAssetDialog })));
const BlockSuiteMarkdownEditor = lazy(() => import('./BlockSuiteMarkdownEditor').then((module) => ({ default: module.BlockSuiteMarkdownEditor })));
const BlockSuiteResourceEditor = lazy(() => import('./BlockSuiteResourceEditor').then((module) => ({ default: module.BlockSuiteResourceEditor })));

type State = '未保存' | '保存中…' | '已保存' | '保存失败' | '版本冲突';
const noteKey = (value: Note) => `${value.collection}:${value.path}`;
const blockSuiteBlobKeyPattern = /^[A-Za-z0-9_-]{43}=$/;
const emptyBlockSuiteArtifactSetEtag = '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945';
const artifactKind = (artifact: { kind?: string; resource_id?: string; resource?: unknown; blob?: unknown }) =>
  artifact.kind ?? (artifact.resource_id || artifact.resource ? 'resource' : artifact.blob ? 'blob' : '');
const artifactId = (artifact: { id?: string; resource_id?: string }) => artifact.id ?? artifact.resource_id ?? '';

function referencedBlockSuiteBlobIds(resource: { snapshot?: unknown }): string[] {
  const found = new Set<string>();
  const visit = (value: unknown) => {
    if (!value || typeof value !== 'object') return;
    if (Array.isArray(value)) { value.forEach(visit); return; }
    for (const [key, item] of Object.entries(value)) {
      if ((key === 'sourceId' || key === 'source_id') && typeof item === 'string' && blockSuiteBlobKeyPattern.test(item)) found.add(item);
      visit(item);
    }
  };
  visit(resource.snapshot);
  return [...found];
}

async function validateSnapshotBlobs(artifacts: { kind?: string; id?: string; etag?: string; size_bytes?: number; bytes?: number; data_base64?: string }[]) {
  const blobs = artifacts.filter((artifact) => artifact.kind === 'blob');
  if (!blobs.length) return;
  const { sha } = await import('@blocksuite/global/utils');
  for (const artifact of blobs) {
    if (!artifact.id || !artifact.data_base64 || !blockSuiteBlobKeyPattern.test(artifact.id)) {
      throw new Error('快照图片缺少规范的 Blob key 或内容。');
    }
    const raw = atob(artifact.data_base64);
    if (btoa(raw) !== artifact.data_base64) throw new Error(`快照图片 ${artifact.id} 的 base64 不是规范编码。`);
    const bytes = Uint8Array.from(raw, (char) => char.charCodeAt(0));
    if (bytes.byteLength !== (artifact.size_bytes ?? artifact.bytes)) throw new Error(`快照图片 ${artifact.id} 的长度校验失败。`);
    if (await sha(bytes.slice().buffer as ArrayBuffer) !== artifact.id) throw new Error(`快照图片 ${artifact.id} 的 SHA-256 校验失败。`);
    const digestRaw = atob(artifact.id.replace(/-/g, '+').replace(/_/g, '/'));
    const expectedHex = digestRaw.split('').map((char) => char.charCodeAt(0).toString(16).padStart(2, '0')).join('');
    if (artifact.etag?.replace(/^"|"$/g, '') !== expectedHex) throw new Error(`快照图片 ${artifact.id} 的 ETag 校验失败。`);
  }
}

export function NotesPage({ onRegisterNavigationGuard, onOpenInboxSource }: { onRegisterNavigationGuard?: (guard: (() => boolean) | null) => void; onOpenInboxSource?: (collection: string, path: string) => void }) {
  const [collections, setCollections] = useState<NoteCollection[]>([]);
  const [collection, setCollection] = useState('drafts');
  const [items, setItems] = useState<{ path: string; title: string }[]>([]);
  const [note, setNote] = useState<Note | null>(null);
  const [content, setContent] = useState('');
  const [editorMode, setEditorMode] = useState<'blocksuite' | 'source'>('blocksuite');
  const [state, setState] = useState<State>('已保存');
  const [message, setMessage] = useState('');
  const blockSuiteFallbackReason = useRef<string | null>(null);
  const blockSuiteFallbackDiagnostic = useRef<'illegal_constructor' | 'missing_custom_element' | 'custom_element_conflict' | 'missing_root' | 'blocksuite_error' | 'other' | null>(null);
  const blockSuiteFallbackStage = useRef<'extension_setup' | 'scope_create' | 'host_render' | 'host_mount' | 'host_update' | null>(null);
  const [loading, setLoading] = useState(false);
  const [trashView, setTrashView] = useState(false);
  const [trashItems, setTrashItems] = useState<NotesTrashItem[]>([]);
  const [trashLoading, setTrashLoading] = useState(false);
  const [trashOffset, setTrashOffset] = useState(0);
  const [trashHasMore, setTrashHasMore] = useState(false);
  const [restorePreview, setRestorePreview] = useState<{ etag: string; content: string } | null>(null);
  const [blockSuiteSnapshots, setBlockSuiteSnapshots] = useState<{ note: Note; result: BlockSuiteSnapshots } | null>(null);
  const [blockSuiteSnapshotPreview, setBlockSuiteSnapshotPreview] = useState<{ entry: BlockSuiteSnapshotEntry; detail: BlockSuiteSnapshotDetail; currentNoteEtag: string; currentArtifactSetEtag: string } | null>(null);
  const [blockSuiteSnapshotBusy, setBlockSuiteSnapshotBusy] = useState(false);
  const [blockSuiteRestoreFailed, setBlockSuiteRestoreFailed] = useState(false);
  const [blockSuiteSnapshotRecoveryCopy, setBlockSuiteSnapshotRecoveryCopy] = useState<string | null>(null);
  const [blockSuiteSnapshotRecoveryComplete, setBlockSuiteSnapshotRecoveryComplete] = useState(false);
  const [visualAsset, setVisualAsset] = useState<VisualAsset | null>(null);
  const [unpersistedVisual, setUnpersistedVisual] = useState<{ note: Note; asset: VisualAsset } | null>(null);
  const [creatingVisual, setCreatingVisual] = useState(false);
  const [creatingBlockSuiteResource, setCreatingBlockSuiteResource] = useState(false);
  const [pendingBlockSuiteReference, setPendingBlockSuiteReference] = useState<{ note: Note; resource: BlockSuiteResource } | null>(null);
  const [blockSuiteResource, setBlockSuiteResource] = useState<BlockSuiteResource | null>(null);
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
  const blockSuiteResourceOpen = useRef(false);
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
    if (blockSuiteResourceOpen.current) {
      setMessage('请先保存并关闭当前 BlockSuite 资源编辑器，再切换笔记。');
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
    setCreatingBlockSuiteResource(false);
    setBlockSuiteResource(null);
    blockSuiteResourceOpen.current = false;
    setRestorePreview(null);
    setBlockSuiteSnapshots(null);
    setBlockSuiteSnapshotPreview(null);
    setBlockSuiteRestoreFailed(false);
    setBlockSuiteSnapshotRecoveryCopy(null);
    setBlockSuiteSnapshotRecoveryComplete(false);
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
      const hasBlockSuiteReference = /\]\(attachments\/[0-9a-f]{32}\.blocksuite\.json\)/i.test(loaded.content);
      const consistent = hasBlockSuiteReference ? await notesApi.readWithArtifactSet(targetCollection, path) : loaded;
      if (viewRevision.current !== revision) return;
      setCurrent(consistent, consistent.content); setState('已保存'); setEditorMode('blocksuite');
      setMessage(consistent.read_only ? `此文件含有当前富文本编辑器不能安全往返的语法（${consistent.safety_reasons.join('、')}），已保留原文并设为只读。` : '');
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

  const leaveBlockSuite = async (reason?: string, diagnostic?: 'illegal_constructor' | 'missing_custom_element' | 'custom_element_conflict' | 'missing_root' | 'blocksuite_error' | 'other', stage?: 'extension_setup' | 'scope_create' | 'host_render' | 'host_mount' | 'host_update') => {
    const target = noteRef.current;
    if (reason) window.clearTimeout(timer.current);
    if (!reason && target && contentRef.current !== savedContent.current) {
      const revision = viewRevision.current;
      const sequence = editSequence.current;
      const body = contentRef.current;
      window.clearTimeout(timer.current);
      try { await save(target, body, revision, sequence); }
      catch { /* save() keeps unsaved content and reports its failure before the editor switches. */ }
    }
    blockSuiteFallbackReason.current = reason ?? null;
    blockSuiteFallbackDiagnostic.current = reason ? diagnostic ?? null : null;
    blockSuiteFallbackStage.current = reason ? stage ?? null : null;
    setEditorMode('source');
    if (reason) setMessage('BlockSuite 无法安全往返此笔记，已保留 Markdown 原文并切换为只读源码视图。');
  };

  const createDraft = async () => {
    if (!protectUnsaved()) return;
    const revision = beginTransition();
    setLoading(true); setMessage(''); blockSuiteFallbackReason.current = null;
    try {
      const created = await notesApi.create('# 未命名笔记\n\n');
      if (viewRevision.current !== revision) return;
      setCollection('drafts'); setCurrent(created, created.content); setState('已保存'); setEditorMode('blocksuite');
      void refresh('drafts');
    } catch { if (viewRevision.current === revision) setMessage('Drafts 尚未配置，或创建失败；没有创建笔记。'); }
    finally { if (viewRevision.current === revision) setLoading(false); }
  };

  const selectCollection = (next: string) => {
    if (next === collection || !protectUnsaved()) return;
    beginTransition(); setCollection(next); setCurrent(null); setState('已保存'); setMessage('');
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

  const attachBlockSuiteResource = async (kind: BlockSuiteResourceKind) => {
    const target = noteRef.current;
    if (!target || target.read_only || state !== '已保存' || creatingBlockSuiteResource || blockSuiteResource) return;
    const revision = viewRevision.current;
    pendingSaves.current += 1;
    setCreatingBlockSuiteResource(true);
    setMessage(`正在创建独立 BlockSuite ${kind === 'database' ? 'Database' : 'Edgeless'} 资源…`);
    let resource: BlockSuiteResource | null = null;
    try {
      const { createBlockSuiteResourcePayload } = await import('./BlockSuiteResourceEditor');
      const payload = createBlockSuiteResourcePayload(kind);
      const created = await notesApi.createBlockSuiteResource(target, payload);
      const versionedTarget = { ...target, artifactSetEtag: created.artifact_set_etag };
      if (noteRef.current && noteKey(noteRef.current) === noteKey(target)) { noteRef.current = versionedTarget; setNote(versionedTarget); }
      resource = { ...payload, resourceId: created.resource_id, etag: created.etag, note_etag: created.note_etag, artifact_set_etag: created.artifact_set_etag, filename: created.filename };
      setPendingBlockSuiteReference({ note: versionedTarget, resource });
      const current = contentRef.current;
      const nextContent = `${current.trimEnd()}${current.trim() ? '\n\n' : ''}${created.reference}\n`;
      window.clearTimeout(timer.current);
      contentRef.current = nextContent;
      setContent(nextContent);
      setState('未保存');
      const sequence = ++editSequence.current;
      const saved = await save(versionedTarget, nextContent, revision, sequence);
      if (!saved) throw new Error('笔记已切换，资源已创建但 Markdown 引用尚未保存；请返回原笔记重试。');
      if (viewRevision.current !== revision || !noteRef.current || noteKey(noteRef.current) !== noteKey(target)) {
        throw new Error('资源已创建，但引用保存结果未应用到当前笔记。');
      }
      setPendingBlockSuiteReference(null);
      blockSuiteResourceOpen.current = true;
      setBlockSuiteResource(resource);
      setMessage('独立 BlockSuite 资源与稳定 Markdown 引用均已保存。');
    } catch (error) {
      if (viewRevision.current === revision) {
        setMessage(resource
          ? `资源文件已创建，但 Markdown 引用未确认保存；引用仍保留在正文，可重试。${error instanceof Error ? error.message : ''}`
          : `BlockSuite 资源创建失败；笔记正文未更改。${error instanceof Error ? error.message : ''}`);
      }
    } finally {
      pendingSaves.current = Math.max(0, pendingSaves.current - 1);
      if (viewRevision.current === revision) setCreatingBlockSuiteResource(false);
    }
  };

  const retryBlockSuiteReference = async () => {
    const pending = pendingBlockSuiteReference;
    if (!pending || !['保存失败', '版本冲突'].includes(state)
        || !noteRef.current || noteKey(noteRef.current) !== noteKey(pending.note)) return;
    const revision = viewRevision.current;
    try {
      let target = noteRef.current;
      let content = contentRef.current;
      if (state === '版本冲突') {
        // Resource creation was explicit and began from a clean Note. On an
        // explicit retry, preserve the newer Core Markdown and append only
        // this resource's stable reference; never resend the stale body.
        target = await notesApi.readWithArtifactSet(pending.note.collection, pending.note.path);
        if (viewRevision.current !== revision || !noteRef.current
            || noteKey(noteRef.current) !== noteKey(pending.note)) return;
        const reference = `[BlockSuite resource](attachments/${pending.resource.filename})`;
        if (!target.content.includes(reference)) {
          content = `${target.content.trimEnd()}${target.content.trim() ? '\n\n' : ''}${reference}\n`;
        } else {
          content = target.content;
        }
        setCurrent(target, target.content);
        contentRef.current = content;
        setContent(content);
        conflictedSave.current = null;
        setState('未保存');
      }
      const saved = await save(target, content, revision, editSequence.current);
      if (!saved) throw new Error('笔记已切换，保存结果未应用到当前页面。');
      setPendingBlockSuiteReference(null);
      blockSuiteResourceOpen.current = true;
      setBlockSuiteResource(pending.resource);
      setMessage('Markdown 资源引用已保存。');
    } catch { /* save() retains the unsaved Markdown and reports the failure. */ }
  };

  const openBlockSuiteResource = async (filename: string) => {
    const target = noteRef.current;
    const revision = viewRevision.current;
    const match = filename.match(/^([0-9a-f]{32})\.blocksuite\.json$/i);
    if (!target || !match || state !== '已保存' || blockSuiteResourceOpen.current) {
      setMessage('请先保存当前笔记，再打开 BlockSuite 资源。');
      return;
    }
    if (!contentRef.current.includes(`(attachments/${filename})`)) {
      setMessage('此 BlockSuite 资源没有当前笔记中的稳定引用，已拒绝打开。');
      return;
    }
    setLoading(true);
    try {
      const consistentTarget = await notesApi.readWithArtifactSet(target.collection, target.path);
      if (viewRevision.current !== revision || !noteRef.current || noteKey(noteRef.current) !== noteKey(target)) throw new Error('笔记已切换，请重新打开资源。');
      const loaded = await notesApi.readBlockSuiteResource(consistentTarget, match[1]);
      if (loaded.note_etag !== consistentTarget.etag) throw new Error('笔记版本已变化，请刷新后再打开资源。');
      if (loaded.artifact_set_etag && loaded.artifact_set_etag !== consistentTarget.artifactSetEtag) throw new Error('附件集合版本已变化，请刷新后再打开资源。');
      noteRef.current = consistentTarget; setNote(consistentTarget);
      blockSuiteResourceOpen.current = true;
      setBlockSuiteResource(loaded);
      setMessage('');
    } catch (error) {
      setMessage(`BlockSuite 资源无法打开：${error instanceof Error ? error.message : '读取失败'}`);
    } finally { setLoading(false); }
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
    if (state !== '已保存' || blockSuiteResourceOpen.current || !protectUnsaved()) {
      setMessage('请先保存并关闭当前编辑器，再查看可恢复版本。');
      return;
    }
    const targetKey = noteKey(target);
    const revision = viewRevision.current;
    setRestorePreview(null);
    setBlockSuiteSnapshots(null);
    setBlockSuiteSnapshotPreview(null);
    setBlockSuiteRestoreFailed(false);
    setBlockSuiteSnapshotRecoveryCopy(null);
    setBlockSuiteSnapshotRecoveryComplete(false);
    try {
      if (/\]\(attachments\/[0-9a-f]{32}\.blocksuite\.json\)/i.test(target.content) || target.artifactSetEtag) {
        let consistent = await notesApi.readWithArtifactSet(target.collection, target.path);
        let closure = await notesApi.readBlockSuiteSnapshots(consistent);
        if (consistent.etag !== closure.note_etag || consistent.artifactSetEtag !== closure.artifact_set_etag) {
          consistent = await notesApi.readWithArtifactSet(target.collection, target.path);
          closure = await notesApi.readBlockSuiteSnapshots(consistent);
        }
        if (consistent.etag !== closure.note_etag || consistent.artifactSetEtag !== closure.artifact_set_etag) {
          throw Object.assign(new Error('笔记或 BlockSuite 资源集合在读取期间变化；请重新打开笔记后重试。'), { status: 412 });
        }
        if (viewRevision.current !== revision || !noteRef.current || noteKey(noteRef.current) !== targetKey) return;
        noteRef.current = consistent; setNote(consistent);
        if (closure.snapshots.length || closure.artifact_set_etag !== emptyBlockSuiteArtifactSetEtag) {
          setBlockSuiteSnapshots({ note: consistent, result: closure });
          if (!closure.snapshots.length) setMessage('暂无完整且已校验的 BlockSuite 快照；当前正文与资源未改变。');
          else setMessage('选择一个快照查看目标 Markdown 与资源摘要；当前笔记尚未改变。');
          return;
        }
      }
      const result = await notesApi.history(noteRef.current ?? target);
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

  const previewBlockSuiteSnapshot = async (snapshotId: string) => {
    const history = blockSuiteSnapshots;
    const revision = viewRevision.current;
    const entry = history?.result.snapshots.find((item) => item.snapshot_id === snapshotId);
    if (!history || !entry || blockSuiteSnapshotBusy) return;
    setBlockSuiteSnapshotBusy(true);
    setBlockSuiteSnapshotPreview(null);
    setBlockSuiteRestoreFailed(false);
    try {
      const current = noteRef.current;
      if (!current || noteKey(current) !== noteKey(history.note)
          || current.etag !== history.note.etag || current.artifactSetEtag !== history.note.artifactSetEtag) {
        throw Object.assign(new Error('当前 Note 或资源集合版本已变化；请重新载入快照列表。'), { status: 412 });
      }
      const detail = await notesApi.readBlockSuiteSnapshot(history.note, snapshotId);
      if (detail.snapshot_id !== entry.snapshot_id || detail.note.etag !== entry.note_sha256
          || detail.artifact_set_etag !== entry.artifact_set_etag) {
        throw new Error('快照详情与列表摘要不匹配；已拒绝预览。');
      }
      const referenced = [...detail.note.content.matchAll(/\]\(attachments\/([0-9a-f]{32})\.blocksuite\.json\)/ig)].map((match) => match[1].toLowerCase());
      const resourceArtifacts = detail.artifacts.filter((artifact) => artifactKind(artifact) === 'resource');
      const blobArtifacts = detail.artifacts.filter((artifact) => artifactKind(artifact) === 'blob');
      const artifactIds = new Set(resourceArtifacts.map(artifactId).map((id) => id.toLowerCase()));
      if (referenced.some((id) => !artifactIds.has(id))) throw new Error('此快照的 Markdown 引用了缺失资源；已拒绝恢复。');
      const referencedBlobs = new Set(resourceArtifacts.flatMap((artifact) => referencedBlockSuiteBlobIds(artifact.resource ?? {})));
      const blobIds = new Set(blobArtifacts.map(artifactId));
      if ([...referencedBlobs].some((id) => !blobIds.has(id))) throw new Error('此快照的 BlockSuite 资源引用了缺失图片；已拒绝恢复。');
      await validateSnapshotBlobs(detail.artifacts);
      if (viewRevision.current !== revision || !noteRef.current || noteKey(noteRef.current) !== noteKey(history.note)) return;
      setBlockSuiteSnapshotPreview({ entry, detail, currentNoteEtag: history.note.etag, currentArtifactSetEtag: history.result.artifact_set_etag });
      setMessage('已载入快照内容与资源摘要；当前笔记尚未改变。');
    } catch (error) {
      const status = (error as Error & { status?: number }).status;
      setMessage(status === 412 ? '当前笔记或资源已变化，未读取混合版本快照；请重新打开后重试。'
        : `无法安全预览此 BlockSuite 快照：${error instanceof Error ? error.message : '读取失败'}`);
    } finally { setBlockSuiteSnapshotBusy(false); }
  };

  const downloadBlockSuiteRecoveryCopy = () => {
    if (!blockSuiteSnapshotRecoveryCopy || !noteRef.current) return;
    const blob = new Blob([blockSuiteSnapshotRecoveryCopy], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = `blocksuite-${noteRef.current.path.split('/').at(-1) || 'note'}-recovery.json`; anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
    setMessage('已下载恢复前捕获的当前 Markdown 与引用资源副本；远端内容未被覆盖。');
  };

  const confirmBlockSuiteRestore = async () => {
    const preview = blockSuiteSnapshotPreview;
    const current = noteRef.current;
    if (!preview || !current || blockSuiteSnapshotBusy || !protectUnsaved()) return;
    if (current.etag !== preview.currentNoteEtag || current.artifactSetEtag !== preview.currentArtifactSetEtag) {
      setBlockSuiteRestoreFailed(true);
      setBlockSuiteSnapshotRecoveryCopy(JSON.stringify({ schemaVersion: 1, recoveryType: 'blocksuite-snapshot-restore-conflict',
        captureComplete: false, note: { collection: current.collection, path: current.path, etag: current.etag, content: current.content },
        artifactSetEtag: current.artifactSetEtag, resources: [], blobs: [] }, null, 2));
      setBlockSuiteSnapshotRecoveryComplete(false);
      setMessage('当前 Note 或资源集合版本已变化（412）；没有恢复或覆盖内容。可下载当前正文副本后重新载入。');
      return;
    }
    const blobSummary = preview.detail.artifacts.filter((artifact) => artifactKind(artifact) === 'blob')
      .map((artifact) => `图片 ${artifactId(artifact)} · ${artifact.content_type ?? 'unknown'} · ${artifact.size_bytes ?? artifact.bytes ?? 0} bytes · ${artifact.sha256 ?? artifact.etag ?? 'unknown digest'}`).join('\n');
    const accepted = window.confirm(`将 BlockSuite 快照 ${preview.entry.snapshot_id} 恢复到此笔记？\n\n当前 Note: ${preview.currentNoteEtag}\n当前资源集合: ${preview.currentArtifactSetEtag}\n目标 Note: ${preview.detail.note.etag}\n目标资源集合: ${preview.detail.artifact_set_etag}\n\n目标图片：\n${blobSummary || '无'}\n\n恢复后会替换正文与该快照中的 BlockSuite 资源。`);
    if (!accepted) return;
    setBlockSuiteSnapshotBusy(true);
    setBlockSuiteRestoreFailed(false);
    setBlockSuiteSnapshotRecoveryCopy(null);
    setBlockSuiteSnapshotRecoveryComplete(false);
    try {
      setBlockSuiteSnapshotRecoveryCopy(JSON.stringify({ schemaVersion: 1, recoveryType: 'blocksuite-snapshot-restore-conflict',
        captureComplete: false, note: { collection: current.collection, path: current.path, etag: current.etag, content: current.content },
        artifactSetEtag: current.artifactSetEtag, resources: [], blobs: [] }, null, 2));
      const resourceIds = [...new Set([...current.content.matchAll(/\]\(attachments\/([0-9a-f]{32})\.blocksuite\.json\)/ig)].map((match) => match[1].toLowerCase()))];
      const currentResources = await Promise.all(resourceIds.map((id) => notesApi.readBlockSuiteResource(current, id)));
      setBlockSuiteSnapshotRecoveryCopy(JSON.stringify({ schemaVersion: 1, recoveryType: 'blocksuite-snapshot-restore-conflict',
        captureComplete: false, note: { collection: current.collection, path: current.path, etag: current.etag, content: current.content },
        artifactSetEtag: current.artifactSetEtag, resources: currentResources, blobs: [] }, null, 2));
      if (currentResources.some((resource) => resource.note_etag !== current.etag
          || resource.artifact_set_etag !== current.artifactSetEtag)) throw Object.assign(new Error('当前资源版本发生变化，未启动恢复。'), { status: 412 });
      const blobIds = [...new Set(currentResources.flatMap(referencedBlockSuiteBlobIds))];
      const { NoteBoundBlockSuiteBlobSource } = await import('./api/notes-blocksuite-blobs');
      const blobSource = new NoteBoundBlockSuiteBlobSource(() => current);
      const currentBlobs = await Promise.all(blobIds.map(async (id) => {
        const value = await blobSource.get(id);
        if (!value) throw new Error(`当前资源引用的图片 ${id} 无法读取；未启动恢复。`);
        const bytes = new Uint8Array(await value.arrayBuffer());
        let binary = ''; for (const byte of bytes) binary += String.fromCharCode(byte);
        return { id, content_type: value.type, bytes: bytes.byteLength, base64: btoa(binary) };
      }));
      const recoveryCopy = JSON.stringify({ schemaVersion: 1, recoveryType: 'blocksuite-snapshot-restore-conflict',
        captureComplete: true,
        note: { collection: current.collection, path: current.path, etag: current.etag, content: current.content },
        artifactSetEtag: current.artifactSetEtag, resources: currentResources, blobs: currentBlobs }, null, 2);
      setBlockSuiteSnapshotRecoveryCopy(recoveryCopy);
      setBlockSuiteSnapshotRecoveryComplete(true);
      const result = await notesApi.restoreBlockSuiteSnapshot(current, preview.entry.snapshot_id);
      if (!result.restored || result.snapshot_id !== preview.entry.snapshot_id) throw new Error('Core 未确认此快照恢复成功。');
      const restored = await notesApi.readWithArtifactSet(current.collection, current.path);
      if (restored.etag !== result.note_etag || restored.artifactSetEtag !== result.artifact_set_etag) {
        throw Object.assign(new Error('恢复响应与重新读取的 Note/资源版本不一致。'), { status: 412 });
      }
      const resourceArtifacts = preview.detail.artifacts.filter((artifact) => artifactKind(artifact) === 'resource');
      const blobArtifacts = preview.detail.artifacts.filter((artifact) => artifactKind(artifact) === 'blob');
      for (const artifact of resourceArtifacts) {
        const id = artifactId(artifact);
        const loaded = await notesApi.readBlockSuiteResource(restored, id);
        if (loaded.resourceId !== id || loaded.etag !== (artifact.sha256 ?? artifact.etag)
            || loaded.note_etag !== restored.etag || loaded.artifact_set_etag !== restored.artifactSetEtag) {
          throw new Error(`恢复后的资源 ${id} 无法验证。`);
        }
      }
      if (blobArtifacts.length) {
        const { NoteBoundBlockSuiteBlobSource } = await import('./api/notes-blocksuite-blobs');
        const source = new NoteBoundBlockSuiteBlobSource(() => restored);
        for (const artifact of blobArtifacts) {
          const id = artifactId(artifact);
          if (!await source.get(id)) throw new Error(`恢复后的图片 ${id} 无法验证。`);
        }
      }
      if (!noteRef.current || noteKey(noteRef.current) !== noteKey(current)) throw new Error('笔记已切换；恢复结果未应用到当前视图。');
      setCurrent(restored, restored.content);
      setState('已保存');
      setBlockSuiteSnapshots(null); setBlockSuiteSnapshotPreview(null); setBlockSuiteRestoreFailed(false);
      setBlockSuiteSnapshotRecoveryCopy(null);
      setBlockSuiteSnapshotRecoveryComplete(false);
      setMessage('BlockSuite 快照已恢复，并重新验证了正文与引用资源。');
      void refresh(restored.collection);
    } catch (error) {
      const status = (error as Error & { status?: number }).status;
      setBlockSuiteRestoreFailed(true);
      setMessage(status === 412 || status === 409
        ? `恢复未执行（HTTP ${status}）：当前正文与资源保留，Core 未强制覆盖。建议先下载当前恢复副本，再重新载入快照列表。`
        : `恢复未能确认完成；当前页面正文仍保留。${error instanceof Error ? error.message : ''}`);
    } finally { setBlockSuiteSnapshotBusy(false); }
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
            <button type="button" disabled={state !== '已保存' || creatingBlockSuiteResource || blockSuiteResource !== null} onClick={() => void attachBlockSuiteResource('database')}>新建 BlockSuite Database</button>
            <button type="button" disabled={state !== '已保存' || creatingBlockSuiteResource || blockSuiteResource !== null} onClick={() => void attachBlockSuiteResource('edgeless-canvas')}>新建 BlockSuite Edgeless 画布</button>
          </>}
          {note && note.collection === 'drafts' && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(note.path) && onOpenInboxSource && <button type="button" onClick={() => { if (protectUnsaved()) onOpenInboxSource(note.collection, note.path); }}>单来源 Inbox 审批</button>}
          {note && <button type="button" onClick={() => void restore()}>查看可恢复版本</button>}
          {note && <button type="button" onClick={() => void trashSelectedNote()} disabled={state !== '已保存' || loading || creatingVisual || savingVisual || visualAsset !== null || unpersistedVisual !== null}>移到回收站</button>}
        </div>
        {note && (note.read_only || editorMode === 'source') && <button type="button" onClick={() => {
          const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          anchor.href = url;
          anchor.download = note.path.split('/').at(-1) || 'note.md';
          anchor.click();
          window.setTimeout(() => URL.revokeObjectURL(url), 0);
        }}>下载当前 Markdown 原文</button>}
        {restorePreview && <section className="notes-restore-preview" aria-label="历史版本预览">
          <h2>最近历史版本预览</h2><pre>{restorePreview.content}</pre>
          <button type="button" onClick={() => setRestorePreview(null)}>取消</button>
          <button type="button" onClick={confirmRestore}>使用此版本</button>
        </section>}
        {blockSuiteSnapshots && <section className="notes-restore-preview blocksuite-snapshot-history" aria-label="BlockSuite 快照恢复">
          <h2>BlockSuite 完整快照</h2>
          <p>当前 Note ETag：<code>{blockSuiteSnapshots.note.etag}</code></p>
          <p>当前资源集合 ETag：<code>{blockSuiteSnapshots.result.artifact_set_etag}</code></p>
          {!blockSuiteSnapshots.result.snapshots.length ? <p>没有可恢复的完整快照。</p> : <ul aria-label="可恢复 BlockSuite 快照">
            {blockSuiteSnapshots.result.snapshots.map((entry) => <li key={entry.snapshot_id}>
              <span>{new Date(entry.created_at).toLocaleString()} · Note {entry.note_sha256.slice(0, 12)} · {entry.artifact_count} 项 / {entry.artifact_bytes} bytes</span>
              <button type="button" disabled={blockSuiteSnapshotBusy} onClick={() => void previewBlockSuiteSnapshot(entry.snapshot_id)}>选择并预览</button>
            </li>)}
          </ul>}
          {blockSuiteSnapshotPreview && <div aria-label="BlockSuite 快照预览">
            <h3>目标快照摘要</h3>
            <p>目标 Note ETag：<code>{blockSuiteSnapshotPreview.detail.note.etag}</code></p>
            <p>目标资源集合 ETag：<code>{blockSuiteSnapshotPreview.detail.artifact_set_etag}</code></p>
            <h4>目标 Markdown</h4><pre>{blockSuiteSnapshotPreview.detail.note.content}</pre>
            <h4>目标 BlockSuite 资源（{blockSuiteSnapshotPreview.detail.artifacts.length} 项）</h4>
            <ul>{blockSuiteSnapshotPreview.detail.artifacts.map((artifact) => <li key={`${artifactKind(artifact)}:${artifactId(artifact)}`}>
              {artifactKind(artifact) === 'resource'
                ? `${artifact.resource?.resourceKind ?? 'resource'} · ${artifact.resource?.docId ?? artifactId(artifact)} · ${artifact.bytes ?? new TextEncoder().encode(JSON.stringify(artifact.resource ?? {})).byteLength} bytes · ${artifact.sha256 ?? artifact.etag ?? ''}`
                : `图片 · ${artifact.content_type ?? 'unknown'} · ${artifact.size_bytes ?? artifact.bytes ?? 0} bytes · SHA-256 ${artifact.sha256 ?? artifact.etag ?? artifactId(artifact)}`}
            </li>)}</ul>
            <p>只有显式确认后才会提交恢复。恢复请求会同时校验当前 Note 与资源集合 ETag。</p>
            <button type="button" disabled={blockSuiteSnapshotBusy} onClick={() => { setBlockSuiteSnapshotPreview(null); setBlockSuiteRestoreFailed(false); setBlockSuiteSnapshotRecoveryCopy(null); setBlockSuiteSnapshotRecoveryComplete(false); }}>取消</button>
            <button type="button" disabled={blockSuiteSnapshotBusy} onClick={() => void confirmBlockSuiteRestore()}>
              {blockSuiteSnapshotBusy ? '正在校验或恢复…' : '确认恢复此 BlockSuite 快照'}
            </button>
          </div>}
          {blockSuiteRestoreFailed && blockSuiteSnapshotRecoveryCopy && <>
            {!blockSuiteSnapshotRecoveryComplete && <p>完整资源副本生成失败；下载文件将包含当前 Markdown 及已成功读取的资源部分。</p>}
            <button type="button" onClick={downloadBlockSuiteRecoveryCopy}>{blockSuiteSnapshotRecoveryComplete ? '下载恢复前的正文、资源与图片副本' : '下载当前部分恢复副本'}</button>
          </>}
          <button type="button" disabled={blockSuiteSnapshotBusy} onClick={() => { setBlockSuiteSnapshots(null); setBlockSuiteSnapshotPreview(null); setBlockSuiteRestoreFailed(false); setBlockSuiteSnapshotRecoveryCopy(null); setBlockSuiteSnapshotRecoveryComplete(false); }}>关闭</button>
        </section>}
        {note && state === '已保存' && !loading && <NotePropertiesPanel key={noteKey(note)} note={note} onSaved={(saved) => {
          setCurrent(saved, saved.content); setState('已保存'); setMessage(''); void refresh(saved.collection);
        }} />}
        {note ? note.read_only || editorMode === 'source' ? <>
          <div className="notes-safety" role="status">{note.read_only
            ? `此文件含有当前 BlockSuite 编辑器不能安全往返的语法（${note.safety_reasons.join('、')}），原始 Markdown 保留只读。`
            : (editorMode === 'source'
              ? 'BlockSuite 无法安全往返此笔记；原文保持只读，可下载保存。'
              : '此笔记含有 YAML Frontmatter；当前编辑器不能确认安全往返，原文保持只读。')}</div>
          <pre className="notes-raw-source">{content}</pre>
        </> : <Suspense fallback={<p role="status">正在加载 BlockSuite 编辑器…</p>}><BlockSuiteMarkdownEditor key={`blocksuite:${noteKey(note)}`} value={content} disabled={state === '保存中…' || state === '版本冲突' || state === '保存失败'} onChange={change}
          onOpenVisualAsset={openVisual} onOpenBlockSuiteResource={(filename) => { void openBlockSuiteResource(filename); }}
          onFallback={(reason, diagnostic, stage) => { void leaveBlockSuite(reason, diagnostic, stage); }} /></Suspense>
          : <p className="notes-empty">先选择一篇已授权 Markdown，或新建 Draft。</p>}
        {message && <p role="alert" data-fallback-reason={blockSuiteFallbackReason.current ?? undefined}
          data-fallback-diagnostic={blockSuiteFallbackDiagnostic.current ?? undefined}
          data-fallback-stage={blockSuiteFallbackStage.current ?? undefined}
          className={state === '版本冲突' || state === '保存失败' ? 'notes-error' : 'notes-hint'}>{message}</p>}
        {unpersistedVisual && state === '保存失败' && note && noteKey(note) === noteKey(unpersistedVisual.note) &&
          <button type="button" onClick={() => void retryVisualReference()}>重试保存图形引用</button>}
        {pendingBlockSuiteReference && ['保存失败', '版本冲突'].includes(state) && note && noteKey(note) === noteKey(pendingBlockSuiteReference.note) &&
          <button type="button" onClick={() => void retryBlockSuiteReference()}>
            {state === '版本冲突' ? '读取最新笔记并追加 BlockSuite 资源引用' : '重试保存 BlockSuite 资源引用'}
          </button>}
      </section>
    </div>}
    {blockSuiteResource && note && <Suspense fallback={<p role="status">正在加载 BlockSuite 资源编辑器…</p>}>
      <BlockSuiteResourceEditor key={`${noteKey(note)}:${blockSuiteResource.resourceId}`} note={note} resource={blockSuiteResource}
        onNoteVersionChange={(artifactSetEtag) => {
          if (!noteRef.current || noteKey(noteRef.current) !== noteKey(note)) return;
          const next = { ...noteRef.current, artifactSetEtag };
          noteRef.current = next; setNote(next);
        }}
        onClose={() => { blockSuiteResourceOpen.current = false; setBlockSuiteResource(null); }} />
    </Suspense>}
    {visualAsset && <Suspense fallback={<p role="status">正在加载图形编辑器…</p>}>
      <VisualAssetDialog key={`${note ? noteKey(note) : ''}:${visualAsset.filename}`} kind={visualKindFromFilename(visualAsset.filename)!} asset={visualAsset}
        onSave={saveVisual} onClose={() => setVisualAsset(null)} onNavigationRiskChange={updateVisualNavigationRisk} canSave={state === '已保存'} />
    </Suspense>}
  </main>;
}
