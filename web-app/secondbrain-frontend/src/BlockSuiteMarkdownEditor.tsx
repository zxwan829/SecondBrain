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
import { LatexStoreExtension } from '@blocksuite/affine-inline-latex/store';
import { LatexViewExtension } from '@blocksuite/affine-inline-latex/view';
import { FootnoteStoreExtension } from '@blocksuite/affine-inline-footnote/store';
import { FootnoteViewExtension } from '@blocksuite/affine-inline-footnote/view';
import { LinkStoreExtension } from '@blocksuite/affine-inline-link/store';
import { LinkViewExtension } from '@blocksuite/affine-inline-link/view';
import { MentionViewExtension } from '@blocksuite/affine-inline-mention/view';
import { ReferenceStoreExtension } from '@blocksuite/affine-inline-reference/store';
import { ReferenceViewExtension } from '@blocksuite/affine-inline-reference/view';
import { SurfaceStoreExtension } from '@blocksuite/affine-block-surface/store';
import { SurfaceViewExtension } from '@blocksuite/affine-block-surface/view';
import { MarkdownAdapter } from '@blocksuite/affine-shared/adapters';
import { StoreExtensionManager, ViewExtensionManager } from '@blocksuite/affine-ext-loader';
import { BlockStdScope } from '@blocksuite/std';
import { Text } from '@blocksuite/store';
import { blockSuiteMarkdownMatches, blockSuiteMarkdownSupportsEditing, preserveSourceTerminalNewlines, splitOpaqueFrontmatter, type MarkdownParts } from './blocksuite-markdown';
import { TransientMarkdownWorkspace } from './transient-blocksuite-workspace';
import './blocksuite-notes.css';
import '@toeverything/theme/style.css';

type FallbackReason = 'invalid_frontmatter' | 'unsupported_syntax' | 'markdown_conversion_error'
  | 'unsafe_roundtrip' | 'content_mismatch' | 'view_initialization_error';

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
    TableStoreExtension, DividerStoreExtension, InlinePresetStoreExtension, LatexStoreExtension,
    FootnoteStoreExtension, LinkStoreExtension, ReferenceStoreExtension,
    SurfaceStoreExtension,
  ]);
  stores.configure(NoteStoreExtension, { mode: 'doc' });
  const views = new ViewExtensionManager([
    FoundationViewExtension, RootViewExtension, NoteViewExtension,
    ParagraphViewExtension, ListViewExtension, CodeBlockViewExtension,
    TableViewExtension, DividerViewExtension, InlinePresetViewExtension, LatexViewExtension,
    FootnoteViewExtension, LinkViewExtension, MentionViewExtension, ReferenceViewExtension,
    SurfaceViewExtension,
  ]);
  return { stores, views };
}

/**
 * BlockSuite is a transient local editing projection only. Its in-memory Y.Doc has
 * no persistence source; Core Notes Markdown/ETag remains the sole save path.
 */
export function BlockSuiteMarkdownEditor({ value, disabled, onChange, onFallback, onOpenVisualAsset, onOpenBlockSuiteResource }: {
  value: string; disabled: boolean; onChange: (markdown: string) => void; onFallback: (reason?: FallbackReason) => void;
  onOpenVisualAsset?: (filename: string) => void; onOpenBlockSuiteResource?: (filename: string) => void;
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
      let fallbackReason: FallbackReason = 'invalid_frontmatter';
      try {
        const split = splitOpaqueFrontmatter(valueRef.current);
        // Keep formats whose assets or Obsidian semantics belong to the existing editor on its fallback path.
        if (/!\[[^\]]*\]\([^)]*attachments\//i.test(split.body)
            || /\[\[[^\]]+\]\]|<\s*\/?[a-z][^>]*>/i.test(split.body)
            || /^(?:[ \t]*>[ \t]*)+\[![-\w]+\]/m.test(split.body)) {
          if (!disposed) onFallbackRef.current('unsupported_syntax');
          return;
        }
        fallbackReason = 'markdown_conversion_error';
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
          if (!disposed) onFallbackRef.current('content_mismatch');
          currentWorkspace.dispose();
          return;
        }
        if (disposed || !host.current) { currentWorkspace.dispose(); return; }
        fallbackReason = 'view_initialization_error';
        std = new BlockStdScope({ store: store as any, extensions: views.get('page') });
        const root = std.render();
        // RootViewExtension resolves `.affine-page-viewport` for page focus,
        // selection and coordinate services. Keep the same wrapper contract as
        // the pinned archive instead of mounting the Page root directly.
        const viewport = document.createElement('div');
        viewport.className = 'affine-page-viewport';
        viewport.append(root);
        host.current.replaceChildren(viewport);
        // Mounting the host is not enough to declare the editor ready: the
        // Page and its block views hydrate asynchronously after attachment.
        // Wait for BlockSuite's own update lifecycle before exposing the
        // saved/ready state to users and browser acceptance.
        await root.getUpdateComplete();
        if (disposed) return;
        const currentEditor: NonNullable<typeof editorRef.current> = { store, std, workspace: currentWorkspace, adapter, split };
        editorRef.current = currentEditor;
        const publish = () => {
          window.clearTimeout(timer.current);
          timer.current = window.setTimeout(() => {
            const current = editorRef.current;
            if (!current) return;
            void current.adapter.fromBlock(current.store.getBlocksByFlavour('affine:note')[0]!.model as any).then(result => {
              const exported = result?.file ?? '';
              const next = `${current.split.prefix}${preserveSourceTerminalNewlines(current.split.body, exported)}`;
              if (next === emittedRef.current) return;
              emittedRef.current = next;
              valueRef.current = next;
              if (!blockSuiteMarkdownSupportsEditing(exported)) {
                // Keep the projection in the fallback editor, but cancel the
                // parent's debounce before unsupported source can reach Core.
                onChangeRef.current(next);
                onFallbackRef.current('unsupported_syntax');
                return;
              }
              onChangeRef.current(next);
            }).catch(() => setStatus('导出失败，当前 Markdown 未发送保存。'));
          }, 250);
        };
        // BlockSuite text content is stored in nested Y.Text values. The
        // blockUpdated slot observes block/property changes, but does not fire
        // for every inline text edit, so listen to the transient document's
        // update event to publish all edits back through Core Notes.
        store.spaceDoc.on('update', publish);
        currentEditor.subscription = { unsubscribe: () => store.spaceDoc.off('update', publish) };
        setReady(true);
        setStatus('BlockSuite Page · Core Notes 保存');
      } catch (error) {
        if (!disposed) {
          setStatus(error instanceof Error ? error.message : 'BlockSuite 无法安全载入此 Markdown');
          onFallbackRef.current(fallbackReason);
        }
        try { std?.unmount(); } catch { /* Keep workspace disposal fail-safe. */ }
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
    const root = host.current;
    if (!root || (!onOpenVisualAsset && !onOpenBlockSuiteResource)) return;
    const onClick = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const anchor = target.closest('a[href]');
      if (!anchor) return;
      let filename: string;
      let kind: 'visual' | 'blocksuite' = 'visual';
      try {
        const url = new URL(anchor.getAttribute('href') || '', window.location.href);
        const match = url.pathname.match(/(?:^|\/)attachments\/([0-9a-f]{32}\.(?:mindmap|excalidraw|blocksuite)\.json)$/i);
        if (!match) return;
        filename = decodeURIComponent(match[1]);
        kind = filename.endsWith('.blocksuite.json') ? 'blocksuite' : 'visual';
      } catch { return; }
      if (kind === 'blocksuite' && !onOpenBlockSuiteResource) return;
      if (kind === 'visual' && !onOpenVisualAsset) return;
      event.preventDefault();
      if (kind === 'blocksuite') onOpenBlockSuiteResource?.(filename);
      else onOpenVisualAsset?.(filename);
    };
    root.addEventListener('click', onClick);
    return () => root.removeEventListener('click', onClick);
  }, [onOpenVisualAsset, onOpenBlockSuiteResource]);

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
        const next = `${current.split.prefix}${preserveSourceTerminalNewlines(current.split.body, exported?.file ?? '')}`;
        if (next !== emittedRef.current) {
          emittedRef.current = next;
          valueRef.current = next;
          onChangeRef.current(next);
        }
      } catch { setStatus('无法安全显示 Markdown 原文，当前编辑器仍保留。'); return; }
    }
    onFallbackRef.current();
  };

  return <section className="blocksuite-notes" aria-label="BlockSuite Markdown 编辑器">
    <div className="blocksuite-notes-bar"><span role="status">{status}</span><button type="button" onClick={() => void fallback()}>查看 Markdown 原文</button></div>
    <div className="blocksuite-notes-canvas" ref={host} aria-busy={!ready} data-disabled={disabled ? 'true' : 'false'} />
  </section>;
}
