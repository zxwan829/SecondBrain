import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./MarkdownEditor', () => ({
  MarkdownEditor: ({ value, onChange, disabled, onOpenVisualAsset }: { value: string; onChange: (value: string) => void; disabled: boolean; onOpenVisualAsset?: (filename: string) => void }) => <>
    <textarea aria-label="合成 Markdown 编辑器" value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} />
    {value.match(/[0-9a-f]{32}\.(?:mindmap|excalidraw)\.json/)?.[0] && <button onClick={() => onOpenVisualAsset?.(value.match(/[0-9a-f]{32}\.(?:mindmap|excalidraw)\.json/)![0])}>打开图形附件</button>}
  </>,
}));
vi.mock('./VisualAssetDialog', () => ({
  VisualAssetDialog: ({ asset, onSave, onClose }: { asset: { content: string }; onSave: (content: string) => Promise<void>; onClose: () => void }) => <section role="dialog" aria-label="合成图形编辑器">
    <textarea aria-label="合成图形源" defaultValue={asset.content} />
    <button onClick={() => onSave((document.querySelector('[aria-label="合成图形源"]') as HTMLTextAreaElement).value)}>保存合成图形</button>
    <button onClick={onClose}>关闭合成图形</button>
  </section>,
}));

import { NotesPage } from './NotesPage';

describe('NotesPage', () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); });

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
  it('serializes overlapping autosaves with the newest confirmed ETag', async () => {
    const note = { collection: 'drafts', path: '00000000-0000-4000-8000-000000000001', content: '# Initial\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
    const pending: ((response: Response) => void)[] = [];
    const putHeaders: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/notes' && !init?.method) return new Response(JSON.stringify({ collections: [{ id: 'drafts', kind: 'drafts' }] }), { status: 200 });
      if (url === '/api/notes/drafts') return new Response(JSON.stringify({ items: [] }), { status: 200 });
      if (url === '/api/notes' && init?.method === 'POST') return new Response(JSON.stringify(note), { status: 200 });
      if (init?.method === 'PUT') {
        putHeaders.push(new Headers(init.headers).get('If-Match') || '');
        return new Promise<Response>((resolve) => pending.push(resolve));
      }
      throw new Error(`Unexpected request ${url}`);
    });
    render(<NotesPage />);
    fireEvent.click(await screen.findByRole('button', { name: '新建 Draft' }));
    const editor = await screen.findByLabelText('合成 Markdown 编辑器') as HTMLTextAreaElement;
    vi.useFakeTimers();
    fireEvent.change(editor, { target: { value: '# First edit\n' } });
    await act(async () => { await vi.advanceTimersByTimeAsync(900); });
    expect(pending).toHaveLength(1);
    fireEvent.change(editor, { target: { value: '# Second edit\n' } });
    await act(async () => { await vi.advanceTimersByTimeAsync(900); });
    expect(pending).toHaveLength(1);
    await act(async () => { pending[0](new Response(JSON.stringify({ ...note, content: '# First edit\n', etag: 'b'.repeat(64) }), { status: 200 })); for (let i = 0; i < 10; i += 1) await Promise.resolve(); });
    expect(pending).toHaveLength(2);
    expect(putHeaders).toEqual([`"${'a'.repeat(64)}"`, `"${'b'.repeat(64)}"`]);
    await act(async () => { pending[1](new Response(JSON.stringify({ ...note, content: '# Second edit\n', etag: 'c'.repeat(64) }), { status: 200 })); for (let i = 0; i < 10; i += 1) await Promise.resolve(); });
    expect(editor.value).toBe('# Second edit\n');
    vi.useRealTimers();
  });

  it('waits for in-flight and queued saves before allowing a note switch', async () => {
    const note = { collection: 'drafts', path: '00000000-0000-4000-8000-000000000001', content: '# Initial\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
    const pending: ((response: Response) => void)[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/notes' && !init?.method) return new Response(JSON.stringify({ collections: [{ id: 'drafts', kind: 'drafts' }, { id: 'personal', kind: 'authorized' }] }), { status: 200 });
      if (url === '/api/notes/drafts' || url === '/api/notes/personal') return new Response(JSON.stringify({ items: [] }), { status: 200 });
      if (url === '/api/notes' && init?.method === 'POST') return new Response(JSON.stringify(note), { status: 200 });
      if (init?.method === 'PUT') return new Promise<Response>((resolve) => pending.push(resolve));
      throw new Error(`Unexpected request ${url}`);
    });
    const { unmount } = render(<NotesPage />);
    fireEvent.click(await screen.findByRole('button', { name: '新建 Draft' }));
    const editor = await screen.findByLabelText('合成 Markdown 编辑器') as HTMLTextAreaElement;
    vi.useFakeTimers();
    fireEvent.change(editor, { target: { value: '# First edit\n' } });
    await act(async () => { await vi.advanceTimersByTimeAsync(900); });
    expect(pending).toHaveLength(1);
    fireEvent.change(editor, { target: { value: '# Queued edit\n' } });
    await act(async () => { await vi.advanceTimersByTimeAsync(900); });
    expect(pending).toHaveLength(1);

    fireEvent.change(document.getElementById('notes-collection')!, { target: { value: 'personal' } });
    expect(screen.getByText('当前笔记正在保存，请等待保存完成后再切换。')).toBeTruthy();
    expect(document.getElementById('notes-collection')).toHaveProperty('value', 'drafts');
    expect(pending).toHaveLength(1);

    // If the page is discarded while the first request is in flight, the
    // queued write must fail its pre-dispatch revision check.
    unmount();
    await act(async () => { pending[0](new Response(JSON.stringify({ ...note, content: '# First edit\n', etag: 'b'.repeat(64) }), { status: 200 })); for (let i = 0; i < 10; i += 1) await Promise.resolve(); });
    expect(pending).toHaveLength(1);
    vi.useRealTimers();
  });

  it('asks before switching away from unsaved content', async () => {
    const note = { collection: 'drafts', path: '00000000-0000-4000-8000-000000000001', content: '# Initial\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/notes' && !init?.method) return new Response(JSON.stringify({ collections: [{ id: 'drafts', kind: 'drafts' }, { id: 'personal', kind: 'authorized' }] }), { status: 200 });
      if (url === '/api/notes/drafts' || url === '/api/notes/personal') return new Response(JSON.stringify({ items: [] }), { status: 200 });
      if (url === '/api/notes' && init?.method === 'POST') return new Response(JSON.stringify(note), { status: 200 });
      throw new Error(`Unexpected request ${url}`);
    });
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<NotesPage />);
    fireEvent.click(await screen.findByRole('button', { name: '新建 Draft' }));
    const editor = await screen.findByLabelText('合成 Markdown 编辑器') as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: '# Unsaved\n' } });
    fireEvent.change(document.getElementById('notes-collection')!, { target: { value: 'personal' } });
    expect(confirm).toHaveBeenCalled();
    expect(editor.value).toBe('# Unsaved\n');
  });

  it('previews history before changing the current Markdown', async () => {
    const note = { collection: 'drafts', path: '00000000-0000-4000-8000-000000000001', content: '# Current\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/notes' && !init?.method) return new Response(JSON.stringify({ collections: [{ id: 'drafts', kind: 'drafts' }] }), { status: 200 });
      if (url === '/api/notes/drafts') return new Response(JSON.stringify({ items: [] }), { status: 200 });
      if (url === '/api/notes' && init?.method === 'POST') return new Response(JSON.stringify(note), { status: 200 });
      if (url.endsWith('/history')) return new Response(JSON.stringify({ versions: [{ etag: 'b'.repeat(64), content: '# Previous\n' }] }), { status: 200 });
      throw new Error(`Unexpected request ${url}`);
    });
    render(<NotesPage />);
    fireEvent.click(await screen.findByRole('button', { name: '新建 Draft' }));
    const editor = await screen.findByLabelText('合成 Markdown 编辑器') as HTMLTextAreaElement;
    fireEvent.click(screen.getByRole('button', { name: '查看可恢复版本' }));
    await screen.findByRole('region', { name: '历史版本预览' });
    expect(editor.value).toBe('# Current\n');
    fireEvent.click(screen.getByRole('button', { name: '使用此版本' }));
    expect(editor.value).toBe('# Previous\n');
  });

  it.each([
    { kind: 'mindmap' as const, button: '插入思维导图', filename: '11111111111111111111111111111111.mindmap.json' },
    { kind: 'excalidraw' as const, button: '插入自由画板', filename: '22222222222222222222222222222222.excalidraw.json' },
  ])('creates, saves, closes, reopens and saves a $kind source again', async ({ kind, button, filename }) => {
    const note = { collection: 'drafts', path: '00000000-0000-4000-8000-000000000001', content: '# Initial\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
    let visual = '';
    let assetVersion = 1;
    const savedNote = { ...note, etag: 'b'.repeat(64) };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/notes' && !init?.method) return new Response(JSON.stringify({ collections: [{ id: 'drafts', kind: 'drafts' }] }), { status: 200 });
      if (url === '/api/notes/drafts') return new Response(JSON.stringify({ items: [] }), { status: 200 });
      if (url === '/api/notes' && init?.method === 'POST') return new Response(JSON.stringify(note), { status: 200 });
      if (url.endsWith(`/visual-assets/${kind}`) && init?.method === 'POST') {
        visual = JSON.parse(String(init.body)).content;
        return new Response(JSON.stringify({ filename, etag: 'v1' }), { status: 200 });
      }
      if (url.endsWith(`/attachments/${filename}`) && !init?.method) return new Response(visual, { status: 200, headers: { ETag: `"v${assetVersion}"` } });
      if (url.endsWith(`/attachments/${filename}`) && init?.method === 'PUT') {
        visual = JSON.parse(String(init.body)).content; assetVersion += 1;
        return new Response(JSON.stringify({ etag: `v${assetVersion}` }), { status: 200 });
      }
      if (init?.method === 'PUT') return new Response(JSON.stringify(savedNote), { status: 200 });
      throw new Error(`Unexpected request ${url}`);
    });

    render(<NotesPage />);
    fireEvent.click(await screen.findByRole('button', { name: '新建 Draft' }));
    fireEvent.click(await screen.findByRole('button', { name: button }));
    await screen.findByRole('dialog', { name: '合成图形编辑器' });
    expect(await screen.findByRole('button', { name: '打开图形附件' })).toBeTruthy();
    const editor = screen.getByLabelText('合成图形源') as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: '{"data":{"text":"first edit"},"children":[]}' } });
    fireEvent.click(screen.getByRole('button', { name: '保存合成图形' }));
    await waitFor(() => expect(visual).toContain('first edit'));
    fireEvent.click(screen.getByRole('button', { name: '关闭合成图形' }));
    fireEvent.click(screen.getByRole('button', { name: '打开图形附件' }));
    const reopened = await screen.findByLabelText('合成图形源') as HTMLTextAreaElement;
    expect(reopened.value).toContain('first edit');
    fireEvent.change(reopened, { target: { value: '{"data":{"text":"second edit"},"children":[]}' } });
    fireEvent.click(screen.getByRole('button', { name: '保存合成图形' }));
    await waitFor(() => expect(visual).toContain('second edit'));
    expect(assetVersion).toBe(3);
  });

});
