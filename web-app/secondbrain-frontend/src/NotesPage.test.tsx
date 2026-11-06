import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./BlockSuiteMarkdownEditor', () => ({
  BlockSuiteMarkdownEditor: ({ value, onChange, disabled, onOpenVisualAsset }: { value: string; onChange: (value: string) => void; disabled: boolean; onOpenVisualAsset?: (filename: string) => void }) => <>
    <textarea aria-label="合成 Markdown 编辑器" value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} />
    {value.match(/[0-9a-f]{32}\.(?:mindmap|excalidraw)\.json/)?.[0] && <button onClick={() => onOpenVisualAsset?.(value.match(/[0-9a-f]{32}\.(?:mindmap|excalidraw)\.json/)![0])}>打开图形附件</button>}
  </>,
}));
vi.mock('./VisualAssetDialog', () => ({
  VisualAssetDialog: ({ asset, onSave, onClose }: { asset: { content: string }; onSave: (content: string) => Promise<void>; onClose: () => void }) => {
    const [saving, setSaving] = React.useState(false);
    const [value, setValue] = React.useState(asset.content);
    const save = async () => { setSaving(true); try { await onSave(value); } finally { setSaving(false); } };
    return <section role="dialog" aria-label="合成图形编辑器">
      <textarea aria-label="合成图形源" value={value} onChange={(event) => setValue(event.target.value)} />
      <button disabled={saving} onClick={() => void save()}>保存合成图形</button>
      <button disabled={saving} onClick={onClose}>关闭合成图形</button>
    </section>;
  },
}));
vi.mock('./BlockSuiteResourceEditor', () => ({
  createBlockSuiteResourcePayload: (resourceKind: string) => ({ schemaVersion: 1, resourceKind,
    docId: '00000000-0000-4000-8000-000000000002', updateB64: 'AQ==', snapshot: { schemaVersion: 1 } }),
  BlockSuiteResourceEditor: () => <div role="dialog" aria-label="合成 BlockSuite 资源编辑器" />,
}));

import { NotesPage } from './NotesPage';

describe('NotesPage', () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); });

  it('opens frontmatter notes in BlockSuite while preserving the complete Markdown source', async () => {
    const note = { collection: 'drafts', path: '中文笔记.md', content: '---\ntags: [合成]\ncustom: 保留\n---\n\n# 正文\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url === '/api/notes') return new Response(JSON.stringify({ collections: [{ id: 'drafts', kind: 'drafts' }] }), { status: 200 });
      if (url === '/api/notes/drafts') return new Response(JSON.stringify({ items: [{ path: note.path, title: '中文笔记' }] }), { status: 200 });
      if (url === `/api/notes/drafts/${encodeURIComponent(note.path)}`) return new Response(JSON.stringify(note), { status: 200 });
      throw new Error(`Unexpected request ${url}`);
    });
    render(<NotesPage />);
    fireEvent.click(await screen.findByRole('button', { name: '中文笔记' }));
    const editor = await screen.findByLabelText('合成 Markdown 编辑器') as HTMLTextAreaElement;
    expect(editor.value).toBe(note.content);
    expect(screen.queryByRole('button', { name: '切回旧版编辑器' })).toBeNull();
  });

  it('opens supported notes directly in BlockSuite by default', async () => {
    const note = { collection: 'drafts', path: '00000000-0000-4000-8000-000000000002', content: '# Direct BlockSuite\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url === '/api/notes') return new Response(JSON.stringify({ collections: [{ id: 'drafts', kind: 'drafts' }] }), { status: 200 });
      if (url === '/api/notes/drafts') return new Response(JSON.stringify({ items: [{ path: note.path, title: 'Direct BlockSuite' }] }), { status: 200 });
      if (url === `/api/notes/drafts/${note.path}`) return new Response(JSON.stringify(note), { status: 200 });
      throw new Error(`Unexpected request ${url}`);
    });
    render(<NotesPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Direct BlockSuite' }));
    expect(await screen.findByLabelText('合成 Markdown 编辑器')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '切回旧版编辑器' })).toBeNull();
  });

  it('opens single-source Inbox for the selected Draft only after the unsaved-navigation guard passes', async () => {
    const note = { collection: 'drafts', path: '00000000-0000-4000-8000-000000000001', content: '# Selected Draft\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url === '/api/notes') return new Response(JSON.stringify({ collections: [{ id: 'drafts', kind: 'drafts' }] }), { status: 200 });
      if (url === '/api/notes/drafts') return new Response(JSON.stringify({ items: [{ path: note.path, title: 'Selected Draft' }] }), { status: 200 });
      if (url === `/api/notes/drafts/${note.path}`) return new Response(JSON.stringify(note), { status: 200 });
      throw new Error(`Unexpected request ${url}`);
    });
    const onOpenInboxSource = vi.fn();
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<NotesPage onOpenInboxSource={onOpenInboxSource} onRegisterNavigationGuard={(value) => { if (value) expect(value).toBeDefined(); }} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Selected Draft' }));
    fireEvent.change(await screen.findByLabelText('合成 Markdown 编辑器'), { target: { value: '# Unsaved Draft\n' } });
    const openInbox = await screen.findByRole('button', { name: '单来源 Inbox 审批' });
    fireEvent.click(openInbox);
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(onOpenInboxSource).not.toHaveBeenCalled();
    confirm.mockReturnValue(true);
    fireEvent.click(openInbox);
    expect(onOpenInboxSource).toHaveBeenCalledWith('drafts', note.path);
  });

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

  it('keeps unsaved Markdown and reports a version conflict when autosave returns 412', async () => {
    const note = { collection: 'drafts', path: '00000000-0000-4000-8000-000000000001', content: '# Initial\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/notes' && !init?.method) return new Response(JSON.stringify({ collections: [{ id: 'drafts', kind: 'drafts' }] }), { status: 200 });
      if (url === '/api/notes/drafts') return new Response(JSON.stringify({ items: [] }), { status: 200 });
      if (url === '/api/notes' && init?.method === 'POST') return new Response(JSON.stringify(note), { status: 200 });
      if (init?.method === 'PUT') return new Response(JSON.stringify({ detail: 'revision changed' }), { status: 412 });
      throw new Error(`Unexpected request ${url}`);
    });

    render(<NotesPage />);
    fireEvent.click(await screen.findByRole('button', { name: '新建 Draft' }));
    const editor = await screen.findByLabelText('合成 Markdown 编辑器') as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: '# Keep this edit\n\nConflict content.' } });
    expect(await screen.findByText('版本冲突', {}, { timeout: 3000 })).toBeTruthy();
    expect(screen.getByText('文件已在其他位置修改。当前输入仍保留；请复制未保存内容后重新载入再合并。')).toBeTruthy();
    expect(editor.value).toContain('Conflict content.');
  });

  it.each([false, true])('keeps a 412 conflict and blocks pending autosaves (already queued: %s)', async (queueSecondSave) => {
    const note = { collection: 'drafts', path: '00000000-0000-4000-8000-000000000001', content: '# Initial\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
    let resolvePut: ((response: Response) => void) | undefined;
    let putCount = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/notes' && !init?.method) return new Response(JSON.stringify({ collections: [{ id: 'drafts', kind: 'drafts' }] }), { status: 200 });
      if (url === '/api/notes/drafts') return new Response(JSON.stringify({ items: [] }), { status: 200 });
      if (url === '/api/notes' && init?.method === 'POST') return new Response(JSON.stringify(note), { status: 200 });
      if (init?.method === 'PUT') {
        putCount += 1;
        return putCount === 1
          ? new Promise<Response>((resolve) => { resolvePut = resolve; })
          : new Response(JSON.stringify({ detail: 'revision changed' }), { status: 412 });
      }
      throw new Error(`Unexpected request ${url}`);
    });

    render(<NotesPage />);
    fireEvent.click(await screen.findByRole('button', { name: '新建 Draft' }));
    const editor = await screen.findByLabelText('合成 Markdown 编辑器') as HTMLTextAreaElement;
    vi.useFakeTimers();
    fireEvent.change(editor, { target: { value: '# First projection\n' } });
    await act(async () => { await vi.advanceTimersByTimeAsync(900); });
    expect(resolvePut).toBeTypeOf('function');

    fireEvent.change(editor, { target: { value: '# Latest editor content\n' } });
    if (queueSecondSave) await act(async () => { await vi.advanceTimersByTimeAsync(900); });
    await act(async () => {
      resolvePut!(new Response(JSON.stringify({ detail: 'revision changed' }), { status: 412 }));
      for (let i = 0; i < 10; i += 1) await Promise.resolve();
    });
    if (!queueSecondSave) await act(async () => { await vi.advanceTimersByTimeAsync(900); });

    expect(screen.getByText('版本冲突')).toBeTruthy();
    expect(screen.getByText('文件已在其他位置修改。当前输入仍保留；请复制未保存内容后重新载入再合并。')).toBeTruthy();
    expect(editor.value).toBe('# Latest editor content\n');
    expect(putCount).toBe(1);
    vi.useRealTimers();
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

  it('treats an empty history response as a normal state', async () => {
    const note = { collection: 'drafts', path: '00000000-0000-4000-8000-000000000001', content: '# Current\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/notes' && !init?.method) return new Response(JSON.stringify({ collections: [{ id: 'drafts', kind: 'drafts' }] }), { status: 200 });
      if (url === '/api/notes/drafts') return new Response(JSON.stringify({ items: [] }), { status: 200 });
      if (url === '/api/notes' && init?.method === 'POST') return new Response(JSON.stringify(note), { status: 200 });
      if (url.endsWith('/history')) return new Response(JSON.stringify({ versions: [] }), { status: 200 });
      throw new Error(`Unexpected request ${url}`);
    });
    render(<NotesPage />);
    fireEvent.click(await screen.findByRole('button', { name: '新建 Draft' }));
    const editor = await screen.findByLabelText('合成 Markdown 编辑器') as HTMLTextAreaElement;
    fireEvent.click(screen.getByRole('button', { name: '查看可恢复版本' }));
    expect(await screen.findByText('暂无可恢复版本。')).toBeTruthy();
    expect(screen.queryByRole('region', { name: '历史版本预览' })).toBeNull();
    expect(editor.value).toBe('# Current\n');
  });

  it.each([
    [401, '登录状态已失效，请重新登录后重试。'],
    [403, '当前会话没有读取此笔记历史的权限。'],
    [404, '笔记或历史目标已不存在，请刷新笔记后重试。'],
    [503, '历史服务暂时不可用，请稍后重试。'],
  ])('reports history HTTP %i distinctly without changing the current note', async (status, expected) => {
    const note = { collection: 'drafts', path: '00000000-0000-4000-8000-000000000001', content: '# Current\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/notes' && !init?.method) return new Response(JSON.stringify({ collections: [{ id: 'drafts', kind: 'drafts' }] }), { status: 200 });
      if (url === '/api/notes/drafts') return new Response(JSON.stringify({ items: [] }), { status: 200 });
      if (url === '/api/notes' && init?.method === 'POST') return new Response(JSON.stringify(note), { status: 200 });
      if (url.endsWith('/history')) return new Response(JSON.stringify({ detail: 'synthetic history failure' }), { status });
      throw new Error(`Unexpected request ${url}`);
    });
    render(<NotesPage />);
    fireEvent.click(await screen.findByRole('button', { name: '新建 Draft' }));
    const editor = await screen.findByLabelText('合成 Markdown 编辑器') as HTMLTextAreaElement;
    fireEvent.click(screen.getByRole('button', { name: '查看可恢复版本' }));
    expect(await screen.findByText(expected as string)).toBeTruthy();
    expect(screen.queryByRole('region', { name: '历史版本预览' })).toBeNull();
    expect(editor.value).toBe('# Current\n');
  });

  it.each([false, true])('applies a delayed history failure only while its note view is current (switch=%s)', async (switchAway) => {
    const noteA = { collection: 'drafts', path: '00000000-0000-4000-8000-000000000001', content: '# Note A\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
    const noteB = { collection: 'drafts', path: '00000000-0000-4000-8000-000000000002', content: '# Note B\n', etag: 'b'.repeat(64), read_only: false, safety_reasons: [] };
    let failHistory!: (response: Response) => void;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url === '/api/notes') return new Response(JSON.stringify({ collections: [{ id: 'drafts', kind: 'drafts' }] }), { status: 200 });
      if (url === '/api/notes/drafts') return new Response(JSON.stringify({ items: [{ path: noteA.path, title: 'Note A' }, { path: noteB.path, title: 'Note B' }] }), { status: 200 });
      if (url === `/api/notes/drafts/${noteA.path}`) return new Response(JSON.stringify(noteA), { status: 200 });
      if (url === `/api/notes/drafts/${noteB.path}`) return new Response(JSON.stringify(noteB), { status: 200 });
      if (url === `/api/notes/drafts/${noteA.path}/history`) return new Promise<Response>((resolve) => { failHistory = resolve; });
      throw new Error(`Unexpected request ${url}`);
    });

    render(<NotesPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Note A' }));
    const editor = await screen.findByLabelText('合成 Markdown 编辑器') as HTMLTextAreaElement;
    await waitFor(() => expect(editor.value).toBe('# Note A\n'));
    fireEvent.click(screen.getByRole('button', { name: '查看可恢复版本' }));
    await waitFor(() => expect(failHistory).toBeTypeOf('function'));

    if (switchAway) {
      fireEvent.click(screen.getByRole('button', { name: 'Note B' }));
      await waitFor(() => expect(screen.getByText('drafts / ' + noteB.path)).toBeTruthy());
      const switchedEditor = await screen.findByLabelText('合成 Markdown 编辑器') as HTMLTextAreaElement;
      await waitFor(() => expect(switchedEditor.value).toBe('# Note B\n'));
    }
    await act(async () => { failHistory(new Response(JSON.stringify({ detail: 'synthetic unavailable' }), { status: 503 })); });

    if (switchAway) {
      await waitFor(() => expect(screen.queryByText('历史服务暂时不可用，请稍后重试。')).toBeNull());
      expect((screen.getByLabelText('合成 Markdown 编辑器') as HTMLTextAreaElement).value).toBe('# Note B\n');
      expect(screen.queryByRole('region', { name: '历史版本预览' })).toBeNull();
    } else {
      expect(await screen.findByText('历史服务暂时不可用，请稍后重试。')).toBeTruthy();
      expect(editor.value).toBe('# Note A\n');
    }
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

  it('blocks note switching until a graph attachment save settles', async () => {
    const note = { collection: 'drafts', path: '00000000-0000-4000-8000-000000000001', content: '# Initial\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
    let resolveVisual!: (response: Response) => void;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/notes' && !init?.method) return new Response(JSON.stringify({ collections: [{ id: 'drafts', kind: 'drafts' }, { id: 'personal', kind: 'authorized' }] }), { status: 200 });
      if (url === '/api/notes/drafts' || url === '/api/notes/personal') return new Response(JSON.stringify({ items: [] }), { status: 200 });
      if (url === '/api/notes' && init?.method === 'POST') return new Response(JSON.stringify(note), { status: 200 });
      if (url.endsWith('/visual-assets/mindmap') && init?.method === 'POST') return new Response(JSON.stringify({ filename: '11111111111111111111111111111111.mindmap.json', etag: 'v1' }), { status: 200 });
      if (url.endsWith('/attachments/11111111111111111111111111111111.mindmap.json') && init?.method === 'PUT') return new Promise<Response>((resolve) => { resolveVisual = resolve; });
      if (init?.method === 'PUT') return new Response(JSON.stringify({ ...note, content: JSON.parse(String(init.body)).content, etag: 'b'.repeat(64) }), { status: 200 });
      throw new Error(`Unexpected request ${url}`);
    });
    render(<NotesPage />);
    fireEvent.click(await screen.findByRole('button', { name: '新建 Draft' }));
    fireEvent.click(await screen.findByRole('button', { name: '插入思维导图' }));
    const source = await screen.findByLabelText('合成图形源') as HTMLTextAreaElement;
    fireEvent.change(source, { target: { value: '{"data":{"text":"pending graph"},"children":[]}' } });
    fireEvent.click(screen.getByRole('button', { name: '保存合成图形' }));
    await waitFor(() => expect(resolveVisual).toBeTypeOf('function'));
    expect(screen.getByRole('button', { name: '关闭合成图形' })).toHaveProperty('disabled', true);
    fireEvent.change(document.getElementById('notes-collection')!, { target: { value: 'personal' } });
    expect(screen.getByText('当前笔记正在保存，请等待保存完成后再切换。')).toBeTruthy();
    expect(document.getElementById('notes-collection')).toHaveProperty('value', 'drafts');
    await act(async () => { resolveVisual(new Response(JSON.stringify({ etag: 'v2' }), { status: 200 })); });
    expect(await screen.findByText('图形已保存，可关闭后再次打开继续编辑。')).toBeTruthy();
  });

  it.each([412, 500])('keeps the inserted Markdown link visible when its reference save returns %i', async (status) => {
    const note = { collection: 'drafts', path: '00000000-0000-4000-8000-000000000001', content: '# Initial\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
    let referenceFailed = false;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/notes' && !init?.method) return new Response(JSON.stringify({ collections: [{ id: 'drafts', kind: 'drafts' }] }), { status: 200 });
      if (url === '/api/notes/drafts') return new Response(JSON.stringify({ items: [] }), { status: 200 });
      if (url === '/api/notes' && init?.method === 'POST') return new Response(JSON.stringify(note), { status: 200 });
      if (url.endsWith('/visual-assets/mindmap') && init?.method === 'POST') return new Response(JSON.stringify({ filename: '11111111111111111111111111111111.mindmap.json', etag: 'v1' }), { status: 200 });
      if (init?.method === 'PUT' && !referenceFailed) { referenceFailed = true; return new Response(JSON.stringify({ detail: 'synthetic reference failure' }), { status }); }
      if (init?.method === 'PUT') return new Response(JSON.stringify({ ...note, content: JSON.parse(String(init.body)).content, etag: 'b'.repeat(64) }), { status: 200 });
      throw new Error(`Unexpected request ${url}`);
    });
    render(<NotesPage />);
    fireEvent.click(await screen.findByRole('button', { name: '新建 Draft' }));
    fireEvent.click(await screen.findByRole('button', { name: '插入思维导图' }));
    const editor = await screen.findByLabelText('合成 Markdown 编辑器') as HTMLTextAreaElement;
    await screen.findByText(/图形源文件已创建，但 Markdown 引用未确认保存；正文保留在编辑区。/);
    expect(editor.value).toContain('attachments/11111111111111111111111111111111.mindmap.json');
    expect(screen.queryByRole('dialog', { name: '合成图形编辑器' })).toBeNull();
    if (status === 500) {
      fireEvent.click(screen.getByRole('button', { name: '重试保存图形引用' }));
      await screen.findByRole('dialog', { name: '合成图形编辑器' });
    } else {
      expect(screen.getByText('版本冲突')).toBeTruthy();
      expect(screen.queryByRole('button', { name: '重试保存图形引用' })).toBeNull();
    }
  });

  it('explicitly rebases a newly created BlockSuite reference after a Markdown 412', async () => {
    const path = '00000000-0000-4000-8000-000000000001';
    const initial = { collection: 'drafts', path, content: '# Initial\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
    const latest = { ...initial, content: '# Initial\n\nRemote concurrent edit.\n', etag: 'c'.repeat(64) };
    const resourceId = '11111111111111111111111111111111';
    let putCount = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/notes' && !init?.method) return new Response(JSON.stringify({ collections: [{ id: 'drafts', kind: 'drafts' }] }), { status: 200 });
      if (url === '/api/notes/drafts') return new Response(JSON.stringify({ items: [] }), { status: 200 });
      if (url === '/api/notes' && init?.method === 'POST') return new Response(JSON.stringify(initial), { status: 200 });
      if (url === `/api/notes/drafts/${path}/blocksuite/resources` && init?.method === 'POST') {
        return new Response(JSON.stringify({ resource_id: resourceId, resource_kind: 'database',
          doc_id: '00000000-0000-4000-8000-000000000002', filename: `${resourceId}.blocksuite.json`,
          reference: `[BlockSuite resource](attachments/${resourceId}.blocksuite.json)`, etag: 'b'.repeat(64), note_etag: initial.etag, artifact_set_etag: 'e'.repeat(64) }), { status: 201 });
      }
      if (url === `/api/notes/drafts/${path}` && init?.method === 'PUT') {
        putCount += 1;
        if (putCount === 1) return new Response(JSON.stringify({ detail: 'revision changed' }), { status: 412 });
        expect(new Headers(init.headers).get('If-Match')).toBe(`"${latest.etag}"`);
        const content = JSON.parse(String(init.body)).content;
        expect(content).toContain('Remote concurrent edit.');
        expect(content).toContain(`${resourceId}.blocksuite.json`);
        return new Response(JSON.stringify({ ...latest, content, etag: 'd'.repeat(64) }), { status: 200 });
      }
      if (url === `/api/notes/drafts/${path}` && !init?.method) return new Response(JSON.stringify(latest), { status: 200 });
      if (url === `/api/notes/drafts/${path}/blocksuite/snapshots`) return new Response(JSON.stringify({ note_etag: latest.etag, artifact_set_etag: 'e'.repeat(64), snapshots: [] }), { status: 200 });
      throw new Error(`Unexpected request ${url}`);
    });

    render(<NotesPage />);
    fireEvent.click(await screen.findByRole('button', { name: '新建 Draft' }));
    fireEvent.click(await screen.findByRole('button', { name: '新建 BlockSuite Database' }));
    await screen.findByText('版本冲突');
    const retry = await screen.findByRole('button', { name: '读取最新笔记并追加 BlockSuite 资源引用' });
    fireEvent.click(retry);
    await screen.findByRole('dialog', { name: '合成 BlockSuite 资源编辑器' });
    expect(putCount).toBe(2);
  });

  it('requires confirmation before soft deletion and sends the current SHA with an idempotency key', async () => {
    const note = { collection: 'projects', path: 'synthetic.md', content: '# Synthetic\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
    const deletes: RequestInit[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/notes' && !init?.method) return new Response(JSON.stringify({ collections: [{ id: 'projects', kind: 'authorized' }] }), { status: 200 });
      if (url === '/api/notes/projects') return new Response(JSON.stringify({ items: [{ path: note.path, title: 'Synthetic' }] }), { status: 200 });
      if (url === '/api/notes/projects/synthetic.md') return new Response(JSON.stringify(note), { status: 200 });
      if (url.startsWith('/api/notes/trash/projects/synthetic.md') && init?.method === 'DELETE') {
        deletes.push(init);
        return new Response(JSON.stringify({ status: 'trashed', trash_id: 'b'.repeat(32) }), { status: 201 });
      }
      throw new Error(`Unexpected request ${url}`);
    });
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<NotesPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Synthetic' }));
    fireEvent.click(await screen.findByRole('button', { name: '移到回收站' }));
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(deletes).toHaveLength(0);
    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByRole('button', { name: '移到回收站' }));
    await screen.findByText('笔记已移到回收站，可在回收站恢复；共享附件未删除。');
    expect(deletes).toHaveLength(1);
    expect(new Headers(deletes[0].headers).get('If-Match')).toBe(`"${note.etag}"`);
    expect(new Headers(deletes[0].headers).get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/i);
    expect(screen.getByText('选择笔记或新建 Draft')).toBeTruthy();
  });

  it('reports an unconfigured Trash root honestly and keeps the note untouched', async () => {
    const note = { collection: 'projects', path: 'synthetic.md', content: '# Synthetic\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/notes' && !init?.method) return new Response(JSON.stringify({ collections: [{ id: 'projects', kind: 'authorized' }] }), { status: 200 });
      if (url === '/api/notes/projects') return new Response(JSON.stringify({ items: [{ path: note.path, title: 'Synthetic' }] }), { status: 200 });
      if (url === '/api/notes/projects/synthetic.md') return new Response(JSON.stringify(note), { status: 200 });
      if (url === '/api/notes/trash?limit=50&offset=0') return new Response(JSON.stringify({ detail: 'Notes Trash is not configured' }), { status: 501 });
      throw new Error(`Unexpected request ${url}`);
    });
    render(<NotesPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Synthetic' }));
    fireEvent.click(screen.getByRole('button', { name: '回收站' }));
    expect(await screen.findByText('回收站尚未配置。笔记未被删除；请先配置隔离的 Trash 存储位置。')).toBeTruthy();
    expect(screen.getByRole('button', { name: '返回笔记' })).toBeTruthy();
  });

  it('keeps a conflicted Trash item and refuses to overwrite its original path', async () => {
    const item = { trash_id: 'b'.repeat(32), collection: 'projects', path: 'synthetic.md', sha256: 'a'.repeat(64), size_bytes: 10, trashed_at: '2026-10-24T00:00:00Z', status: 'trashed', duplicate: false, recovery_reason: null };
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    let restoreCalls = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/notes' && !init?.method) return new Response(JSON.stringify({ collections: [{ id: 'projects', kind: 'authorized' }] }), { status: 200 });
      if (url === '/api/notes/projects') return new Response(JSON.stringify({ items: [] }), { status: 200 });
      if (url === '/api/notes/trash?limit=50&offset=0') return new Response(JSON.stringify({ status: 'real', items: [item], pagination: { limit: 50, offset: 0, has_more: false } }), { status: 200 });
      if (url === `/api/notes/trash/${item.trash_id}/restore` && init?.method === 'POST') {
        restoreCalls += 1;
        return new Response(JSON.stringify({ detail: 'Restore target already exists' }), { status: 409 });
      }
      throw new Error(`Unexpected request ${url}`);
    });
    render(<NotesPage />);
    fireEvent.click(await screen.findByRole('button', { name: '回收站' }));
    fireEvent.click(await screen.findByRole('button', { name: '恢复到原目录' }));
    expect(await screen.findByText('恢复目标已存在，未覆盖任何文件。请先处理同名目标后再重试。')).toBeTruthy();
    expect(screen.getByText('synthetic.md')).toBeTruthy();
    expect(restoreCalls).toBe(1);
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('拒绝覆盖'));
  });

});
