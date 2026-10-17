import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./MarkdownEditor', () => ({
  MarkdownEditor: ({ value, onChange, disabled }: { value: string; onChange: (value: string) => void; disabled: boolean }) =>
    <textarea aria-label="合成 Markdown 编辑器" value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} />,
}));

import { NotesPage } from './NotesPage';

describe('NotesPage', () => {
  afterEach(() => vi.restoreAllMocks());

  it('keeps unsaved Markdown in the editor when the autosave request fails', async () => {
    const note = { collection: 'drafts', path: '00000000-0000-4000-8000-000000000001', content: '# Initial\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/notes' && !init?.method) return new Response(JSON.stringify({ collections: [{ id: 'drafts', kind: 'drafts' }] }), { status: 200 });
      if (url === '/api/notes/drafts') return new Response(JSON.stringify({ items: [] }), { status: 200 });
      if (url === '/api/notes' && init?.method === 'POST') return new Response(JSON.stringify(note), { status: 200 });
      if (init?.method === 'PUT') return new Response(JSON.stringify({ detail: 'synthetic failure' }), { status: 500 });
      throw new Error(`Unexpected request ${url}`);
    });

    render(<NotesPage />);
    await screen.findByRole('heading', { name: '笔记' });
    fireEvent.click(screen.getByRole('button', { name: '新建 Draft' }));
    const editor = await screen.findByLabelText('合成 Markdown 编辑器') as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: '# Still here\n\nUnsaved content.' } });
    await screen.findByText('未保存');
    await screen.findByText('保存失败', {}, { timeout: 3000 });
    expect(editor.value).toContain('Unsaved content.');
  });
});
