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
import { StoreExtensionManager } from '@blocksuite/affine-ext-loader';
import { markdownViewManager } from './blocksuite-resource-views';
import { BlockStdScope } from '@blocksuite/std';
import { Text } from '@blocksuite/store';
import { blockSuiteMarkdownMatches, blockSuiteMarkdownSupportsEditing, preserveSourceTerminalNewlines, splitOpaqueFrontmatter, type MarkdownParts } from './blocksuite-markdown';
import { TransientMarkdownWorkspace } from './transient-blocksuite-workspace';
import './blocksuite-notes.css';
import '@toeverything/theme/style.css';
import { assertPlainSnapshotMarkdownCompatible, PlainMarkdownFormatError } from './plain-markdown-format-guard';
import * as Y from 'yjs';

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
  const views = markdownViewManager;
  return { stores, views };
}

/**
 * BlockSuite is a transient local editing projection only. Its in-memory Y.Doc has
 * no persistence source; Core Notes Markdown/ETag remains the sole save path.
 */
export function BlockSuiteMarkdownEditor({ value, disabled, onChange, onFallback, onOpenVisualAsset, onOpenBlockSuiteResource, onProjectionPending }: {
  onProjectionPending?: (pending: boolean) => void;
  value: string; disabled: boolean; onChange: (markdown: string) => void; onFallback: (reason?: FallbackReason, diagnostic?: 'illegal_constructor' | 'missing_custom_element' | 'custom_element_conflict' | 'duplicate_root' | 'duplicate_note' | 'duplicate_paragraph' | 'duplicate_database' | 'duplicate_data_view' | 'duplicate_edgeless_text' | 'duplicate_other' | 'missing_root' | 'blocksuite_error' | 'other', stage?: 'extension_setup' | 'scope_create' | 'host_render' | 'host_mount' | 'host_update') => void;
  onOpenVisualAsset?: (filename: string) => void; onOpenBlockSuiteResource?: (filename: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const editorRef = useRef<{ store: any; std: BlockStdScope; workspace: TransientMarkdownWorkspace; adapter: MarkdownAdapter; split: MarkdownParts; subscription?: { unsubscribe: () => void } } | null>(null);
  const pendingCallback = useRef(onProjectionPending);
  pendingCallback.current = onProjectionPending;
  const projectionSequence = useRef(0);
  const disabledRef = useRef(disabled);
  disabledRef.current = disabled;
  const valueRef = useRef(value);
  const emittedRef = useRef(value);
  const onChangeRef = useRef(onChange);
  const onFallbackRef = useRef(onFallback);
  onChangeRef.current = onChange;
  onFallbackRef.current = onFallback;
  const timer = useRef<number | undefined>(undefined);
  const [status, setStatus] = useState('正在载入 BlockSuite Page…');
  const [ready, setReady] = useState(false);
  const [formatViolation, setFormatViolation] = useState(false);
  const formatViolationRef = useRef(false);

  useEffect(() => {
    let disposed = false;
    let workspace: TransientMarkdownWorkspace | undefined;
    let std: BlockStdScope | undefined;
    const initialize = async () => {
      let fallbackReason: FallbackReason = 'invalid_frontmatter';
      let initializationStage: 'extension_setup' | 'scope_create' | 'host_render' | 'host_mount' | 'host_update' = 'extension_setup';
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
        // Populate the transient document before making its mounted view readonly.
        store.readonly = disabledRef.current;
        fallbackReason = 'view_initialization_error';
        const pageExtensions = views.get('page');
        initializationStage = 'scope_create';
        std = new BlockStdScope({ store: store as any, extensions: pageExtensions });
        initializationStage = 'host_render';
        const root = std.render();
        // RootViewExtension resolves `.affine-page-viewport` for page focus,
        // selection and coordinate services. Keep the same wrapper contract as
        // the pinned archive instead of mounting the Page root directly.
        const viewport = document.createElement('div');
        viewport.className = 'affine-page-viewport';
        viewport.append(root);
        initializationStage = 'host_mount';
        host.current.replaceChildren(viewport);
        // Mounting the host is not enough to declare the editor ready: the
        // Page and its block views hydrate asynchronously after attachment.
        // Wait for BlockSuite's own update lifecycle before exposing the
        // saved/ready state to users and browser acceptance.
        initializationStage = 'host_update';
        await root.getUpdateComplete();
        if (disposed) return;
        store.readonly = disabledRef.current;
        const currentEditor: NonNullable<typeof editorRef.current> = { store, std, workspace: currentWorkspace, adapter, split };
        editorRef.current = currentEditor;
        const publish = () => {
          const sequence = ++projectionSequence.current;
          pendingCallback.current?.(true);
          window.clearTimeout(timer.current);
          timer.current = window.setTimeout(() => {
            const current = editorRef.current;
            if (!current) return;
            void current.adapter.fromBlock(current.store.getBlocksByFlavour('affine:note')[0]!.model as any).then(result => {
              if (disposed || sequence !== projectionSequence.current || editorRef.current !== current) return;
              const exported = result?.file ?? '';
              const next = `${current.split.prefix}${preserveSourceTerminalNewlines(current.split.body, exported)}`;
              try {
                assertPlainSnapshotMarkdownCompatible(current.store.getTransformer().docToSnapshot(current.store));
              } catch (error) {
                if (!(error instanceof PlainMarkdownFormatError)) throw error;
                current.store.readonly = true;
                formatViolationRef.current = true;
                setFormatViolation(true);
                setStatus('此格式无法安全写回普通 Markdown；原文与本地编辑均保留。请下载完整恢复副本后显式另存为富 Page。');
                pendingCallback.current?.(true);
                return;
              }
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
            }).then(() => { if (!disposed && !formatViolationRef.current && editorRef.current === current && sequence === projectionSequence.current) pendingCallback.current?.(false); }).catch(() => setStatus('导出失败，当前 Markdown 未发送保存。'));
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
          const message = error instanceof Error ? error.message.toLowerCase() : '';
          const diagnostic = /illegal constructor/i.test(message) ? 'illegal_constructor'
            : /custom element .* not registered|not defined in the custom element registry/i.test(message) ? 'missing_custom_element'
              : /already been used with this registry|already defined/i.test(message)
                ? /affine-page-root|affine-edgeless-root/.test(message) ? 'duplicate_root'
                  : /affine-note/.test(message) ? 'duplicate_note'
                    : /affine-paragraph/.test(message) ? 'duplicate_paragraph'
                      : /affine-database/.test(message) ? 'duplicate_database'
                        : /affine-data-view/.test(message) ? 'duplicate_data_view'
                          : /affine-edgeless-text/.test(message) ? 'duplicate_edgeless_text' : 'duplicate_other'
                : /missing root block|no root model/i.test(message) ? 'missing_root'
                  : error instanceof Error && error.name === 'BlockSuiteError' ? 'blocksuite_error' : 'other';
          onFallbackRef.current(fallbackReason, diagnostic, initializationStage);
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

  useEffect(() => { if (editorRef.current) editorRef.current.store.readonly = disabled || formatViolation; }, [disabled, formatViolation]);

  useEffect(() => {
    const root = host.current;
    if (!root || (!onOpenVisualAsset && !onOpenBlockSuiteResource)) return;
    const onClick = (event: MouseEvent) => {
      // Lit links live in shadow roots; event.target is retargeted to their
      // host. Inspect the composed path to find the actual attachment anchor.
      const anchor = event.composedPath().find((node): node is HTMLAnchorElement =>
        node instanceof HTMLAnchorElement && node.hasAttribute('href'));
      if (!anchor) return;
      let filename: string;
      let kind: 'visual' | 'blocksuite' = 'visual';
      try {
        // AffineLink normalizes relative Markdown URLs to https:// URLs for
        // display. Route attachments from the original delta, not that href.
        const linkNode = event.composedPath().find(node => node instanceof Element && node.localName === 'affine-link') as (Element & { delta?: { attributes?: { link?: string } } }) | undefined;
        const sourceLink = linkNode?.delta?.attributes?.link ?? anchor.getAttribute('href') ?? '';
        if (!/^attachments\/[0-9a-f]{32}\.(?:mindmap|excalidraw|blocksuite)\.json$/i.test(sourceLink)) return;
        const url = new URL(sourceLink, window.location.href);
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
    root.addEventListener('click', onClick, true);
    return () => root.removeEventListener('click', onClick, true);
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
    if (formatViolation) { setStatus('当前格式不支持无损 Markdown 回退；请先下载完整恢复副本。'); return; }
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

  const downloadFormatRecovery = () => {
    const current = editorRef.current;
    if (!current) return;
    try {
      const snapshot = current.store.getTransformer().docToSnapshot(current.store);
      const bytes = Y.encodeStateAsUpdate(current.store.spaceDoc as Y.Doc);
      const binary = Array.from(bytes, value => String.fromCharCode(value)).join('');
      const body = { schemaVersion: 1, resourceKind: 'plain-markdown-format-recovery', originalMarkdown: valueRef.current,
        snapshot, updateB64: btoa(binary), complete: true };
      const url = URL.createObjectURL(new Blob([JSON.stringify(body, null, 2)], { type: 'application/json' }));
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'blocksuite-markdown-format-recovery.json'; anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
      pendingCallback.current?.(false);
      setStatus('完整本地恢复副本已下载；普通 Markdown 原文未被覆盖。');
    } catch (error) { setStatus(`恢复副本生成失败；本地编辑仍保留。${error instanceof Error ? error.message : ''}`); }
  };

  return <section className="blocksuite-notes" aria-label="BlockSuite Markdown 编辑器">
    <div className="blocksuite-notes-bar"><span role="status">{status}</span>{formatViolation
      ? <button type="button" onClick={downloadFormatRecovery}>下载完整恢复副本</button>
      : <button type="button" onClick={() => void fallback()}>查看 Markdown 原文</button>}</div>
    <div className="blocksuite-notes-canvas" ref={host} aria-busy={!ready} data-disabled={disabled || formatViolation ? 'true' : 'false'} />
  </section>;
}
