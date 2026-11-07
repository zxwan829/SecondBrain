import React, { useEffect, useRef, useState } from 'react';
import { Picker } from 'emoji-mart';
import rawEmojiData from '@emoji-mart/data';
import type { EmojiMartData } from '@emoji-mart/data';
import emojiI18nZh from '@emoji-mart/data/i18n/zh.json';
import { insertContent } from '@blocksuite/affine-rich-text';
import { HtmlAdapter, MarkdownAdapter } from '@blocksuite/affine-shared/adapters';
import type { BlockStdScope } from '@blocksuite/std';
import { GfxControllerIdentifier } from '@blocksuite/std/gfx';
import { Bound } from '@blocksuite/global/gfx';
import { sanitizeArchiveExportHtml } from './archive-export-safety';
export { sanitizeArchiveExportHtml } from './archive-export-safety';
import { withChineseEmojiKeywords } from './emoji-localization';
import { PropertiesPanel, type MockProperties } from './properties-panel';

export { PropertiesPanel as ArchivePropertiesPanel, DEFAULT_MOCK_PROPERTIES as DEFAULT_ARCHIVE_PROPERTIES } from './properties-panel';
export type { MockProperties as ArchiveProperties } from './properties-panel';

/** Host owns the property persistence contract; this component never writes Markdown. */
export function ArchiveDocumentHeader({ store, title, status, readonly, properties, onTitleChange, onPropertyChange,
  onModeChange, onSave, onExportPdf, devMode = false }: {
  store: any; title: string; status: string; readonly: boolean; properties: MockProperties;
  onTitleChange: (title: string) => void; onPropertyChange: (key: keyof MockProperties, value: unknown) => void;
  onModeChange: (mode: 'page' | 'edgeless') => void; onSave: () => void;
  onExportPdf: () => void; devMode?: boolean;
}) {
  const [renamingTitle, setRenamingTitle] = useState(false);
  const critical = /失败|冲突|412|409|缺失|未能|ERROR/.test(status);
  const pending = critical || /未保存|正在|等待/.test(status);
  return <div className="sb-archive-surface issue258" data-page-width={properties.pageWidth} data-edgeless-theme={properties.edgelessTheme}>
    <div className="document-title-row"><div className="document-title-stack">
      <div className="document-breadcrumb" aria-label="文档位置">富文档 <span>/</span> {properties.folderCollection === 'Unfiled' ? '未归档' : properties.folderCollection}</div>
      {renamingTitle
        ? <input autoFocus className="document-title-input" aria-label="重命名文档" value={title} disabled={readonly} onChange={event => onTitleChange(event.target.value)} onBlur={() => setRenamingTitle(false)} onKeyDown={event => { if (event.key === 'Enter') event.currentTarget.blur(); if (event.key === 'Escape') setRenamingTitle(false); }} />
        : <h1 className="document-heading"><button type="button" disabled={readonly} className="document-title-edit" aria-label="重命名文档" title="重命名文档" onClick={() => setRenamingTitle(true)}>{title}<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m10.8 2.3 2.9 2.9M3 13l2.8-.5 7.7-7.7a1.3 1.3 0 0 0-1.8-1.8L4 10.7 3 13Z" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" /></svg></button></h1>}
    </div><div className="document-controls" role="toolbar" aria-label="文档操作">
      <span className="document-status" data-severity={critical ? 'critical' : pending ? 'pending' : 'quiet'} role={critical ? 'alert' : 'status'} aria-live={critical ? 'assertive' : 'polite'}>{status}</span>
      <button className="icon-action pdf-export-action" aria-label="导出 PDF" title="导出 PDF" onClick={onExportPdf}><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M11 2.5H4.5v15h11V7L11 2.5ZM11 2.5V7h4.5M10 9.5v5m-2-2 2 2 2-2" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg></button>
      <button className="icon-action" disabled={readonly} aria-label="撤销" title="撤销（⌘Z）" aria-keyshortcuts="Meta+Z" onClick={() => store?.undo()}><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M7 6 3.5 9.5 7 13M4 9.5h7a5 5 0 0 1 5 5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg></button>
      <button className="icon-action" disabled={readonly} aria-label="重做" title="重做（⇧⌘Z）" aria-keyshortcuts="Meta+Shift+Z" onClick={() => store?.redo()}><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m13 6 3.5 3.5L13 13m3-3.5h-7a5 5 0 0 0-5 5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg></button>
      <button className="icon-action save-action" disabled={readonly} aria-label="保存" title="保存文档" onClick={onSave}><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 3.5h10l2 2V16H4zM7 3.5v5h6v-5M7 16v-5h6v5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /></svg></button>
    </div></div>
    <fieldset disabled={readonly} style={{ border: 0, padding: 0, margin: 0 }}><PropertiesPanel values={properties} title={title} onTitleChange={onTitleChange} onChange={onPropertyChange} onModeChange={onModeChange} devMode={devMode} /></fieldset>
  </div>;
}

/** Uses the full pinned local catalogue and Chinese dictionary; no CDN locale fetch. */
export function ArchiveEmojiPicker({ std, modelId, onClose }: { std: BlockStdScope; modelId: string; onClose: () => void }) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!container.current) return;
    const picker = new Picker({
      data: withChineseEmojiKeywords(rawEmojiData as unknown as EmojiMartData), locale: 'zh', i18n: emojiI18nZh, autoFocus: true,
      onEmojiSelect: (emoji: { native?: string }) => {
        const model = std.store.getBlock(modelId)?.model;
        if (model && !std.store.readonly && emoji.native) insertContent(std, model, emoji.native);
        onClose();
      },
    }) as unknown as HTMLElement;
    const escape = (event: Event) => {
      if ((event as KeyboardEvent).key === 'Escape') { event.preventDefault(); event.stopPropagation(); onClose(); }
    };
    picker.addEventListener('keydown', escape, true);
    container.current.replaceChildren(picker);
    picker.shadowRoot?.addEventListener('keydown', escape, true);
    return () => { picker.removeEventListener('keydown', escape, true); picker.shadowRoot?.removeEventListener('keydown', escape, true); picker.remove(); };
  }, [std, modelId, onClose]);
  return <div className="sb-archive-surface"><div className="sb-emoji-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="sb-emoji-dialog" role="dialog" aria-modal="true" aria-label="选择表情"><button className="sb-emoji-close" onClick={onClose} aria-label="关闭表情选择器">关闭</button><div ref={container} /></section>
  </div></div>;
}

export async function archiveExportMarkdown(store: any) {
  const adapter = new MarkdownAdapter(store.getTransformer(), store.provider);
  const result = await adapter.fromDoc(store);
  if (!result || typeof result.file !== 'string') throw new Error('Markdown 无法无损表达当前格式；已停止导出，请使用 HTML 或原生恢复副本。');
  return result.file;
}
export async function archiveExportHtml(store: any) {
  const adapter = new HtmlAdapter(store.getTransformer(), store.provider);
  const result = await adapter.fromDoc(store);
  if (!result || typeof result.file !== 'string') throw new Error('HTML 导出失败；原文档未更改。');
  return sanitizeArchiveExportHtml(result.file);
}

/** Print an isolated, readonly, script-free view instead of reloading/mutating the live note. */
export async function archivePrintPdf(store: any, title: string) {
  const content = await archiveExportHtml(store);
  const frame = document.createElement('iframe');
  frame.title = '富文档 PDF 打印'; frame.setAttribute('sandbox', 'allow-same-origin allow-modals');
  Object.assign(frame.style, { position: 'fixed', width: '1024px', height: '768px', left: '-12000px', top: '0', border: '0' });
  const loaded = new Promise<void>(resolve => frame.addEventListener('load', () => resolve(), { once: true }));
  const origin = location.origin;
  frame.srcdoc = `<!doctype html><html><head><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data: blob: ${origin}; font-src ${origin}"><style>body{font:15px/1.65 Inter,ui-sans-serif,system-ui,sans-serif;color:#202936;margin:24px}table{border-collapse:collapse}td,th{border:1px solid #ccd3df;padding:8px}img{max-width:100%}@page{margin:16mm}@media print{body{margin:0}}</style></head><body>${content}</body></html>`;
  document.body.append(frame);
  try {
    await loaded;
    if (!frame.contentDocument || !frame.contentWindow) throw new Error('无法打开打印视图。');
    frame.contentDocument.title = title;
    await frame.contentDocument.fonts.ready;
    const images = [...frame.contentDocument.images];
    await Promise.all(images.map(image => image.decode().catch(() => undefined)));
    frame.contentWindow.addEventListener('afterprint', () => frame.remove(), { once: true });
    frame.contentWindow.focus(); frame.contentWindow.print();
  } catch (error) { frame.remove(); throw error; }
  window.setTimeout(() => frame.remove(), 60000);
}

export function archiveInspectMindMap(std: BlockStdScope) {
  const gfx = std.get(GfxControllerIdentifier);
  const surface = std.store.getBlocksByFlavour('affine:surface')[0]?.model as any;
  return { mode: gfx ? 'mounted' : 'unavailable', viewport: gfx.viewport.viewportBounds,
    elements: (surface?.elementModels ?? []).filter((element: any) => element.type === 'mindmap').map((element: any) => ({ id: element.id, bounds: element.elementBound, children: element.children?.length ?? 0 })) };
}
export function archiveFocusMindMap(std: BlockStdScope) {
  const gfx = std.get(GfxControllerIdentifier);
  const surface = std.store.getBlocksByFlavour('affine:surface')[0]?.model as any;
  const element = (surface?.elementModels ?? []).find((value: any) => value.type === 'mindmap');
  const bound = element?.elementBound;
  if (!bound || !(bound.w > 0 && bound.h > 0)) throw new Error('当前画布没有可定位的思维导图。');
  gfx.viewport.setViewportByBound(Bound.fromXYWH([bound.x, bound.y, bound.w, bound.h]), [48, 48, 48, 48], false, true);
}

export type ArchiveDiagnosticsActions = {
  writeClientMarker?: () => void; setParagraphAlign?: (align: 'left' | 'center' | 'right') => void; inspectDocument: () => void; reloadAfterGuard?: () => void;
  openPeer?: () => void; saveConflictCopy?: () => void; openConflictCopy?: () => void;
  createBackup?: () => void; restoreBackup?: () => void; inspectMindMap: () => void; focusMindMap: () => void;
};
/** Development tools remain explicit host actions, never mock routes or global cache deletion. */
export function ArchiveNativeDiagnostics({ actions, readonly, conflict, hasConflictCopy, hasBackup, client, revision, documentId, report }: {
  actions: ArchiveDiagnosticsActions; readonly: boolean; conflict: boolean; hasConflictCopy: boolean; hasBackup: boolean;
  client: string; revision: string; documentId: string; report: string;
}) {
  return <details className="diagnostics"><summary>高级工具与诊断</summary><div className="diagnostic-content">
    <div className="diagnostic-actions">
      <button disabled={readonly || !actions.writeClientMarker} onClick={actions.writeClientMarker}>写入客户端标记</button>
      <button disabled={readonly || !actions.setParagraphAlign} onClick={() => actions.setParagraphAlign?.('left')}>正文左对齐</button>
      <button disabled={readonly || !actions.setParagraphAlign} onClick={() => actions.setParagraphAlign?.('center')}>正文居中</button>
      <button disabled={readonly || !actions.setParagraphAlign} onClick={() => actions.setParagraphAlign?.('right')}>正文右对齐</button>
      <button onClick={actions.inspectDocument}>核对文档</button>
      <button disabled={readonly || !actions.reloadAfterGuard} onClick={actions.reloadAfterGuard}>清临时缓存并重载</button>
      <button disabled={!actions.openPeer} onClick={actions.openPeer}>打开冲突客户端</button>
      <button disabled={!conflict || hasConflictCopy || !actions.saveConflictCopy} onClick={actions.saveConflictCopy}>保存冲突副本</button>
      <button disabled={!hasConflictCopy || !actions.openConflictCopy} onClick={actions.openConflictCopy}>打开冲突副本</button>
      <button disabled={readonly || !actions.createBackup} onClick={actions.createBackup}>备份正文与画布</button>
      <button disabled={!hasBackup || !actions.restoreBackup} onClick={actions.restoreBackup}>恢复闭包备份</button>
      <button onClick={actions.inspectMindMap}>检查思维导图视口</button><button onClick={actions.focusMindMap}>定位思维导图</button>
    </div><div className="meta"><b>客户端：</b>{client}<br /><b>服务端版本：</b><code>{revision}</code><br /><b>文档：</b><code>{documentId}</code><pre>{report}</pre></div>
  </div></details>;
}
