import { useEffect, useRef, useState } from 'react';
import { DatabaseBlockDataSource, databaseViewInitTemplate, richTextColumnConfig } from '@blocksuite/affine-block-database';
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
import { StoreExtensionManager, ViewExtensionManager } from '@blocksuite/affine-ext-loader';
import { BlockStdScope } from '@blocksuite/std';
import { Text } from '@blocksuite/store';
import * as Y from 'yjs';
import { notesApi, type BlockSuiteResource, type BlockSuiteResourceKind, type BlockSuiteResourceWrite, type Note } from './api/notes';
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

function managers() {
  return {
    stores: new StoreExtensionManager([
      FoundationStoreExtension, RootStoreExtension, NoteStoreExtension, ParagraphStoreExtension,
      ListStoreExtension, CodeStoreExtension, TableStoreExtension, DividerStoreExtension,
      InlinePresetStoreExtension, LatexStoreExtension, FootnoteStoreExtension, LinkStoreExtension,
      ReferenceStoreExtension, SurfaceStoreExtension, DataViewStoreExtension, DatabaseStoreExtension,
      EdgelessTextStoreExtension, BrushStoreExtension, ConnectorStoreExtension, GroupStoreExtension,
      MindmapStoreExtension, ShapeStoreExtension, GfxTextStoreExtension,
    ]),
    views: new ViewExtensionManager([
      FoundationViewExtension, RootViewExtension, NoteViewExtension, ParagraphViewExtension,
      ListViewExtension, CodeBlockViewExtension, TableViewExtension, DividerViewExtension,
      InlinePresetViewExtension, LatexViewExtension, FootnoteViewExtension, LinkViewExtension,
      MentionViewExtension, ReferenceViewExtension, SurfaceViewExtension, DataViewViewExtension,
      DatabaseViewExtension, EdgelessTextViewExtension, BrushViewExtension, ConnectorViewExtension,
      GroupViewExtension, MindmapViewExtension, PointerViewExtension, ShapeViewExtension,
      GfxTextViewExtension, EdgelessAutoConnectViewExtension, EdgelessDraggingAreaViewExtension,
      EdgelessSelectedRectViewExtension, EdgelessToolbarViewExtension, EdgelessZoomToolbarViewExtension,
      FrameTitleViewExtension, KeyboardToolbarViewExtension, NoteSlicerViewExtension,
      RemoteSelectionViewExtension, ViewportOverlayViewExtension,
    ]),
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

export function BlockSuiteResourceEditor({ note, resource: initialResource, onClose }: {
  note: Note; resource: BlockSuiteResource; onClose: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const resourceRef = useRef(initialResource);
  const noteRef = useRef(note);
  const dirtyRef = useRef(false);
  const [status, setStatus] = useState('正在载入 BlockSuite 资源…');
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [recoveryCopyReady, setRecoveryCopyReady] = useState(false);
  noteRef.current = note;

  useEffect(() => {
    let disposed = false;
    let workspace: TransientMarkdownWorkspace | undefined;
    let std: BlockStdScope | undefined;
    let offUpdate: (() => void) | undefined;
    const setup = async () => {
      try {
        const { stores, views } = managers();
        workspace = new TransientMarkdownWorkspace();
        workspace.storeExtensions = stores.get('store');
        workspace.meta.initialize();
        const doc = workspace.createDoc(initialResource.docId);
        Y.applyUpdate(doc.spaceDoc, unbase64(initialResource.updateB64));
        doc.load();
        const store = doc.getStore();
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
      if (store.getBlocksByFlavour(['affine:image', 'affine:attachment']).length > 0) {
        throw new Error('此资源尚不支持图片或 Blob 附件；已保留页面修改，未提交。');
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
      resourceRef.current = { ...resourceRef.current, etag: result.etag, note_etag: result.note_etag };
      dirtyRef.current = false;
      setDirty(false);
      setStatus('BlockSuite 资源已保存');
    } catch (error) {
      setStatus(error instanceof Error ? `保存失败；修改仍保留，可重试。${error.message}` : '保存失败；修改仍保留，可重试。');
    } finally {
      setSaving(false);
    }
  };

  const downloadRecoveryCopy = () => {
    const store = (host.current as (HTMLDivElement & { __sbBlockSuiteStore?: any }) | null)?.__sbBlockSuiteStore;
    if (!store) return;
    const snapshot = store.getTransformer().docToSnapshot(store);
    const spaceDoc = store.spaceDoc as Y.Doc;
    const body = {
      schemaVersion: 1,
      resourceId: resourceRef.current.resourceId,
      resourceKind: resourceRef.current.resourceKind,
      docId: resourceRef.current.docId,
      updateB64: base64(Y.encodeStateAsUpdate(spaceDoc)),
      snapshot,
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
  };

  return <div className="blocksuite-resource-backdrop" role="presentation">
    <section className="blocksuite-resource-dialog" role="dialog" aria-modal="true" aria-label={initialResource.resourceKind === 'database' ? 'BlockSuite 数据库资源' : 'BlockSuite Edgeless 资源'}>
      <header><strong>{initialResource.resourceKind === 'database' ? '独立 Database 资源' : '独立 Edgeless 画布'}</strong>
        <span role="status" aria-live="polite">{status}</span>
        <button type="button" onClick={onClose} disabled={saving || (dirty && !recoveryCopyReady)}>
          {dirty && recoveryCopyReady ? '关闭（恢复副本已下载）' : '关闭'}
        </button>
      </header>
      <div className="blocksuite-resource-host" ref={host} data-kind={initialResource.resourceKind} />
      <footer><span>资源通过 Markdown 附件引用关联；Yjs update 为保存源。保存冲突或失败时可下载未保存恢复副本。</span>
        <button type="button" onClick={downloadRecoveryCopy} disabled={!dirty || saving}>下载未保存恢复副本</button>
        <button type="button" onClick={() => void save()} disabled={!dirty || saving}>{saving ? '保存中…' : '保存资源'}</button>
      </footer>
    </section>
  </div>;
}
