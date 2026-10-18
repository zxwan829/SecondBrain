import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./api/home', () => ({ fetchHome: vi.fn(async () => ({})) }));
vi.mock('./MarkdownEditor', () => ({
  MarkdownEditor: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => <textarea aria-label="合成 Markdown 编辑器" value={value} onChange={(event) => onChange(event.target.value)} />,
}));
vi.mock('./MindMapEditor', () => ({
  MindMapEditor: ({ content, onChange }: { content: string; onChange: (value: string) => void }) => <textarea aria-label="合成脑图编辑器" value={content} onChange={(event) => onChange(event.target.value)} />,
}));

import { App } from './App';

const syntheticCollections = { collections: [{ id: 'drafts', kind: 'drafts' }] };
const singleDraftId = 'ec5467a3-3087-45a2-befd-74038d08830c';

function mockAppFetch(notesStatus = 200, deferPut?: () => Promise<Response>) {
  const calls: string[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push(url);
    if (url === '/api/auth/session') return new Response('{}', { status: 200 });
    if (url === '/api/notes') return new Response(JSON.stringify(notesStatus === 200 ? syntheticCollections : { detail: 'synthetic gate denial' }), { status: notesStatus });
    if (url === '/api/notes/drafts') return new Response(JSON.stringify({ items: [{ path: 'synthetic.md', title: '合成笔记' }] }), { status: 200 });
    if (url === `/api/notes/drafts/${singleDraftId}`) return new Response(JSON.stringify({ collection: 'drafts', path: singleDraftId, content: '# 指定合成 Draft\n\nB1 synthetic only.\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] }), { status: 200 });
    if (url.startsWith('/api/inbox/proposals?')) return new Response(JSON.stringify({ proposals: [] }), { status: 200 });
    if (url.endsWith('/visual-assets/mindmap') && init?.method === 'POST') return new Response(JSON.stringify({ filename: `${'1'.repeat(32)}.mindmap.json`, etag: 'b'.repeat(64) }), { status: 200 });
    if (init?.method === 'PUT' && deferPut) return deferPut();
    if (init?.method === 'PUT') {
      const body = JSON.parse(String(init.body)) as { content: string };
      return new Response(JSON.stringify({ collection: 'drafts', path: 'synthetic.md', content: body.content, etag: 'c'.repeat(64), read_only: false, safety_reasons: [] }), { status: 200 });
    }
    if (url === '/api/notes/drafts/synthetic.md') return new Response(JSON.stringify({
      collection: 'drafts', path: 'synthetic.md', content: '# 合成笔记\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [],
    }), { status: 200 });
    return new Response('{}', { status: 200 });
  });
  return calls;
}

function startAt(path = '/') {
  localStorage.clear();
  history.replaceState({}, '', path);
  return render(<App />);
}

describe('Notes application navigation gate', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    history.replaceState({}, '', '/');
    localStorage.clear();
  });

  it('keeps Notes hidden and redirects a deep link when its feature flag is off', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'false');
    mockAppFetch();
    startAt('/notes/drafts/example');

    await screen.findByRole('heading', { name: '你的工作台' });
    await waitFor(() => expect(location.pathname).toBe('/'));
    expect(screen.queryByRole('button', { name: '笔记' })).toBeNull();
    expect(screen.queryByRole('heading', { name: '笔记' })).toBeNull();
  });

  it.each([403, 503])('keeps Notes unavailable and redirects a deep link when Core returns HTTP %i', async (status) => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const calls = mockAppFetch(status);
    startAt('/notes');

    await screen.findByRole('heading', { name: '你的工作台' });
    await waitFor(() => expect(location.pathname).toBe('/'));
    expect(calls.filter((url) => url === '/api/notes')).toHaveLength(1);
    expect(screen.queryByRole('button', { name: '笔记' })).toBeNull();
    expect(screen.queryByRole('heading', { name: '笔记' })).toBeNull();
  });

  it('opens the dedicated single-source route without loading the full Inbox or Notes lists', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const calls = mockAppFetch();
    startAt(`/inbox/source?collection=drafts&path=${singleDraftId}`);

    expect(await screen.findByRole('heading', { name: '指定合成 Draft' })).toBeTruthy();
    await waitFor(() => expect(calls.some((url) => url.startsWith('/api/inbox/proposals?source_kind=notes&'))).toBe(true));
    expect(calls).toContain(`/api/notes/drafts/${singleDraftId}`);
    expect(calls.some((url) => url === '/api/notes' || url === '/api/notes/drafts' || url === '/api/inbox?limit=100')).toBe(false);
    expect(calls.filter((url) => url === `/api/notes/drafts/${singleDraftId}`)).toHaveLength(1);
  });

  it('fails closed for an invalid single-source URL without reading a Draft or Inbox source', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const calls = mockAppFetch();
    startAt('/inbox/source?collection=capture&path=../../private');

    expect(await screen.findByText('必须提供有效的 Draft 来源；未加载任何收件箱来源。')).toBeTruthy();
    expect(calls.some((url) => url.startsWith('/api/notes/drafts/') || url.startsWith('/api/inbox'))).toBe(false);
    expect(calls).not.toContain('/api/notes');
  });

  it('opens and leaves Notes through desktop navigation after the Core read gate succeeds', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    mockAppFetch();
    startAt('/');

    const notesButton = await screen.findByRole('button', { name: '笔记' });
    fireEvent.click(notesButton);
    expect(await screen.findByRole('heading', { name: '笔记' })).toBeTruthy();
    expect(location.pathname).toBe('/notes');

    fireEvent.click(screen.getByRole('button', { name: '首页' }));
    await screen.findByRole('heading', { name: '你的工作台' });
    expect(location.pathname).toBe('/');
  });

  it('restores the Notes route on refresh and opens it from the mobile menu', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    mockAppFetch();
    startAt('/notes');
    expect(await screen.findByRole('heading', { name: '笔记' })).toBeTruthy();
    expect(location.pathname).toBe('/notes');

    fireEvent.click(screen.getByRole('button', { name: '打开导航菜单' }));
    const sidebar = document.querySelector('aside.sidebar') as HTMLElement;
    expect(sidebar.classList.contains('is-open')).toBe(true);
    fireEvent.click(within(sidebar).getByRole('button', { name: '笔记' }));
    expect(location.pathname).toBe('/notes');
    expect(screen.getByRole('button', { name: '打开导航菜单' }).getAttribute('aria-expanded')).toBe('false');
    expect(await screen.findByRole('heading', { name: '笔记' })).toBeTruthy();
  });

  it('blocks shell navigation when the real NotesPage has unsaved Markdown and honors confirmation', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    mockAppFetch();
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    startAt('/');

    fireEvent.click(await screen.findByRole('button', { name: '笔记' }));
    fireEvent.click(await screen.findByRole('button', { name: '合成笔记' }));
    const editor = await screen.findByLabelText('合成 Markdown 编辑器') as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: '# 尚未保存\n' } });

    fireEvent.click(screen.getByRole('button', { name: '首页' }));
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(location.pathname).toBe('/notes');
    expect(editor.value).toBe('# 尚未保存\n');

    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByRole('button', { name: '首页' }));
    await screen.findByRole('heading', { name: '你的工作台' });
    expect(location.pathname).toBe('/');
  });

  it('restores Notes after browser back when leaving is declined', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    mockAppFetch();
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    startAt('/');
    fireEvent.click(await screen.findByRole('button', { name: '笔记' }));
    fireEvent.click(await screen.findByRole('button', { name: '合成笔记' }));
    const editor = await screen.findByLabelText('合成 Markdown 编辑器') as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: '# 浏览器返回保护\n' } });

    const popStates: unknown[] = [];
    const capturePop = (event: PopStateEvent) => popStates.push(event.state);
    window.addEventListener('popstate', capturePop);
    window.history.back();
    await waitFor(() => expect(popStates).toHaveLength(2));
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(location.pathname).toBe('/notes');
    expect(editor.value).toBe('# 浏览器返回保护\n');

    confirm.mockReturnValue(true);
    window.history.back();
    await waitFor(() => expect(popStates).toHaveLength(3));
    await screen.findByRole('heading', { name: '你的工作台' });
    expect(location.pathname).toBe('/');
    window.removeEventListener('popstate', capturePop);
  });

  it('blocks shell navigation while a Markdown save request is in flight', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    let resolvePut!: (response: Response) => void;
    const pendingPut = new Promise<Response>((resolve) => { resolvePut = resolve; });
    mockAppFetch(200, () => pendingPut);
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    startAt('/');
    fireEvent.click(await screen.findByRole('button', { name: '笔记' }));
    fireEvent.click(await screen.findByRole('button', { name: '合成笔记' }));
    const editor = await screen.findByLabelText('合成 Markdown 编辑器') as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: '# 保存进行中\n' } });
    await screen.findByText('保存中…', {}, { timeout: 3000 });

    fireEvent.click(screen.getByRole('button', { name: '首页' }));
    expect(confirm).not.toHaveBeenCalled();
    expect(location.pathname).toBe('/notes');
    expect(screen.getByText('当前笔记正在保存，请等待保存完成后再切换。')).toBeTruthy();

    await act(async () => {
      resolvePut(new Response(JSON.stringify({ collection: 'drafts', path: 'synthetic.md', content: '# 保存进行中\n', etag: 'c'.repeat(64), read_only: false, safety_reasons: [] }), { status: 200 }));
      for (let i = 0; i < 10; i += 1) await Promise.resolve();
    });
  });

  it('blocks shell navigation while a real NotesPage visual editor has unsaved changes', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    mockAppFetch();
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    startAt('/');
    fireEvent.click(await screen.findByRole('button', { name: '笔记' }));
    fireEvent.click(await screen.findByRole('button', { name: '合成笔记' }));
    await screen.findByLabelText('合成 Markdown 编辑器');
    fireEvent.click(screen.getByRole('button', { name: '插入思维导图' }));
    const graphEditor = await screen.findByLabelText('合成脑图编辑器') as HTMLTextAreaElement;
    fireEvent.change(graphEditor, { target: { value: '{"edited":true}' } });
    await screen.findByText('有未保存修改');

    fireEvent.click(screen.getByRole('button', { name: '首页' }));
    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
    expect(location.pathname).toBe('/notes');
    expect(screen.getByRole('dialog', { name: '思维导图' })).toBeTruthy();
    expect(screen.getByText('有未保存修改')).toBeTruthy();
  });
});
