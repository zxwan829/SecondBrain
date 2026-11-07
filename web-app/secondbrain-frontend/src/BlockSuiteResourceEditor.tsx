import React, { useEffect, useRef, useState } from 'react';
import { DatabaseBlockDataSource, databaseViewInitTemplate, richTextColumnConfig } from '@blocksuite/affine-block-database';
import { ShapeType } from '@blocksuite/affine-model';
import { BlockStdScope } from '@blocksuite/std';
import { Text } from '@blocksuite/store';
import * as Y from 'yjs';
import { notesApi, type BlockSuiteResource, type BlockSuiteResourceKind, type BlockSuiteResourceWrite, type Note } from './api/notes';
import { NoteBoundBlockSuiteBlobSource } from './api/notes-blocksuite-blobs';
import { TransientMarkdownWorkspace } from './transient-blocksuite-workspace';
import { assertRichPageMarkdownBinding, bindRichPageSnapshot, markdownSha256, richPageMarkdownBinding, richPageReadableMarkdown } from './rich-page-projection';
import { forkRichPageNote, snapshotBlobIds, snapshotCanvasIds } from './rich-page-fork';
import { nativeResourceSnapshot, remapNativeResourceReferences } from './native-resource-state';
import { sameBlockSuiteSnapshot } from './resource-snapshot-equality';
import { ArchiveDocumentHeader, ArchiveEmojiPicker, archiveExportHtml, archivePrintPdf, archiveInspectMindMap, archiveFocusMindMap, archiveFocusFrame, ArchiveNativeDiagnostics } from './archive-rich-page-tools';
import type { ArchiveProperties } from './archive-rich-page-tools';
import { archiveManagers, archiveViewExtensions, bindArchiveSurface } from './archive-rich-page-runtime';
import { ArchiveCanvasGallery, type ArchiveCanvasCard } from './archive-canvas-gallery';
import { toCanvasPreviewShape } from './canvas-preview';
import { CANVAS_REF_FLAVOUR, CANVAS_REF_OPEN_EVENT, CANVAS_REF_COPY_EVENT } from './canvas-ref-block';
import { DEFAULT_ARCHIVE_PROPERTIES } from './archive-rich-page-tools';
import { readKnownFrontmatter } from './markdown-frontmatter';
import './blocksuite-resource.css';
import '@toeverything/theme/style.css';

const base64 = (bytes: Uint8Array) => {
  let raw = '';
  for (const byte of bytes) raw += String.fromCharCode(byte);
  return btoa(raw);
};
const unbase64 = (value: string) => {
  const raw = atob(value);
  return Uint8Array.from(raw, char => char.charCodeAt(0));
};

function referencedBlockSuiteBlobIds(store: any): string[] {
  const ids = new Set<string>();
  for (const block of store.getBlocksByFlavour(['affine:image', 'affine:attachment'])) {
    const id = block.model.props.sourceId;
    if (typeof id !== 'string' || !id) throw new Error('图片/附件 Block 缺少 Blob sourceId；资源未保存。');
    ids.add(id);
  }
  return [...ids];
}

function selectedManagers(_kind: BlockSuiteResourceKind) {
  return archiveManagers();
}

function seedResource(store: any, kind: BlockSuiteResourceKind) {
  const root = store.addBlock('affine:page', {}, null);
  const surface = store.addBlock('affine:surface', {}, root, 0);
  if (kind === 'rich-page') {
    // Persist the intended opening mode with the native resource itself.
    // Relying only on the UI fallback let a new resource mount in Edgeless
    // without an explicit Page-mode value in its Yjs state.
    store.spaceDoc.getMap('secondbrain-rich-page-properties').set('docMode', 'page');
    const note = store.addBlock('affine:note', {}, root);
    store.addBlock('affine:paragraph', { type: 'h1', text: new Text('富 Page') }, note);
    store.addBlock('affine:paragraph', { text: new Text('在这里开始编辑完整富格式内容。') }, note);
  } else if (kind === 'database') {
    const note = store.addBlock('affine:note', {}, root);
    store.addBlock('affine:paragraph', { type: 'h1', text: new Text('独立数据库') }, note);
    const id = store.addBlock('affine:database', {}, note);
    const model = store.getBlock(id)?.model;
    const source = new DatabaseBlockDataSource(model);
    databaseViewInitTemplate(source, 'table');
    const column = source.propertyAdd('end', { type: richTextColumnConfig.type, name: '备注' });
    model.props.title.insert('测试数据库', 0);
    const row = model.children[0];
    if (row && column) {
      row.text?.insert('测试记录', 0);
      source.cellValueChange(row.id, column, new Text('仅供体验'));
    }
  } else {
    const canvas = store.getBlock(surface)?.model;
    canvas.addElement({ type: 'shape', shapeType: ShapeType.Rect, xywh: '[80,100,260,150]', text: '可编辑测试画布' });
    const sticky = store.addBlock('affine:edgeless-text', { xywh: '[120,360,320,120]', hasMaxWidth: true }, surface);
    store.addBlock('affine:paragraph', { text: new Text('独立 Edgeless 便签') }, sticky);
  }
}

export function createBlockSuiteResourcePayload(kind: BlockSuiteResourceKind): Omit<BlockSuiteResourceWrite, 'resourceId'> {
  const workspace = new TransientMarkdownWorkspace();
  try {
    const { stores } = selectedManagers(kind);
    workspace.storeExtensions = stores.get('store');
    workspace.meta.initialize();
    const docId = crypto.randomUUID();
    const doc = workspace.createDoc(docId).load();
    const store = doc.getStore();
    seedResource(store, kind);
    const snapshot = kind === 'rich-page' ? nativeResourceSnapshot(store) : store.getTransformer().docToSnapshot(store);
    if (!snapshot || typeof snapshot !== 'object') throw new Error('BlockSuite 未能导出初始快照');
    return { schemaVersion: 1, resourceKind: kind, docId,
      updateB64: base64(Y.encodeStateAsUpdate(doc.spaceDoc)), snapshot: snapshot as Record<string, unknown> };
  } finally {
    workspace.dispose();
  }
}

export function restoreBlockSuiteResourceSnapshot(resource: Pick<BlockSuiteResourceWrite, 'docId' | 'resourceKind' | 'updateB64'>): Record<string, unknown> {
  const workspace = new TransientMarkdownWorkspace();
  try {
    const { stores } = selectedManagers(resource.resourceKind);
    workspace.storeExtensions = stores.get('store');
    workspace.meta.initialize();
    const doc = workspace.createDoc(resource.docId);
    Y.applyUpdate(doc.spaceDoc, unbase64(resource.updateB64));
    doc.load();
    const store = doc.getStore();
    const snapshot = store.getTransformer().docToSnapshot(store);
    if (!snapshot || typeof snapshot !== 'object') throw new Error('BlockSuite 未能从 Yjs update 恢复快照');
    return snapshot as Record<string, unknown>;
  } finally {
    workspace.dispose();
  }
}

function initialArchiveProperties(note: Note, resource: BlockSuiteResource): ArchiveProperties {
  const snapshotMeta = resource.snapshot.secondbrainRichPage;
  const stored = snapshotMeta && typeof snapshotMeta === 'object' && 'properties' in snapshotMeta
    && snapshotMeta.properties && typeof snapshotMeta.properties === 'object'
    ? snapshotMeta.properties as Partial<ArchiveProperties> : {};
  const frontmatter = readKnownFrontmatter(note.content);
  const list = (value: unknown) => Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string')
    : typeof value === 'string' ? value.split(',').map(item => item.trim()).filter(Boolean) : [];
  return { ...DEFAULT_ARCHIVE_PROPERTIES, ...stored,
    tags: list(frontmatter.tags ?? stored.tags), aliases: list(frontmatter.aliases ?? stored.aliases), related: list(frontmatter.related ?? stored.related),
    type: typeof frontmatter.type === 'string' ? frontmatter.type : stored.type ?? DEFAULT_ARCHIVE_PROPERTIES.type,
    status: stored.status ?? (typeof frontmatter.status === 'string' ? frontmatter.status : DEFAULT_ARCHIVE_PROPERTIES.status),
    created: typeof frontmatter.created === 'string' ? frontmatter.created : stored.created ?? '',
    updated: typeof frontmatter.updated === 'string' ? frontmatter.updated : stored.updated ?? '',
    description: typeof frontmatter.description === 'string' ? frontmatter.description : stored.description ?? '',
    source: typeof frontmatter.source === 'string' ? frontmatter.source : stored.source ?? '',
    folderCollection: stored.folderCollection ?? note.collection,
  };
}

export function BlockSuiteResourceEditor({ note, resource: initialResource, onClose, onNoteVersionChange, onNoteSaved, onResourceSaved, onForked, onOpenBackups }: {
  onNoteSaved?: (note: Note) => void; onForked?: (note: Note, resource: BlockSuiteResource) => void;
  onResourceSaved?: (resource: BlockSuiteResource, store: any) => void;
  onOpenBackups?: () => void;
  note: Note; resource: BlockSuiteResource; onClose: () => void; onNoteVersionChange: (artifactSetEtag: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const archiveSurfaceRef = useRef<ReturnType<typeof bindArchiveSurface> | null>(null);
  const focusFrameAfterView = useRef<string | null>(null);
  const resourceRef = useRef(initialResource);
  const noteRef = useRef(note);
  const blobSourceRef = useRef<NoteBoundBlockSuiteBlobSource | null>(null);
  const dirtyRef = useRef(false);
  const editSequence = useRef(0);
  // Keep the exact bytes uploaded in this editing session so a later artifact
  // set conflict cannot make the only recovery copy depend on a stale server ETag.
  const uploadedBlobCopies = useRef(new Map<string, { contentType: string; bytes: Uint8Array }>());
  const [status, setStatus] = useState('正在载入 BlockSuite 资源…');
  const [dirty, setDirty] = useState(false);
  const [storeReady, setStoreReady] = useState(false);
  const [projectionConflict, setProjectionConflict] = useState(false);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const [recoveryCopyReady, setRecoveryCopyReady] = useState(false);
  const [recoveryCopyComplete, setRecoveryCopyComplete] = useState(false);
  const [uploadingImage, setUploadingImage] = useState(false);
  const [viewMode, setViewMode] = useState<'page' | 'edgeless'>(() => initialResource.resourceKind === 'rich-page' ? initialArchiveProperties(note, initialResource).docMode : 'edgeless');
  const [archiveProperties, setArchiveProperties] = useState<ArchiveProperties>(() => initialArchiveProperties(note, initialResource));
  const [emojiModelId, setEmojiModelId] = useState<string | null>(null);
  const [canvasCards, setCanvasCards] = useState<ArchiveCanvasCard[]>([]);
  const [nestedResource, setNestedResource] = useState<BlockSuiteResource | null>(null);
  const [mindMapReport, setMindMapReport] = useState('');
  const [diagnosticStatus, setDiagnosticStatus] = useState('');
  const [hasBackup, setHasBackup] = useState(false);
  const [reloadGeneration, setReloadGeneration] = useState(0);
  noteRef.current = note;

  useEffect(() => {
    let disposed = false;
    setStoreReady(false);
    let workspace: TransientMarkdownWorkspace | undefined;
    let std: BlockStdScope | undefined;
    let offUpdate: (() => void) | undefined;
    const setup = async () => {
      try {
        const editingResource = resourceRef.current;
        const native = editingResource.resourceKind === 'rich-page';
        const { stores, views } = selectedManagers(editingResource.resourceKind);
        const blobSource = new NoteBoundBlockSuiteBlobSource(() => noteRef.current, fetch, (etag) => {
          noteRef.current = { ...noteRef.current, artifactSetEtag: etag };
          resourceRef.current = { ...resourceRef.current, artifact_set_etag: etag };
          onNoteVersionChange(etag);
        });
        blobSourceRef.current = blobSource;
        workspace = new TransientMarkdownWorkspace(blobSource);
        workspace.storeExtensions = stores.get('store');
        workspace.meta.initialize();
        const doc = workspace.createDoc(editingResource.docId);
        Y.applyUpdate(doc.spaceDoc, unbase64(editingResource.updateB64));
        doc.load();
        const store = doc.getStore();
        (store as any).__sbNativeResource = native;
        // Capture the verified image closure before enabling an editing session.
        // A later remote conflict must not remove its complete recovery copy.
        for (const id of referencedBlockSuiteBlobIds(store)) {
          const blob = await store.blobSync.get(id) as Blob | null;
          if (!blob) throw new Error('资源引用的图片缺失；未启用编辑。');
          uploadedBlobCopies.current.set(id, { contentType: blob.type, bytes: new Uint8Array(await blob.arrayBuffer()) });
        }
        const scope = initialResource.resourceKind === 'edgeless-canvas' ? 'edgeless' : native ? viewMode : 'page';
        const extensionSet = native ? archiveViewExtensions(scope) : views.get(scope);
        std = new BlockStdScope({ store: store as any, extensions: extensionSet });
        const root = std.render();
        if (disposed || !host.current) { workspace.dispose(); return; }
        const viewport = document.createElement('div');
        viewport.className = `${scope === 'edgeless' ? 'affine-edgeless-viewport' : 'affine-page-viewport'}${native ? ' sb-archive-viewport' : ''}`;
        host.current.replaceChildren(viewport);
        viewport.append(root);
        await root.getUpdateComplete();
        if (disposed) return;
        if (native && scope === 'edgeless' && focusFrameAfterView.current) {
          try { archiveFocusFrame(std!, focusFrameAfterView.current); setStatus('已打开内嵌画布范围。'); }
          catch (error) { setStatus(error instanceof Error ? error.message : '无法定位内嵌画布'); }
          focusFrameAfterView.current = null;
        }
        const onUpdate = () => {
          editSequence.current += 1;
          if (initialResource.resourceKind === 'edgeless-canvas') {
            try {
              const currentSnapshot = store.getTransformer().docToSnapshot(store);
              if (currentSnapshot && sameBlockSuiteSnapshot(currentSnapshot, resourceRef.current.snapshot)) {
                dirtyRef.current = false;
                setDirty(false);
                setRecoveryCopyReady(false);
                if (!savingRef.current) setStatus('BlockSuite 资源已保存');
                return;
              }
            } catch {
              // Snapshot uncertainty is never grounds for enabling close.
            }
          }
          const wasDirty = dirtyRef.current;
          dirtyRef.current = true;
          setDirty(true);
          setRecoveryCopyReady(false);
          // Layout updates must not overwrite upload/save failure diagnostics.
          if (!wasDirty) setStatus('有未保存的资源修改');
        };
        doc.spaceDoc.on('update', onUpdate);
        offUpdate = () => doc.spaceDoc.off('update', onUpdate);
        setStatus(native ? 'BlockSuite 富 Page 已就绪' : initialResource.resourceKind === 'database' ? 'BlockSuite Database 已就绪' : 'BlockSuite Edgeless 画布已就绪');
        Object.assign(host.current, { __sbBlockSuiteStore: store, __sbBlockSuiteStd: std });
        setStoreReady(true);
        if (native && (richPageMarkdownBinding(editingResource.snapshot) !== editingResource.note_etag
          || editingResource.note_etag !== noteRef.current.etag)) {
          setProjectionConflict(true);
          setStatus('富 Page 与 Markdown 版本冲突；仅在本地保留修改。请下载双方副本或另存新富 Page。');
        }
      } catch (error) {
        if (!disposed) setStatus(error instanceof Error ? `加载失败：${error.message}` : 'BlockSuite 资源无法载入');
        workspace?.dispose();
      }
    };
    void setup();
    return () => {
      disposed = true;
      offUpdate?.();
      std?.unmount();
      workspace?.dispose();
      host.current?.replaceChildren();
    };
  }, [initialResource, viewMode, reloadGeneration]);

  const save = async (): Promise<boolean> => {
    const store = (host.current as (HTMLDivElement & { __sbBlockSuiteStore?: any }) | null)?.__sbBlockSuiteStore;
    if (!store || savingRef.current) return false;
    savingRef.current = true;
    setSaving(true);
    setStatus('正在保存 BlockSuite 资源…');
    let nativeWriteCommitted = false;
    let projectionWriteStarted = false;
    try {
      const basis = { ...noteRef.current };
      if (initialResource.resourceKind === 'rich-page') assertRichPageMarkdownBinding(basis, resourceRef.current.snapshot);
      const blobIds = referencedBlockSuiteBlobIds(store);
      for (const id of blobIds) {
        if (!await store.blobSync.get(id)) throw new Error(`资源引用的 Blob ${id} 不在此笔记的 Core 存储中；已保留页面修改，未提交。`);
      }
      if (JSON.stringify([...blobIds].sort()) !== JSON.stringify(referencedBlockSuiteBlobIds(store).sort())) {
        throw new Error('资源引用的图片在校验期间变化，请再次保存。');
      }
      // Layout-only changes may occur while blobs are read. Capture the latest
      // synchronous snapshot only after confirming its blob closure is validated.
      const sequence = editSequence.current;
      const rawSnapshot = initialResource.resourceKind === 'rich-page' ? nativeResourceSnapshot(store) : store.getTransformer().docToSnapshot(store);
      if (!rawSnapshot || typeof rawSnapshot !== 'object') throw new Error('BlockSuite 未能导出快照');
      const snapshot = JSON.parse(JSON.stringify(rawSnapshot)) as Record<string, unknown>;
      const spaceDoc = store.spaceDoc as Y.Doc;
      if (!(spaceDoc instanceof Y.Doc)) throw new Error('无法安全取得 BlockSuite Yjs 文档');
      const capturedUpdate = base64(Y.encodeStateAsUpdate(spaceDoc));
      const readable = initialResource.resourceKind === 'rich-page' ? richPageReadableMarkdown(basis, resourceRef.current, snapshot) : null;
      const projectionSha = readable === null ? null : await markdownSha256(readable);
      const body: BlockSuiteResourceWrite = {
        schemaVersion: 1, resourceId: resourceRef.current.resourceId,
        resourceKind: resourceRef.current.resourceKind, docId: resourceRef.current.docId,
        updateB64: capturedUpdate, snapshot: projectionSha ? bindRichPageSnapshot(snapshot, projectionSha) : snapshot,
      };
      const result = await notesApi.saveBlockSuiteResource(basis, resourceRef.current, body);
      nativeWriteCommitted = true;
      resourceRef.current = { ...resourceRef.current, updateB64: body.updateB64, snapshot: body.snapshot, etag: result.etag, note_etag: result.note_etag, artifact_set_etag: result.artifact_set_etag };
      noteRef.current = { ...noteRef.current, artifactSetEtag: result.artifact_set_etag };
      if (blobSourceRef.current) blobSourceRef.current.artifactSetEtag = result.artifact_set_etag;
      onNoteVersionChange(result.artifact_set_etag);
      if (readable !== null) {
        projectionWriteStarted = true;
        const projected = await notesApi.save({ ...basis, artifactSetEtag: result.artifact_set_etag }, readable);
        if (projected.etag !== projectionSha) throw new Error('Markdown 投影确认版本不一致；双方数据已保留');
        const nextArtifactSetEtag = projected.artifactSetEtag ?? result.artifact_set_etag;
        resourceRef.current = { ...resourceRef.current, updateB64: body.updateB64, snapshot: body.snapshot,
          note_etag: projected.etag, artifact_set_etag: nextArtifactSetEtag };
        noteRef.current = { ...projected, artifactSetEtag: nextArtifactSetEtag };
        if (blobSourceRef.current) blobSourceRef.current.artifactSetEtag = nextArtifactSetEtag;
        setProjectionConflict(false); onNoteSaved?.(noteRef.current);
      } else onResourceSaved?.(resourceRef.current, store);
      // Gfx may emit redundant Yjs layout transactions. Only clear dirty if
      // the complete current semantic snapshot still equals the submitted one.
      const currentSnapshot = initialResource.resourceKind === 'rich-page' ? nativeResourceSnapshot(store) : store.getTransformer().docToSnapshot(store);
      const unchanged = sequence === editSequence.current
        || (currentSnapshot !== null && typeof currentSnapshot === 'object'
          && sameBlockSuiteSnapshot(currentSnapshot, snapshot));
      if (unchanged) {
        dirtyRef.current = false; setDirty(false);
        setStatus('BlockSuite 资源已保存');
      } else {
        dirtyRef.current = true; setDirty(true); setRecoveryCopyReady(false);
        setStatus('先前版本已保存；有未保存的资源修改');
      }
      return unchanged;
    } catch (error) {
      const status = (error as Error & { status?: number })?.status;
      if (status === 412 || projectionWriteStarted || nativeWriteCommitted) {
        dirtyRef.current = true; setDirty(true);
        if (initialResource.resourceKind === 'rich-page') setProjectionConflict(true);
        setRecoveryCopyReady(false);
      }
      setStatus(status === 412
        ? initialResource.resourceKind === 'rich-page'
          ? nativeWriteCommitted
            ? 'Markdown 投影遇到版本冲突（412）；刚保存的富 Page 资源与双方 Markdown 均保留，请显式另存或恢复。'
            : '版本冲突（412）；远端资源与当前修改均保留，Core 未覆盖。请下载恢复副本后显式处理。'
          : '版本冲突（412）；Core 未覆盖现有资源。当前修改仍保留，请下载恢复副本后重试。'
        : error instanceof Error ? `保存失败；修改仍保留，可重试。${error.message}` : '保存失败；修改仍保留，可重试。');
      return false;
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  const currentStore = () => (host.current as (HTMLDivElement & { __sbBlockSuiteStore?: any }) | null)?.__sbBlockSuiteStore;
  const currentStd = () => (host.current as (HTMLDivElement & { __sbBlockSuiteStd?: BlockStdScope }) | null)?.__sbBlockSuiteStd;
  const refreshCanvasCards = (store: any) => {
    const cards = store.getBlocksByFlavour(CANVAS_REF_FLAVOUR).map(({ model }: any) => {
      let preview: ArchiveCanvasCard['preview'] = [];
      try { const value = JSON.parse(model.props.previewJson || '[]'); if (Array.isArray(value)) preview = value; } catch { /* invalid previews remain empty */ }
      return { blockId: model.id, resourceId: model.props.resourceId, title: model.props.title || '独立画布', revision: model.props.revision || '',
        dirty: model.props.state === 'creating', error: model.props.state === 'error' ? '读取失败' : undefined, preview };
    });
    setCanvasCards(cards);
  };
  const updateArchiveProperty = (key: keyof ArchiveProperties, value: unknown) => {
    if (key === 'tags' || key === 'type' || key === 'aliases' || key === 'created' || key === 'updated'
      || key === 'description' || key === 'source' || key === 'related') return;
    const store = currentStore();
    if (!store) return;
    store.spaceDoc.getMap('secondbrain-rich-page-properties').set(String(key), value);
    setArchiveProperties(current => ({ ...current, [key]: value }));
  };
  const updateArchiveTitle = (value: string) => {
    const store = currentStore();
    const title = store?.getBlocksByFlavour('affine:paragraph').find((item: any) => item.model.props.type === 'h1')?.model;
    if (!title) return;
    const text = title.props.text;
    if (text?.length) text.delete(0, text.length);
    text?.insert(0, value);
  };
  const currentTitle = () => {
    const title = currentStore()?.getBlocksByFlavour('affine:paragraph').find((item: any) => item.model.props.type === 'h1')?.model.props.text;
    return title?.toString?.() || '富 Page';
  };
  const switchViewMode = async (mode: 'page' | 'edgeless') => {
    if (mode === viewMode && archiveProperties.docMode === mode) {
      if (focusFrameAfterView.current && currentStd()) {
        try { archiveFocusFrame(currentStd()!, focusFrameAfterView.current); }
        catch (error) { setStatus(error instanceof Error ? error.message : '无法定位内嵌画布'); }
        focusFrameAfterView.current = null;
      }
      return;
    }
    if (saving || projectionConflict) return;
    const store = currentStore();
    if (!store) return;
    store.spaceDoc.getMap('secondbrain-rich-page-properties').set('docMode', mode);
    setArchiveProperties(current => ({ ...current, docMode: mode }));
    if (!await save()) return;
    setViewMode(mode);
  };
  const reloadFromCore = async () => {
    if (dirtyRef.current || projectionConflict || saving) return;
    try {
      const latestNote = await notesApi.readWithArtifactSet(noteRef.current.collection, noteRef.current.path);
      const latestResource = await notesApi.readBlockSuiteResource(latestNote, resourceRef.current.resourceId);
      if (latestResource.note_etag !== latestNote.etag || latestResource.artifact_set_etag !== latestNote.artifactSetEtag) throw Object.assign(new Error('读取期间版本变化'), { status: 412 });
      noteRef.current = latestNote; resourceRef.current = latestResource;
      onNoteVersionChange(latestNote.artifactSetEtag ?? '');
      setStatus('已从 Core 重新读取当前资源版本。'); setReloadGeneration(value => value + 1);
    } catch (error) { setStatus(`重读未完成；当前编辑会话仍保留。${error instanceof Error ? error.message : ''}`); }
  };
  const openBackups = async () => {
    if (dirtyRef.current && !await save()) return;
    onOpenBackups?.();
  };

  useEffect(() => {
    if (initialResource.resourceKind !== 'rich-page' || !storeReady) return;
    let active = true;
    void notesApi.readBlockSuiteSnapshots(noteRef.current).then(result => {
      if (active) setHasBackup(result.snapshots.length > 0);
    }).catch(() => { if (active) setHasBackup(false); });
    return () => { active = false; };
  }, [initialResource.resourceKind, storeReady, reloadGeneration]);

  useEffect(() => {
    if (initialResource.resourceKind !== 'rich-page' || !storeReady) return;
    const store = currentStore(), std = currentStd();
    const viewport = host.current?.querySelector<HTMLElement>('.sb-archive-viewport');
    if (!store || !std || !viewport) return;
    host.current?.classList.add('sb-archive-surface');
    const setReference = (blockId: string, patch: Record<string, unknown>) => {
      const model = store.getBlock(blockId)?.model;
      if (model) store.updateBlock(model, patch);
      refreshCanvasCards(store);
    };
    const cleanup = bindArchiveSurface(viewport, std, {
      onStatus: setStatus,
      onEmoji: setEmojiModelId,
      onCanvasCreate: async detail => {
        const block = store.getBlock(detail.blockId)?.model;
        if (!block || block.props.resourceId) return;
        try {
          const { createBlockSuiteResourcePayload } = await import('./BlockSuiteResourceEditor');
          const payload = createBlockSuiteResourcePayload('edgeless-canvas');
          const created = await notesApi.createBlockSuiteResource(noteRef.current, payload);
          noteRef.current = { ...noteRef.current, artifactSetEtag: created.artifact_set_etag };
          resourceRef.current = { ...resourceRef.current, artifact_set_etag: created.artifact_set_etag };
          if (blobSourceRef.current) blobSourceRef.current.artifactSetEtag = created.artifact_set_etag;
          onNoteVersionChange(created.artifact_set_etag);
          setReference(detail.blockId, { resourceId: created.resource_id, docId: created.doc_id, title: detail.title || '独立画布', state: 'ready', revision: created.etag, previewJson: '[]' });
          setStatus('独立画布已创建并绑定到此富 Page；保存富 Page 以持久化引用。');
        } catch (error) {
          setReference(detail.blockId, { state: 'error' });
          setStatus(`独立画布创建失败；引用仍可重试，未删除任何资源。${error instanceof Error ? error.message : ''}`);
        }
      },
      onCanvasOpen: async detail => {
        if (!detail.resourceId) return;
        const latest = await notesApi.readWithArtifactSet(noteRef.current.collection, noteRef.current.path);
        const resource = await notesApi.readBlockSuiteResource(latest, detail.resourceId);
        if (latest.etag !== resource.note_etag || latest.artifactSetEtag !== resource.artifact_set_etag) throw Object.assign(new Error('笔记或资源集合已变化，请刷新后重试'), { status: 412 });
        setNestedResource(resource);
      },
      onCanvasCopy: async detail => {
        const sourceNote = await notesApi.readWithArtifactSet(noteRef.current.collection, noteRef.current.path);
        const source = await notesApi.readBlockSuiteResource(sourceNote, detail.resourceId || '');
        if (source.resourceKind !== 'edgeless-canvas') throw new Error('只允许复制已保存的 Edgeless 画布');
        if (source.note_etag !== sourceNote.etag || source.artifact_set_etag !== sourceNote.artifactSetEtag) throw Object.assign(new Error('源画布版本已变化'), { status: 412 });
        const nestedIds = new Set<string>();
        const visit = (value: any) => { if (!value || typeof value !== 'object') return; if (Array.isArray(value)) return value.forEach(visit); for (const [key, item] of Object.entries(value)) { if (key === 'resourceId' && typeof item === 'string' && item !== source.resourceId) nestedIds.add(item); else visit(item); } };
        visit(source.snapshot);
        if (nestedIds.size) throw new Error('此画布含有嵌套画布引用；请先另存整个富 Page，以完整复制资源闭包。');
        const blobIds: string[] = [];
        const collect = (value: any) => { if (!value || typeof value !== 'object') return; if (Array.isArray(value)) return value.forEach(collect); for (const [key, item] of Object.entries(value)) { if (key === 'sourceId' && typeof item === 'string') blobIds.push(item); else collect(item); } };
        collect(source.snapshot);
        const blobSource = new NoteBoundBlockSuiteBlobSource(() => sourceNote);
        const destinationBlobs = new NoteBoundBlockSuiteBlobSource(() => noteRef.current, fetch, etag => {
          noteRef.current = { ...noteRef.current, artifactSetEtag: etag };
          resourceRef.current = { ...resourceRef.current, artifact_set_etag: etag };
          onNoteVersionChange(etag);
        });
        for (const id of new Set(blobIds)) {
          const blob = await blobSource.get(id);
          if (!blob) throw new Error('源画布图片缺失；未创建副本');
          await destinationBlobs.set(id, blob);
        }
        const payload: Omit<BlockSuiteResourceWrite, 'resourceId'> = { schemaVersion: 1, resourceKind: source.resourceKind, docId: crypto.randomUUID(), updateB64: source.updateB64, snapshot: source.snapshot };
        const created = await notesApi.createBlockSuiteResource({ ...noteRef.current, artifactSetEtag: destinationBlobs.artifactSetEtag }, payload);
        noteRef.current = { ...noteRef.current, artifactSetEtag: created.artifact_set_etag };
        resourceRef.current = { ...resourceRef.current, artifact_set_etag: created.artifact_set_etag };
        onNoteVersionChange(created.artifact_set_etag);
        setReference(detail.blockId, { resourceId: created.resource_id, docId: created.doc_id, revision: created.etag, previewJson: '[]', state: 'ready' });
        setStatus('画布已深拷贝为新资源；源画布仍保留。');
      },
      onCanvasRemoveReference: detail => {
        store.deleteBlock(detail.blockId);
        refreshCanvasCards(store);
        setStatus('已从富 Page 移除引用；原画布资源保留在笔记附件中。');
      },
      onCanvasResize: () => setStatus('画布预览尺寸已更新；保存富 Page 以持久化。'),
      onEmbeddedCanvasOpen: frameId => { focusFrameAfterView.current = frameId; void switchViewMode('edgeless'); },
    });
    archiveSurfaceRef.current = cleanup;
    refreshCanvasCards(store);
    return () => { cleanup.dispose(); if (archiveSurfaceRef.current === cleanup) archiveSurfaceRef.current = null; };
  }, [initialResource.resourceKind, storeReady, viewMode]);

  const addCanvasImage = async (file?: File) => {
    const store = (host.current as (HTMLDivElement & { __sbBlockSuiteStore?: any }) | null)?.__sbBlockSuiteStore;
    if (!file || !store || initialResource.resourceKind !== 'edgeless-canvas' || uploadingImage) return;
    setUploadingImage(true);
    setStatus('正在将图片写入当前笔记的 SHA-256 Blob 存储…');
    try {
      const sourceId = await store.blobSync.set(file);
      uploadedBlobCopies.current.set(sourceId, {
        contentType: file.type,
        bytes: new Uint8Array(await file.arrayBuffer()),
      });
      const surface = store.getBlocksByFlavour('affine:surface')[0]?.model;
      if (!surface) throw new Error('画布 surface 不存在；图片已上传，可重试。');
      const index = store.getBlocksByFlavour('affine:image').length;
      store.addBlock('affine:image', {
        sourceId, width: 320, height: 220, size: file.size, rotate: 0,
        xywh: `[${440 + index * 32},${100 + index * 28},320,220]`,
      }, surface.id);
      setStatus('图片已加入 Edgeless 画布；保存资源以持久化位置和引用。');
    } catch (error) {
      setStatus(`图片未能安全写入；未加入画布。${error instanceof Error ? error.message : ''}`);
    } finally { setUploadingImage(false); }
  };

  const downloadRecoveryCopy = async () => {
    const store = (host.current as (HTMLDivElement & { __sbBlockSuiteStore?: any }) | null)?.__sbBlockSuiteStore;
    if (!store) return;
    try {
      setStatus('正在生成恢复副本…');
      const sequence = editSequence.current;
      const snapshot = initialResource.resourceKind === 'rich-page' ? nativeResourceSnapshot(store) : store.getTransformer().docToSnapshot(store);
      const spaceDoc = store.spaceDoc as Y.Doc;
      const recoveryUpdate = base64(Y.encodeStateAsUpdate(spaceDoc));
      const blobs = [];
      const missingBlobs = new Set<string>();
      const missingResources = new Set<string>();
      let remoteMarkdown = null;
      let pinnedNote: Note | null = null;
      let remoteMarkdownReadError: string | null = null;
      try { pinnedNote = await notesApi.readWithArtifactSet(noteRef.current.collection, noteRef.current.path); }
      catch (error) { if (initialResource.resourceKind === 'rich-page') remoteMarkdownReadError = error instanceof Error ? error.message : 'remote markdown unavailable'; }
      if (initialResource.resourceKind === 'rich-page') remoteMarkdown = pinnedNote;
      const resourceClosure: BlockSuiteResource[] = [];
      const queuedResources = initialResource.resourceKind === 'rich-page' ? snapshotCanvasIds(snapshot) : [];
      const seenResources = new Set<string>();
      if (pinnedNote && initialResource.resourceKind === 'rich-page') {
        while (queuedResources.length) {
          const id = queuedResources.shift()!;
          if (seenResources.has(id)) continue;
          seenResources.add(id);
          try {
            if (seenResources.size > 64) throw new Error('引用资源超过每笔记容量限制');
            const child = await notesApi.readBlockSuiteResource(pinnedNote, id);
            if (child.note_etag !== pinnedNote.etag || child.artifact_set_etag !== pinnedNote.artifactSetEtag
              || child.resourceKind !== 'edgeless-canvas') throw Object.assign(new Error('引用画布版本不一致'), { status: 412 });
            resourceClosure.push(child);
            queuedResources.push(...snapshotCanvasIds(child.snapshot));
          } catch {
            missingResources.add(id);
          }
        }
      } else {
        for (const id of queuedResources) missingResources.add(id);
      }
      const blobIds = new Set([...referencedBlockSuiteBlobIds(store), ...snapshotBlobIds(snapshot),
        ...resourceClosure.flatMap(resource => snapshotBlobIds(resource.snapshot))]);
      const pinnedBlobSource = pinnedNote ? new NoteBoundBlockSuiteBlobSource(() => pinnedNote!) : null;
      for (const id of blobIds) {
        const local = uploadedBlobCopies.current.get(id);
        if (local) {
          blobs.push({ id, contentType: local.contentType, bytes: local.bytes.byteLength, base64: base64(local.bytes) });
          continue;
        }
        try {
          const data = await pinnedBlobSource?.get(id) ?? null;
          if (!data) { missingBlobs.add(id); continue; }
          const bytes = new Uint8Array(await data.arrayBuffer());
          blobs.push({ id, contentType: data.type, bytes: bytes.byteLength, base64: base64(bytes) });
        } catch {
          missingBlobs.add(id);
        }
      }
      const body = {
        remoteMarkdown,
        remoteMarkdownReadError,
        schemaVersion: 1,
        resourceId: resourceRef.current.resourceId,
        resourceKind: resourceRef.current.resourceKind,
        docId: resourceRef.current.docId,
        updateB64: recoveryUpdate,
        snapshot,
        resources: resourceClosure,
        missingResources: [...missingResources],
        blobs,
        missingBlobs: [...missingBlobs],
        complete: missingBlobs.size === 0 && missingResources.size === 0 && remoteMarkdownReadError === null,
        recoveryContext: { noteCollection: noteRef.current.collection, notePath: noteRef.current.path,
          noteEtag: noteRef.current.etag, resourceEtag: resourceRef.current.etag },
      };
      const blob = new Blob([JSON.stringify(body, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `blocksuite-${resourceRef.current.resourceId}-recovery.json`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
      if (sequence !== editSequence.current) {
        setRecoveryCopyReady(false);
        setStatus('已下载先前版本副本；有新修改，请重新下载后关闭。');
        return;
      }
      setRecoveryCopyReady(true);
      const complete = missingBlobs.size === 0 && missingResources.size === 0 && remoteMarkdownReadError === null;
      setRecoveryCopyComplete(complete);
      setStatus(complete
        ? '已下载包含 Yjs update、快照、引用画布与图片的完整恢复副本。'
        : `已下载部分恢复副本；缺失画布 ${missingResources.size} 个、Blob ${missingBlobs.size} 个，远端 Markdown 状态${remoteMarkdownReadError ? '未能读取' : '已读取'}，详见文件标记。`);
    } catch (error) {
      setStatus(`恢复副本生成失败；编辑内容仍保留。${error instanceof Error ? error.message : ''}`);
    }
  };

  return <div className="blocksuite-resource-backdrop" role="presentation">
    <section className="blocksuite-resource-dialog" role="dialog" aria-modal="true" aria-label={initialResource.resourceKind === 'database' ? 'BlockSuite 数据库资源' : initialResource.resourceKind === 'rich-page' ? 'BlockSuite 富 Page 资源' : 'BlockSuite Edgeless 资源'}>
      {initialResource.resourceKind === 'rich-page' ? <ArchiveDocumentHeader store={currentStore()} title={currentTitle()} status={status}
        readonly={saving || projectionConflict} properties={archiveProperties} readOnlyKeys={['tags', 'type', 'aliases', 'created', 'updated', 'description', 'source', 'related']}
        onTitleChange={updateArchiveTitle} onPropertyChange={updateArchiveProperty} onModeChange={mode => { void switchViewMode(mode); }}
        onSave={() => { void save(); }} onExportPdf={() => { const store = currentStore(); if (store) void archivePrintPdf(store, currentTitle()).catch(error => setStatus(`PDF 导出失败：${error instanceof Error ? error.message : ''}`)); }} />
        : <header><strong>{initialResource.resourceKind === 'database' ? '独立 Database 资源' : '独立 Edgeless 画布'}</strong>
        <span role="status" aria-live="polite">{status}</span>
        <button type="button" onClick={onClose} disabled={saving || (dirty && !recoveryCopyReady)}>
          {dirty && recoveryCopyReady
            ? recoveryCopyComplete ? '关闭（完整恢复副本已下载）' : '关闭（部分恢复副本已下载）'
            : '关闭'}
        </button></header>}
      {initialResource.resourceKind === 'rich-page' && <div className="blocksuite-resource-toolbar" role="toolbar" aria-label="富 Page 工具">
        <button type="button" onClick={() => { const store = currentStore(); if (store) void archiveExportHtml(store).then(html => {
          const url = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' })); const anchor = document.createElement('a');
          anchor.href = url; anchor.download = `${currentTitle()}.html`; anchor.click(); window.setTimeout(() => URL.revokeObjectURL(url), 0);
        }).catch(error => setStatus(`HTML 导出失败：${error instanceof Error ? error.message : ''}`)); }}>导出 HTML</button>
        <button type="button" onClick={onClose} disabled={!storeReady || saving || dirty}>关闭富 Page</button>
        <button type="button" disabled={!storeReady || saving} onClick={() => void downloadRecoveryCopy()}>下载资源恢复副本</button>
        <button type="button" onClick={() => { const std = currentStd(); if (std) { const report = archiveInspectMindMap(std); setMindMapReport(JSON.stringify(report, null, 2)); setDiagnosticStatus('思维导图视口检查完成'); } }}>检查思维导图</button>
        <button type="button" onClick={() => { const std = currentStd(); if (std) try { archiveFocusMindMap(std); setDiagnosticStatus('已定位思维导图'); } catch (error) { setDiagnosticStatus(error instanceof Error ? error.message : '无法定位思维导图'); } }}>定位思维导图</button>
        <button type="button" onClick={() => { const count = archiveSurfaceRef.current?.cropEmbeddedFrames() ?? 0; setStatus(count ? `已按现有内容调整 ${count} 个内嵌画布范围；保存富 Page 以持久化。` : '当前没有可裁切的内嵌画布。'); }}>裁切内嵌画布</button>
        <button type="button" onClick={() => { const store = currentStore(); if (store) { const url = URL.createObjectURL(new Blob([JSON.stringify(nativeResourceSnapshot(store), null, 2)], { type: 'application/json' })); const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'rich-page-snapshot.json'; anchor.click(); window.setTimeout(() => URL.revokeObjectURL(url), 0); } }}>导出 JSON 快照</button>
      </div>}
      <div className="blocksuite-resource-host" ref={host} data-kind={initialResource.resourceKind} />
      {initialResource.resourceKind === 'rich-page' && <ArchiveCanvasGallery cards={canvasCards} readonly={saving || projectionConflict}
        onCreate={() => { const store = currentStore(); const parent = store?.getBlocksByFlavour('affine:note')[0]?.model.id; if (!store || !parent) return;
          const blockId = store.addBlock(CANVAS_REF_FLAVOUR, { title: '新建画布', state: 'creating' }, parent);
          host.current?.querySelector<HTMLElement>('.sb-archive-viewport')?.dispatchEvent(new CustomEvent('sb-canvas-ref-create', { bubbles: true, detail: { blockId } })); }}
        onOpen={card => { host.current?.querySelector<HTMLElement>('.sb-archive-viewport')?.dispatchEvent(new CustomEvent(CANVAS_REF_OPEN_EVENT, { bubbles: true, detail: { blockId: card.blockId, resourceId: card.resourceId } })); }}
        onCopy={card => { host.current?.querySelector<HTMLElement>('.sb-archive-viewport')?.dispatchEvent(new CustomEvent(CANVAS_REF_COPY_EVENT, { bubbles: true, detail: { blockId: card.blockId, resourceId: card.resourceId } })); }}
        onRemoveReference={card => { const store = currentStore(); if (store) { store.deleteBlock(card.blockId); refreshCanvasCards(store); setStatus('已移除引用；画布原件仍保留。保存富 Page 以持久化。'); } }} />}
      {initialResource.resourceKind === 'rich-page' && <ArchiveNativeDiagnostics readonly={saving || dirty || projectionConflict} conflict={projectionConflict} hasConflictCopy={recoveryCopyReady} hasBackup={hasBackup}
        client={navigator.userAgent.slice(0, 160)} revision={resourceRef.current.etag} documentId={resourceRef.current.docId} report={`${diagnosticStatus}${mindMapReport ? `\n${mindMapReport}` : ''}`}
        actions={{ writeClientMarker: () => { const store = currentStore(); if (store) store.spaceDoc.getMap('secondbrain-rich-page-properties').set('clientMarker', crypto.randomUUID()); },
          inspectDocument: () => setDiagnosticStatus(`资源 ${resourceRef.current.resourceId} · ${resourceRef.current.resourceKind} · ${dirtyRef.current ? '未保存' : '已保存'}`),
          reloadAfterGuard: reloadFromCore, openConflictCopy: () => setDiagnosticStatus('冲突恢复副本采用下载的 JSON；可通过“另存为新富 Page”显式创建 Core 副本。'),
          createBackup: openBackups, restoreBackup: onOpenBackups, saveConflictCopy: downloadRecoveryCopy,
          inspectMindMap: () => { const std = currentStd(); if (std) setMindMapReport(JSON.stringify(archiveInspectMindMap(std), null, 2)); },
          focusMindMap: () => { const std = currentStd(); if (std) try { archiveFocusMindMap(std); } catch (error) { setDiagnosticStatus(error instanceof Error ? error.message : '无法定位'); } } }} />}
      {projectionConflict && initialResource.resourceKind === 'rich-page' && <section className="blocksuite-resource-conflict" role="alert">
        <p>Markdown 与富 Page 未自动合并或覆盖。可下载双方副本，或将当前本地富 Page 另存为新 Draft；原笔记与远端资源均保留。</p>
        <button type="button" disabled={saving || !storeReady} onClick={() => { void (async () => {
          const store = (host.current as any)?.__sbBlockSuiteStore;
          if (!store) return;
          setSaving(true);
          try {
            const snapshot = nativeResourceSnapshot(store);
            const forked = await forkRichPageNote(noteRef.current, { schemaVersion: 1, resourceId: resourceRef.current.resourceId,
              resourceKind: 'rich-page', docId: resourceRef.current.docId,
              updateB64: base64(Y.encodeStateAsUpdate(store.spaceDoc)), snapshot }, uploadedBlobCopies.current, remapNativeResourceReferences);
            onForked?.(forked.note, forked.resource);
          } catch (error) { setStatus(`另存未完成；原件与当前编辑均保留。${error instanceof Error ? error.message : ''}`); }
          finally { setSaving(false); }
        })(); }}>另存为新富 Page（保留原件）</button>
      </section>}
      <footer><span>资源通过 Markdown 附件引用关联；Yjs update 与同笔记 SHA-256 图片均受 Core ETag/配额保护。</span>
        {initialResource.resourceKind === 'edgeless-canvas' && <label className="blocksuite-resource-upload">
          添加画布图片
          <input aria-label="选择 Edgeless 图片" type="file" accept="image/png,image/jpeg,image/gif,image/webp" disabled={!storeReady || saving || uploadingImage}
            onChange={(event) => { void addCanvasImage(event.currentTarget.files?.[0]); event.currentTarget.value = ''; }} />
        </label>}
        <button type="button" onClick={() => void downloadRecoveryCopy()} disabled={!dirty || saving}>下载未保存恢复副本</button>
        <button type="button" onClick={() => void save()} disabled={!dirty || projectionConflict || saving || uploadingImage}>{saving ? '保存中…' : '保存资源'}</button>
      </footer>
    </section>
    {emojiModelId && currentStd() && <ArchiveEmojiPicker std={currentStd()!} modelId={emojiModelId} onClose={() => setEmojiModelId(null)} />}
    {nestedResource && <BlockSuiteResourceEditor key={`nested:${nestedResource.resourceId}`} note={noteRef.current} resource={nestedResource}
      onNoteVersionChange={etag => { noteRef.current = { ...noteRef.current, artifactSetEtag: etag }; resourceRef.current = { ...resourceRef.current, artifact_set_etag: etag }; if (blobSourceRef.current) blobSourceRef.current.artifactSetEtag = etag; onNoteVersionChange(etag); }}
        onResourceSaved={(resource, childStore) => {
          const shapes = childStore.getBlocksByFlavour('affine:surface')[0]?.model.elementModels ?? [];
          const preview = shapes.map((shape: any) => toCanvasPreviewShape(shape)).filter(Boolean);
          const parentStore = currentStore();
          const reference = parentStore?.getBlocksByFlavour(CANVAS_REF_FLAVOUR).find(({ model }: any) => model.props.resourceId === resource.resourceId)?.model;
          if (reference) parentStore.updateBlock(reference, { revision: resource.etag, previewJson: JSON.stringify(preview) });
          if (parentStore) refreshCanvasCards(parentStore);
        }}
      onClose={() => setNestedResource(null)} />}
  </div>;
}
