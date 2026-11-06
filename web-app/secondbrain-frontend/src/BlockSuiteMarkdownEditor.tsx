import React, { useEffect, useRef, useState } from 'react';
import { RootStoreExtension } from '@blocksuite/affine-block-root/store';
import { RootViewExtension } from '@blocksuite/affine-block-root/view';
import { NoteStoreExtension } from '@blocksuite/affine-block-note/store';
import { NoteViewExtension } from '@blocksuite/affine-block-note/view';
import { ParagraphStoreExtension } from '@blocksuite/affine-block-paragraph/store';
import { ParagraphViewExtension } from '@blocksuite/affine-block-paragraph/view';
import { ListStoreExtension } from '@blocksuite/affine-block-list/store';
import { ListViewExtension } from '@blocksuite/affine-block-list/view';
import { CodeStoreExtension } from '@blocksuite/affine-block-code/store';
import { CodeBlockViewExtension } from '@blocksuite/affine-block-code/view';
import { TableStoreExtension } from '@blocksuite/affine-block-table/store';
import { TableViewExtension } from '@blocksuite/affine-block-table/view';
import { DividerStoreExtension } from '@blocksuite/affine-block-divider/store';
import { DividerViewExtension } from '@blocksuite/affine-block-divider/view';
import { FoundationStoreExtension } from '@blocksuite/affine-foundation/store';
import { FoundationViewExtension } from '@blocksuite/affine-foundation/view';
import { InlinePresetStoreExtension } from '@blocksuite/affine-inline-preset/store';
import { InlinePresetViewExtension } from '@blocksuite/affine-inline-preset/view';
import { SurfaceStoreExtension } from '@blocksuite/affine-block-surface/store';
import { SurfaceViewExtension } from '@blocksuite/affine-block-surface/view';
import { MarkdownAdapter } from '@blocksuite/affine-shared/adapters';
import { StoreExtensionManager, ViewExtensionManager } from '@blocksuite/affine-ext-loader';
import { BlockStdScope } from '@blocksuite/std';
import { Text } from '@blocksuite/store';
import { blockSuiteMarkdownMatches, splitOpaqueFrontmatter, type MarkdownParts } from './blocksuite-markdown';
import { TransientMarkdownWorkspace } from './transient-blocksuite-workspace';
import './blocksuite-notes.css';
import '@toeverything/theme/style.css';

function markdownAdapter(store: any) {
  const job = store.getTransformer();
  // v0.22.4's source entrypoints and declaration entrypoints expose duplicate
  // nominal Store types. Keep that package inconsistency at this adapter seam.
  return new MarkdownAdapter(job as any, store.provider as any);
}

function makeManagers() {
  const stores = new StoreExtensionManager([
    FoundationStoreExtension, RootStoreExtension, NoteStoreExtension,
    ParagraphStoreExtension, ListStoreExtension, CodeStoreExtension,
    TableStoreExtension, DividerStoreExtension, InlinePresetStoreExtension,
    SurfaceStoreExtension,
  ]);
  stores.configure(NoteStoreExtension, { mode: 'doc' });
  const views = new ViewExtensionManager([
    FoundationViewExtension, RootViewExtension, NoteViewExtension,
    ParagraphViewExtension, ListViewExtension, CodeBlockViewExtension,
    TableViewExtension, DividerViewExtension, InlinePresetViewExtension,
    SurfaceViewExtension,
  ]);
  return { stores, views };
}

/**
 * BlockSuite is a transient local editing projection only. Its in-memory Y.Doc has
 * no persistence source; Core Notes Markdown/ETag remains the sole save path.
 */
export function BlockSuiteMarkdownEditor({ value, disabled, onChange, onFallback }: {
  value: string; disabled: boolean; onChange: (markdown: string) => void; onFallback: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const editorRef = useRef<{ store: any; std: BlockStdScope; workspace: TransientMarkdownWorkspace; adapter: MarkdownAdapter; split: MarkdownParts; subscription?: { unsubscribe: () => void } } | null>(null);
  const valueRef = useRef(value);
  const emittedRef = useRef(value);
  const onChangeRef = useRef(onChange);
  const onFallbackRef = useRef(onFallback);
  onChangeRef.current = onChange;
  onFallbackRef.current = onFallback;
  const timer = useRef<number | undefined>(undefined);
  const [status, setStatus] = useState('正在载入 BlockSuite Page…');
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let disposed = false;
    let workspace: TransientMarkdownWorkspace | undefined;
    let std: BlockStdScope | undefined;
    const initialize = async () => {
      try {
        const split = splitOpaqueFrontmatter(valueRef.current);
        // Keep formats whose assets or Obsidian semantics belong to the existing editor on its fallback path.
        if (/!\[[^\]]*\]\([^)]*attachments\//i.test(split.body) || /\[\[[^\]]+\]\]|<\s*\/?[a-z][^>]*>/i.test(split.body)) {
          throw new Error('此笔记含附件或 Obsidian 专用语法');
        }
        const { stores, views } = makeManagers();
        const currentWorkspace = new TransientMarkdownWorkspace();
        workspace = currentWorkspace;
        currentWorkspace.storeExtensions = stores.get('store');
        currentWorkspace.meta.initialize();
        const localDoc = currentWorkspace.createDoc(`markdown-${crypto.randomUUID()}`);
        localDoc.load();
        const store = localDoc.getStore();
        store.readonly = disabled;
        const adapter = markdownAdapter(store);
        // Match the pinned BlockSuite Page document contract: the Page root
        // contains a surface before the Markdown adapter creates its note block.
        const rootId = store.addBlock('affine:page', { title: new Text('') }, null);
        store.addBlock('affine:surface', {}, rootId, 0);
        await adapter.toBlock({ file: split.body }, store as any, rootId);
        const exported = await adapter.fromBlock(store.getBlocksByFlavour('affine:note')[0]!.model as any);
        const body = exported?.file ?? '';
        if (!blockSuiteMarkdownMatches(split.body, body)) {
          throw new Error('此笔记无法通过 BlockSuite 安全往返');
        }
        if (disposed || !host.current) { currentWorkspace.dispose(); return; }
        std = new BlockStdScope({ store: store as any, extensions: views.get('page') });
        const root = std.render();
        // RootViewExtension resolves `.affine-page-viewport` for page focus,
        // selection and coordinate services. Keep the same wrapper contract as
        // the pinned archive instead of mounting the Page root directly.
        const viewport = document.createElement('div');
        viewport.className = 'affine-page-viewport';
        viewport.append(root);
        host.current.replaceChildren(viewport);
        const currentEditor: NonNullable<typeof editorRef.current> = { store, std, workspace: currentWorkspace, adapter, split };
        editorRef.current = currentEditor;
        const publish = () => {
          window.clearTimeout(timer.current);
          timer.current = window.setTimeout(() => {
            const current = editorRef.current;
            if (!current) return;
            void current.adapter.fromBlock(current.store.getBlocksByFlavour('affine:note')[0]!.model as any).then(result => {
              const next = `${current.split.prefix}${result?.file ?? ''}`;
              if (next === emittedRef.current) return;
              emittedRef.current = next;
              valueRef.current = next;
              onChangeRef.current(next);
            }).catch(() => setStatus('导出失败，当前 Markdown 未发送保存。'));
          }, 250);
        };
        const subscription = store.slots.blockUpdated.subscribe(publish);
        currentEditor.subscription = subscription;
        setReady(true);
        setStatus('BlockSuite Page · Core Notes 保存');
      } catch (error) {
        if (!disposed) {
          setStatus(error instanceof Error ? error.message : 'BlockSuite 无法安全载入此 Markdown');
          onFallbackRef.current();
        }
        workspace?.dispose();
      }
    };
    void initialize();
    return () => {
      disposed = true;
      window.clearTimeout(timer.current);
      editorRef.current?.subscription?.unsubscribe();
      editorRef.current?.std.unmount();
      editorRef.current?.workspace.dispose();
      editorRef.current = null;
      host.current?.replaceChildren();
    };
  }, []);

  useEffect(() => { if (editorRef.current) editorRef.current.store.readonly = disabled; }, [disabled]);

  useEffect(() => {
    // A parent save response updates the prop to the same serialized content. Do not
    // reconstruct the local editor for that acknowledgement; re-open uses a new key.
    if (value !== emittedRef.current && value !== valueRef.current) {
      if (editorRef.current) editorRef.current.store.readonly = true;
      setStatus('笔记内容已从外部更新，请重新打开以避免覆盖。');
      setReady(false);
    }
  }, [value]);

  const fallback = async () => {
    const current = editorRef.current;
    if (current) {
      try {
        const exported = await current.adapter.fromBlock(current.store.getBlocksByFlavour('affine:note')[0]!.model as any);
        const next = `${current.split.prefix}${exported?.file ?? ''}`;
        if (next !== emittedRef.current) {
          emittedRef.current = next;
          valueRef.current = next;
          onChangeRef.current(next);
        }
      } catch { setStatus('切换旧版编辑器失败，当前编辑器仍保留。'); return; }
    }
    onFallbackRef.current();
  };

  return <section className="blocksuite-notes" aria-label="BlockSuite Markdown 编辑器">
    <div className="blocksuite-notes-bar"><span role="status">{status}</span><button type="button" onClick={() => void fallback()}>切回旧版编辑器</button></div>
    <div className="blocksuite-notes-canvas" ref={host} aria-busy={!ready} data-disabled={disabled ? 'true' : 'false'} />
  </section>;
}
