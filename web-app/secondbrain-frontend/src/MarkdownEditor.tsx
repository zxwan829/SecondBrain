import React, { useEffect, useMemo, useRef, useState } from 'react';
import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from '@tiptap/markdown';
import Image from '@tiptap/extension-image';
import { Table } from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableHeader from '@tiptap/extension-table-header';
import TableCell from '@tiptap/extension-table-cell';
import { visualKindFromFilename } from './visualAssets';

const supportedMarkdown = (markdown: string, serialized: string) => {
  const normalize = (value: string) => value.replace(/\r\n/g, '\n').replace(/[ \t]+$/gm, '').split('\n')
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed.startsWith('|') || !trimmed.endsWith('|')) return line;
      const cells = trimmed.slice(1, -1).split('|').map((cell) => {
        const value = cell.trim();
        return /^:?-{3,}:?$/.test(value) ? `${value.startsWith(':') ? ':' : ''}---${value.endsWith(':') ? ':' : ''}` : value;
      });
      return `|${cells.join('|')}|`;
    }).join('\n').replace(/\n{3,}/g, '\n\n').replace(/\n+$/, '');
  return normalize(markdown) === normalize(serialized);
};

export function MarkdownEditor({ value, disabled, onChange, onImagePaste, onOpenVisualAsset, assetBase = '' }: { value: string; disabled: boolean; onChange: (markdown: string) => void; onImagePaste?: (file: File) => Promise<string>; onOpenVisualAsset?: (filename: string) => void; assetBase?: string }) {
  const extensions = useMemo(() => [
    StarterKit,
    Markdown,
    Image.configure({ inline: false, allowBase64: false }),
    Table.configure({ resizable: false }), TableRow, TableHeader, TableCell,
  ], []);
  const syncing = useRef(true);
  const rejected = useRef(false);
  const lifecycle = useRef(0);
  const documentIdentity = useRef(assetBase);
  documentIdentity.current = assetBase;
  const [roundTripSafe, setRoundTripSafe] = useState(true);
  const displayMarkdown = (markdown: string) => assetBase ? markdown.replace(/\]\((attachments\/[^)]+)\)/g, `](${assetBase}/$1)`) : markdown;
  const sourceMarkdown = (markdown: string) => {
    let result = markdown;
    if (assetBase) result = result.replaceAll(`](${assetBase}/`, '](');
    result = result.replace(/\]\((\/api\/notes\/[^)]+\/attachments\/[^)]+)\)/g, (_match, url: string) => {
      const filename = url.slice(url.lastIndexOf('/') + 1);
      return `](attachments/${filename})`;
    });
    return result;
  };
  const editor = useEditor({ extensions, content: displayMarkdown(value), contentType: 'markdown', editable: !disabled,
    editorProps: { handlePaste: (_view, event) => {
      const image = Array.from(event.clipboardData?.files ?? []).find((file) => file.type.startsWith('image/'));
      if (!image || !onImagePaste) return false;
      event.preventDefault();
      const identity = assetBase;
      const generation = lifecycle.current;
      const targetEditor = editor;
      void onImagePaste(image).then((url) => {
        if (lifecycle.current !== generation || documentIdentity.current !== identity || !targetEditor || targetEditor.isDestroyed) return;
        targetEditor.commands.insertContent({ type: 'image', attrs: { src: url, alt: 'image' } });
      }).catch(() => undefined);
      return true;
    } },
    onUpdate: ({ editor: current }) => { if (!syncing.current && !rejected.current) onChange(sourceMarkdown(current.getMarkdown())); } });

  useEffect(() => {
    const generation = ++lifecycle.current;
    return () => { if (lifecycle.current === generation) lifecycle.current += 1; };
  }, [editor, assetBase]);

  useEffect(() => {
    if (!editor || !assetBase || !onOpenVisualAsset) return;
    const handleClick = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const anchor = target.closest('a');
      if (!anchor) return;
      try {
        const basePath = new URL(assetBase, window.location.origin).pathname.replace(/\/$/, '');
        const linkPath = new URL(anchor.href, window.location.origin).pathname;
        if (!linkPath.startsWith(`${basePath}/attachments/`)) return;
        const filename = decodeURIComponent(linkPath.slice(`${basePath}/attachments/`.length));
        if (!visualKindFromFilename(filename)) return;
        event.preventDefault();
        onOpenVisualAsset(filename);
      } catch { /* Leave malformed or external links to the browser. */ }
    };
    editor.view.dom.addEventListener('click', handleClick, true);
    return () => editor.view.dom.removeEventListener('click', handleClick, true);
  }, [editor, assetBase, onOpenVisualAsset]);

  useEffect(() => {
    if (!editor) return;
    syncing.current = true;
    editor.setEditable(!disabled);
    if (editor.getMarkdown() !== displayMarkdown(value)) {
      editor.commands.setContent(displayMarkdown(value), { contentType: 'markdown', emitUpdate: false });
    }
    queueMicrotask(() => {
      const source = displayMarkdown(value);
      rejected.current = !supportedMarkdown(source, editor.getMarkdown());
      setRoundTripSafe(!rejected.current);
      syncing.current = false;
    });
  }, [editor, value, assetBase, disabled]);

  if (!editor) return <p role="status">正在加载编辑器…</p>;
  if (!roundTripSafe) return <><div className="notes-safety" role="status">此 Markdown 无法通过当前编辑器安全往返，已停止编辑；请保留并使用原始 Markdown。</div><pre className="notes-raw-source">{value}</pre></>;
  const button = (label: string, run: () => void, pressed = false) => <button type="button" key={label} aria-pressed={pressed} disabled={disabled} onClick={run}>{label}</button>;
  return <div className="notes-editor">
    <div className="notes-toolbar" role="toolbar" aria-label="Markdown 格式工具">
      {button('加粗', () => editor.chain().focus().toggleBold().run(), editor.isActive('bold'))}
      {button('标题', () => editor.chain().focus().toggleHeading({ level: 2 }).run(), editor.isActive('heading'))}
      {button('列表', () => editor.chain().focus().toggleBulletList().run(), editor.isActive('bulletList'))}
      {button('引用', () => editor.chain().focus().toggleBlockquote().run(), editor.isActive('blockquote'))}
      {button('代码', () => editor.chain().focus().toggleCodeBlock().run(), editor.isActive('codeBlock'))}
      {button('链接', () => { const href = window.prompt('输入链接地址'); if (href && /^https?:\/\//i.test(href)) editor.chain().focus().extendMarkRange('link').setLink({ href }).run(); })}
      {button('表格', () => editor.chain().focus().insertTable({ rows: 2, cols: 2, withHeaderRow: true }).run())}
    </div>
    <EditorContent editor={editor} className="notes-prose" />
  </div>;
}
