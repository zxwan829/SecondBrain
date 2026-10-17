import React, { useState } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MarkdownEditor } from './MarkdownEditor';
import { notesApi, type Note } from './api/notes';

const imageNote: Note = { collection: 'drafts', path: '00000000-0000-4000-8000-000000000001', content: '# Images\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
function ImageRoundTripHarness({ onSaved }: { onSaved: (note: Note) => void }) {
  const [markdown, setMarkdown] = useState(imageNote.content);
  const base = `/api/notes/${imageNote.collection}/${imageNote.path}`;
  const onChange = (value: string) => {
    setMarkdown(value);
    void notesApi.save(imageNote, value).then((saved) => { onSaved(saved); setMarkdown(saved.content); });
  };
  const onImagePaste = async (file: File) => (await notesApi.upload(imageNote, file)).url;
  return <MarkdownEditor value={markdown} disabled={false} onChange={onChange} onImagePaste={onImagePaste} assetBase={base} />;
}

describe('MarkdownEditor', () => {
  it('opens ordinary Markdown structure without dropping its main blocks', async () => {
    const onChange = vi.fn();
    const { container } = render(<MarkdownEditor value={'# Heading\n\n**bold text**\n\n- first\n- second\n\n> quote\n\n[link](https://example.com)\n\nline one  \nline two\n\n`inline code`\n\n```js\nconst n = 1;\n```\n\n\\*escaped literal\\*\n\n![image](attachments/sample.png)\n\n| Name | Value |\n| --- | --- |\n| one | 1 |\n'} disabled={false} onChange={onChange} />);
    await screen.findByRole('heading', { level: 1, name: 'Heading' });
    expect(screen.getByText('bold text').tagName).toBe('STRONG');
    expect(screen.getByRole('list').textContent).toContain('first');
    expect(container.querySelector('blockquote')?.textContent).toContain('quote');
    expect(container.querySelector('a[href="https://example.com"]')?.textContent).toBe('link');
    expect(container.querySelector('table')?.textContent).toContain('Name');
    expect(container.querySelector('br')).toBeTruthy();
    expect(container.querySelector('code')?.textContent).toContain('inline code');
    expect(container.querySelector('img')?.getAttribute('src')).toBe('attachments/sample.png');
    expect(screen.getByText('*escaped literal*')).toBeTruthy();
    await waitFor(() => expect(onChange).not.toHaveBeenCalled());
  });
  it('uploads, inserts, saves, and reopens an image as a relative Markdown attachment', async () => {
    let saved: Note = imageNote;
    const onSaved = vi.fn((note: Note) => { saved = note; });
    const uploadUrl = `/api/notes/${imageNote.collection}/${imageNote.path}/attachments/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png`;
    let putBody = '';
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
      if (init?.method === 'POST') return new Response(JSON.stringify({ path: 'attachments/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png', url: uploadUrl }), { status: 200 });
      if (init?.method === 'PUT') {
        putBody = String(init.body);
        const body = JSON.parse(putBody) as { content: string };
        saved = { ...imageNote, content: body.content, etag: 'b'.repeat(64) };
        return new Response(JSON.stringify(saved), { status: 200 });
      }
      throw new Error(`Unexpected request ${String(_input)}`);
    });
    const { container, unmount } = render(<ImageRoundTripHarness onSaved={onSaved} />);
    await waitFor(() => expect(container.querySelector('.tiptap')).toBeTruthy());
    const editor = container.querySelector('.tiptap') as HTMLElement;
    const image = new File(['synthetic'], 'synthetic.png', { type: 'image/png' });
    fireEvent.paste(editor, { clipboardData: { files: [image], getData: () => '' } });
    await waitFor(() => expect(container.querySelector('img')?.getAttribute('src')).toBe(uploadUrl));
    await waitFor(() => expect(putBody).toContain('attachments/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png'));
    expect(putBody).not.toContain(uploadUrl);
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    unmount();
    const reopened = render(<MarkdownEditor value={saved.content} disabled={false} onChange={vi.fn()} assetBase={`/api/notes/${saved.collection}/${saved.path}`} />);
    await waitFor(() => expect(reopened.container.querySelector('img')?.getAttribute('src')).toBe(uploadUrl));
  });

  it('preserves Markdown as read-only when a reference link cannot round-trip', async () => {
    const source = '[reference][target]\n\n[target]: https://example.com\n';
    const { container } = render(<MarkdownEditor value={source} disabled={false} onChange={vi.fn()} />);
    await screen.findByText('此 Markdown 无法通过当前编辑器安全往返，已停止编辑；请保留并使用原始 Markdown。');
    expect(container.querySelector('.notes-raw-source')?.textContent).toBe(source);
    expect(container.querySelector('.tiptap')).toBeNull();
  });

});
