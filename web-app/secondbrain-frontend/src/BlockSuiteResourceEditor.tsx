import React, { useEffect, useRef, useState } from 'react';
import { DatabaseBlockDataSource, databaseViewInitTemplate, richTextColumnConfig } from '@blocksuite/affine-block-database';
import { ImageStoreExtension } from '@blocksuite/affine-block-image/store';
import { ImageViewExtension } from '@blocksuite/affine-block-image/view';
import { DatabaseStoreExtension } from '@blocksuite/affine-block-database/store';
import { DatabaseViewExtension } from '@blocksuite/affine-block-database/view';
import { DataViewStoreExtension } from '@blocksuite/affine-block-data-view/store';
import { DataViewViewExtension } from '@blocksuite/affine-block-data-view/view';
import { EdgelessTextStoreExtension } from '@blocksuite/affine-block-edgeless-text/store';
import { EdgelessTextViewExtension } from '@blocksuite/affine-block-edgeless-text/view';
import { BrushStoreExtension } from '@blocksuite/affine-gfx-brush/store';
import { BrushViewExtension } from '@blocksuite/affine-gfx-brush/view';
import { ConnectorStoreExtension } from '@blocksuite/affine-gfx-connector/store';
import { ConnectorViewExtension } from '@blocksuite/affine-gfx-connector/view';
import { GroupStoreExtension } from '@blocksuite/affine-gfx-group/store';
import { GroupViewExtension } from '@blocksuite/affine-gfx-group/view';
import { MindmapStoreExtension } from '@blocksuite/affine-gfx-mindmap/store';
import { MindmapViewExtension } from '@blocksuite/affine-gfx-mindmap/view';
import { PointerViewExtension } from '@blocksuite/affine-gfx-pointer/view';
import { ShapeType } from '@blocksuite/affine-model';
import { ShapeStoreExtension } from '@blocksuite/affine-gfx-shape/store';
import { ShapeViewExtension } from '@blocksuite/affine-gfx-shape/view';
import { TextStoreExtension as GfxTextStoreExtension } from '@blocksuite/affine-gfx-text/store';
import { TextViewExtension as GfxTextViewExtension } from '@blocksuite/affine-gfx-text/view';
import { EdgelessAutoConnectViewExtension } from '@blocksuite/affine-widget-edgeless-auto-connect/view';
import { EdgelessDraggingAreaViewExtension } from '@blocksuite/affine-widget-edgeless-dragging-area/view';
import { EdgelessSelectedRectViewExtension } from '@blocksuite/affine-widget-edgeless-selected-rect/view';
import { EdgelessToolbarViewExtension } from '@blocksuite/affine-widget-edgeless-toolbar/view';
import { EdgelessZoomToolbarViewExtension } from '@blocksuite/affine-widget-edgeless-zoom-toolbar/view';
import { FrameTitleViewExtension } from '@blocksuite/affine-widget-frame-title/view';
import { KeyboardToolbarViewExtension } from '@blocksuite/affine-widget-keyboard-toolbar/view';
import { NoteSlicerViewExtension } from '@blocksuite/affine-widget-note-slicer/view';
import { RemoteSelectionViewExtension } from '@blocksuite/affine-widget-remote-selection/view';
import { ViewportOverlayViewExtension } from '@blocksuite/affine-widget-viewport-overlay/view';
import { CodeBlockViewExtension } from '@blocksuite/affine-block-code/view';
import { DividerViewExtension } from '@blocksuite/affine-block-divider/view';
import { ListViewExtension } from '@blocksuite/affine-block-list/view';
import { NoteViewExtension } from '@blocksuite/affine-block-note/view';
import { ParagraphViewExtension } from '@blocksuite/affine-block-paragraph/view';
import { RootStoreExtension } from '@blocksuite/affine-block-root/store';
import { RootViewExtension } from '@blocksuite/affine-block-root/view';
import { effects as registerRootEffects } from '@blocksuite/affine-block-root/effects';
import { SurfaceStoreExtension } from '@blocksuite/affine-block-surface/store';
import { SurfaceViewExtension } from '@blocksuite/affine-block-surface/view';
import { TableViewExtension } from '@blocksuite/affine-block-table/view';
import { FoundationStoreExtension } from '@blocksuite/affine-foundation/store';
import { FoundationViewExtension } from '@blocksuite/affine-foundation/view';
import { CodeStoreExtension } from '@blocksuite/affine-block-code/store';
import { DividerStoreExtension } from '@blocksuite/affine-block-divider/store';
import { ListStoreExtension } from '@blocksuite/affine-block-list/store';
import { NoteStoreExtension } from '@blocksuite/affine-block-note/store';
import { ParagraphStoreExtension } from '@blocksuite/affine-block-paragraph/store';
import { TableStoreExtension } from '@blocksuite/affine-block-table/store';
import { LinkStoreExtension } from '@blocksuite/affine-inline-link/store';
import { LinkViewExtension } from '@blocksuite/affine-inline-link/view';
import { InlinePresetStoreExtension } from '@blocksuite/affine-inline-preset/store';
import { InlinePresetViewExtension } from '@blocksuite/affine-inline-preset/view';
import { FootnoteStoreExtension } from '@blocksuite/affine-inline-footnote/store';
import { FootnoteViewExtension } from '@blocksuite/affine-inline-footnote/view';
import { LatexStoreExtension } from '@blocksuite/affine-inline-latex/store';
import { LatexViewExtension } from '@blocksuite/affine-inline-latex/view';
import { MentionViewExtension } from '@blocksuite/affine-inline-mention/view';
import { ReferenceStoreExtension } from '@blocksuite/affine-inline-reference/store';
import { ReferenceViewExtension } from '@blocksuite/affine-inline-reference/view';
import { StoreExtensionManager } from '@blocksuite/affine-ext-loader';
import { prepareViewExtensions, resourceViewManager } from './blocksuite-resource-views';
import { BlockStdScope } from '@blocksuite/std';
import { Text } from '@blocksuite/store';
import * as Y from 'yjs';
import { notesApi, type BlockSuiteResource, type BlockSuiteResourceKind, type BlockSuiteResourceWrite, type Note } from './api/notes';
import { NoteBoundBlockSuiteBlobSource } from './api/notes-blocksuite-blobs';
import { TransientMarkdownWorkspace } from './transient-blocksuite-workspace';
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

function managers() {
  return {
    stores: new StoreExtensionManager([
      FoundationStoreExtension, RootStoreExtension, NoteStoreExtension, ParagraphStoreExtension,
      ListStoreExtension, CodeStoreExtension, TableStoreExtension, DividerStoreExtension,
      InlinePresetStoreExtension, LatexStoreExtension, FootnoteStoreExtension, LinkStoreExtension,
      ReferenceStoreExtension, SurfaceStoreExtension, DataViewStoreExtension, DatabaseStoreExtension, ImageStoreExtension,
      EdgelessTextStoreExtension, BrushStoreExtension, ConnectorStoreExtension, GroupStoreExtension,
      MindmapStoreExtension, ShapeStoreExtension, GfxTextStoreExtension,
    ]),
    views: resourceViewManager,
  };
}

function seedResource(store: any, kind: BlockSuiteResourceKind) {
  const root = store.addBlock('affine:page', {}, null);
  const surface = store.addBlock('affine:surface', {}, root, 0);
  if (kind === 'database') {
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
    const sticky = store.addBlock('affine:edgeless-text', { xywh: '[120,300,240,100]' }, surface);
    store.addBlock('affine:paragraph', { text: new Text('独立 Edgeless 便签') }, sticky);
  }
}

export function createBlockSuiteResourcePayload(kind: BlockSuiteResourceKind): Omit<BlockSuiteResourceWrite, 'resourceId'> {
  const workspace = new TransientMarkdownWorkspace();
  try {
    const { stores } = managers();
    workspace.storeExtensions = stores.get('store');
    workspace.meta.initialize();
    const docId = crypto.randomUUID();
    const doc = workspace.createDoc(docId).load();
    const store = doc.getStore();
    seedResource(store, kind);
    const snapshot = store.getTransformer().docToSnapshot(store);
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
    const { stores } = managers();
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

export function BlockSuiteResourceEditor({ note, resource: initialResource, onClose, onNoteVersionChange }: {
  note: Note; resource: BlockSuiteResource; onClose: () => void; onNoteVersionChange: (artifactSetEtag: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const resourceRef = useRef(initialResource);
  const noteRef = useRef(note);
  const dirtyRef = useRef(false);
  // Keep the exact bytes uploaded in this editing session so a later artifact
  // set conflict cannot make the only recovery copy depend on a stale server ETag.
  const uploadedBlobCopies = useRef(new Map<string, { contentType: string; bytes: Uint8Array }>());
  const [status, setStatus] = useState('正在载入 BlockSuite 资源…');
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [recoveryCopyReady, setRecoveryCopyReady] = useState(false);
  const [recoveryCopyComplete, setRecoveryCopyComplete] = useState(false);
  const [uploadingImage, setUploadingImage] = useState(false);
  noteRef.current = note;

  useEffect(() => {
    let disposed = false;
    let workspace: TransientMarkdownWorkspace | undefined;
    let std: BlockStdScope | undefined;
    let offUpdate: (() => void) | undefined;
    const setup = async () => {
      try {
        const { stores, views } = managers();
        workspace = new TransientMarkdownWorkspace(new NoteBoundBlockSuiteBlobSource(() => noteRef.current, fetch, (etag) => {
          noteRef.current = { ...noteRef.current, artifactSetEtag: etag };
          resourceRef.current = { ...resourceRef.current, artifact_set_etag: etag };
          onNoteVersionChange(etag);
        }));
        workspace.storeExtensions = stores.get('store');
        workspace.meta.initialize();
        const doc = workspace.createDoc(initialResource.docId);
        Y.applyUpdate(doc.spaceDoc, unbase64(initialResource.updateB64));
        doc.load();
        const store = doc.getStore();
        prepareViewExtensions();
        const extensionSet = views.get(initialResource.resourceKind === 'database' ? 'page' : 'edgeless');
        std = new BlockStdScope({ store: store as any, extensions: extensionSet });
        const root = std.render();
        if (disposed || !host.current) { workspace.dispose(); return; }
        const viewport = document.createElement('div');
        viewport.className = initialResource.resourceKind === 'database' ? 'affine-page-viewport' : 'affine-edgeless-viewport';
        host.current.replaceChildren(viewport);
        viewport.append(root);
        await root.getUpdateComplete();
        if (disposed) return;
        const onUpdate = () => {
          dirtyRef.current = true;
          setDirty(true);
          setRecoveryCopyReady(false);
          setStatus('有未保存的资源修改');
        };
        doc.spaceDoc.on('update', onUpdate);
        offUpdate = () => doc.spaceDoc.off('update', onUpdate);
        setStatus(initialResource.resourceKind === 'database' ? 'BlockSuite Database 已就绪' : 'BlockSuite Edgeless 画布已就绪');
        Object.assign(host.current, { __sbBlockSuiteStore: store });
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
  }, [initialResource]);

  const save = async () => {
    const store = (host.current as (HTMLDivElement & { __sbBlockSuiteStore?: any }) | null)?.__sbBlockSuiteStore;
    if (!store || saving) return;
    setSaving(true);
    setStatus('正在保存 BlockSuite 资源…');
    try {
      const blobIds = referencedBlockSuiteBlobIds(store);
      for (const id of blobIds) {
        if (!await store.blobSync.get(id)) throw new Error(`资源引用的 Blob ${id} 不在此笔记的 Core 存储中；已保留页面修改，未提交。`);
      }
      const snapshot = store.getTransformer().docToSnapshot(store);
      if (!snapshot || typeof snapshot !== 'object') throw new Error('BlockSuite 未能导出快照');
      const spaceDoc = store.spaceDoc as Y.Doc;
      if (!(spaceDoc instanceof Y.Doc)) throw new Error('无法安全取得 BlockSuite Yjs 文档');
      const body: BlockSuiteResourceWrite = {
        schemaVersion: 1, resourceId: resourceRef.current.resourceId,
        resourceKind: resourceRef.current.resourceKind, docId: resourceRef.current.docId,
        updateB64: base64(Y.encodeStateAsUpdate(spaceDoc)), snapshot: snapshot as Record<string, unknown>,
      };
      const result = await notesApi.saveBlockSuiteResource(noteRef.current, resourceRef.current, body);
      resourceRef.current = { ...resourceRef.current, etag: result.etag, note_etag: result.note_etag, artifact_set_etag: result.artifact_set_etag };
      noteRef.current = { ...noteRef.current, artifactSetEtag: result.artifact_set_etag };
      onNoteVersionChange(result.artifact_set_etag);
      dirtyRef.current = false;
      setDirty(false);
      setStatus('BlockSuite 资源已保存');
    } catch (error) {
      const status = (error as Error & { status?: number })?.status;
      setStatus(status === 412
        ? '版本冲突（412）；Core 未覆盖现有资源。当前修改仍保留，请下载恢复副本后重新载入。'
        : error instanceof Error ? `保存失败；修改仍保留，可重试。${error.message}` : '保存失败；修改仍保留，可重试。');
    } finally {
      setSaving(false);
    }
  };

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
        xywh: `[${80 + index * 32},${100 + index * 28},320,220]`,
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
      const snapshot = store.getTransformer().docToSnapshot(store);
      const spaceDoc = store.spaceDoc as Y.Doc;
      const blobs = [];
      const missingBlobs: string[] = [];
      for (const id of referencedBlockSuiteBlobIds(store)) {
        const local = uploadedBlobCopies.current.get(id);
        if (local) {
          blobs.push({ id, contentType: local.contentType, bytes: local.bytes.byteLength, base64: base64(local.bytes) });
          continue;
        }
        try {
          const data = await store.blobSync.get(id) as Blob | null;
          if (!data) { missingBlobs.push(id); continue; }
          const bytes = new Uint8Array(await data.arrayBuffer());
          blobs.push({ id, contentType: data.type, bytes: bytes.byteLength, base64: base64(bytes) });
        } catch {
          // Preserve Yjs and any locally cached blobs even when a concurrent
          // attachment-set change makes the remaining remote reads unsafe.
          missingBlobs.push(id);
        }
      }
      const body = {
        schemaVersion: 1,
        resourceId: resourceRef.current.resourceId,
        resourceKind: resourceRef.current.resourceKind,
        docId: resourceRef.current.docId,
        updateB64: base64(Y.encodeStateAsUpdate(spaceDoc)),
        snapshot,
        blobs,
        missingBlobs,
        complete: missingBlobs.length === 0,
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
      setRecoveryCopyReady(true);
      setRecoveryCopyComplete(missingBlobs.length === 0);
      setStatus(missingBlobs.length === 0
        ? '已下载包含 Yjs update、快照与所引用图片的完整恢复副本。'
        : `已下载部分恢复副本；${missingBlobs.length} 个图片 Blob 未包含，已在文件中明确列出。`);
    } catch (error) {
      setStatus(`恢复副本生成失败；编辑内容仍保留。${error instanceof Error ? error.message : ''}`);
    }
  };

  return <div className="blocksuite-resource-backdrop" role="presentation">
    <section className="blocksuite-resource-dialog" role="dialog" aria-modal="true" aria-label={initialResource.resourceKind === 'database' ? 'BlockSuite 数据库资源' : 'BlockSuite Edgeless 资源'}>
      <header><strong>{initialResource.resourceKind === 'database' ? '独立 Database 资源' : '独立 Edgeless 画布'}</strong>
        <span role="status" aria-live="polite">{status}</span>
        <button type="button" onClick={onClose} disabled={saving || (dirty && !recoveryCopyReady)}>
          {dirty && recoveryCopyReady
            ? recoveryCopyComplete ? '关闭（完整恢复副本已下载）' : '关闭（部分恢复副本已下载）'
            : '关闭'}
        </button>
      </header>
      <div className="blocksuite-resource-host" ref={host} data-kind={initialResource.resourceKind} />
      <footer><span>资源通过 Markdown 附件引用关联；Yjs update 与同笔记 SHA-256 图片均受 Core ETag/配额保护。</span>
        {initialResource.resourceKind === 'edgeless-canvas' && <label className="blocksuite-resource-upload">
          添加画布图片
          <input aria-label="选择 Edgeless 图片" type="file" accept="image/png,image/jpeg,image/gif,image/webp" disabled={saving || uploadingImage}
            onChange={(event) => { void addCanvasImage(event.currentTarget.files?.[0]); event.currentTarget.value = ''; }} />
        </label>}
        <button type="button" onClick={() => void downloadRecoveryCopy()} disabled={!dirty || saving}>下载未保存恢复副本</button>
        <button type="button" onClick={() => void save()} disabled={!dirty || saving || uploadingImage}>{saving ? '保存中…' : '保存资源'}</button>
      </footer>
    </section>
  </div>;
}
