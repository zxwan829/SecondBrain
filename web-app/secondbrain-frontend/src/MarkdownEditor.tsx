import React, { useEffect, useMemo, useRef } from 'react';
import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from '@tiptap/markdown';
import Image from '@tiptap/extension-image';
import { Table } from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableHeader from '@tiptap/extension-table-header';
import TableCell from '@tiptap/extension-table-cell';

export function MarkdownEditor({ value, disabled, onChange, onImagePaste, assetBase = '' }: { value: string; disabled: boolean; onChange: (markdown: string) => void; onImagePaste?: (file: File) => Promise<string>; assetBase?: string }) {
  const extensions = useMemo(() => [
    StarterKit,
    Markdown,
    Image.configure({ inline: false, allowBase64: false }),
    Table.configure({ resizable: false }), TableRow, TableHeader, TableCell,
  ], []);
  const syncing = useRef(true);
  const displayMarkdown = (markdown: string) => assetBase ? markdown.replace(/\]\((attachments\/[^)]+)\)/g, `](${assetBase}/$1)`) : markdown;
  const sourceMarkdown = (markdown: string) => assetBase ? markdown.replaceAll(`](${assetBase}/`, '](') : markdown;
  const editor = useEditor({ extensions, content: displayMarkdown(value), contentType: 'markdown', editable: !disabled,
    editorProps: { handlePaste: (_view, event) => {
      const image = Array.from(event.clipboardData?.files ?? []).find((file) => file.type.startsWith('image/'));
      if (!image || !onImagePaste) return false;
      event.preventDefault();
      void onImagePaste(image).then((path) => editor?.commands.insertContent(`![image](${path})`)).catch(() => undefined);
      return true;
    } },
    onUpdate: ({ editor: current }) => { if (!syncing.current) onChange(sourceMarkdown(current.getMarkdown())); } });

  useEffect(() => {
    if (!editor) return;
    syncing.current = true;
    editor.setEditable(!disabled);
    if (editor.getMarkdown() !== displayMarkdown(value)) {
      editor.commands.setContent(displayMarkdown(value), { contentType: 'markdown', emitUpdate: false });
    }
    queueMicrotask(() => { syncing.current = false; });
  }, [editor, value, assetBase, disabled]);

  if (!editor) return <p role="status">正在加载编辑器…</p>;
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
