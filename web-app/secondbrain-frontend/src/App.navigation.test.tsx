import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./MarkdownEditor', () => ({
  MarkdownEditor: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => <textarea aria-label="合成 Markdown 编辑器" value={value} onChange={(event) => onChange(event.target.value)} />,
}));
vi.mock('./MindMapEditor', () => ({
  MindMapEditor: ({ content, onChange }: { content: string; onChange: (value: string) => void }) => <textarea aria-label="合成脑图编辑器" value={content} onChange={(event) => onChange(event.target.value)} />,
}));

import { App } from './App';

const syntheticCollections = { collections: [{ id: 'drafts', kind: 'drafts' }] };
const singleDraftId = 'ec5467a3-3087-45a2-befd-74038d08830c';
const secondDraftId = 'acf4e33a-349f-4d8f-84a5-cec5304ae100';
const captureId = '1234567890abcdef1234567890abcdef';
const secondCaptureId = 'abcdef1234567890abcdef1234567890';

function mockAppFetch(notesStatus = 200, deferPut?: () => Promise<Response>, summaryStatus = 200) {
  const calls: string[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push(url);
    if (url === '/api/auth/session') return new Response('{}', { status: 200 });
    if (url === '/api/home') return new Response('{}', { status: 200 });
    if (url === '/api/inbox/summary?limit=100') return new Response(JSON.stringify(summaryStatus === 200 ? { status: 'real', items: [{ capture_id: captureId, source_type: 'text', input_type: 'text', captured_at: '2026-10-18T00:00:00Z', display_filename: 'synthetic.txt', status: 'completed', error_code: null, has_review: false }] } : { detail: 'synthetic failure' }), { status: summaryStatus });
    if (url === `/api/capture/${captureId}`) return new Response(JSON.stringify({ capture_id: captureId, source_type: 'text', input_type: 'text', captured_at: '2026-10-18T00:00:00Z', raw_path: 'synthetic.txt', display_filename: 'synthetic.txt', title: 'Synthetic capture', status: 'completed', content_preview: 'SYNTHETIC EXACT CAPTURE BODY', review_path: null }), { status: 200 });
    if (url === `/api/inbox/${captureId}/preview`) return new Response('SYNTHETIC EXACT CAPTURE BODY', { status: 200 });
    if (url === '/api/notes') return new Response(JSON.stringify(notesStatus === 200 ? syntheticCollections : { detail: 'synthetic gate denial' }), { status: notesStatus });
    if (url === '/api/notes/drafts') return new Response(JSON.stringify({ items: [{ path: 'synthetic.md', title: '合成笔记' }, { path: singleDraftId, title: 'Inbox 合成草稿' }] }), { status: 200 });
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
    expect(calls).not.toContain('/api/home');
    expect(calls.some((url) => url === '/api/notes' || url === '/api/notes/drafts' || url === '/api/inbox?limit=100')).toBe(false);
    expect(calls.filter((url) => url === `/api/notes/drafts/${singleDraftId}`)).toHaveLength(1);
  });

  it('keeps ordinary Home loading unchanged', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const calls = mockAppFetch();
    startAt('/');
    await screen.findByRole('heading', { name: '你的工作台' });
    await waitFor(() => expect(calls).toContain('/api/home'));
  });

  it('opens Knowledge from navigation and does not issue Knowledge reads from other page initialization', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const calls = mockAppFetch();
    startAt('/');
    await screen.findByRole('heading', { name: '你的工作台' });

    fireEvent.click(screen.getByRole('button', { name: '知识库' }));
    expect(await screen.findByRole('heading', { name: '知识库' })).toBeTruthy();
    expect(location.pathname).toBe('/knowledge');
    expect(calls.some((url) => url.startsWith('/api/knowledge/'))).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: '首页' }));
    await screen.findByRole('heading', { name: '你的工作台' });
    fireEvent.click(screen.getByRole('button', { name: '对话' }));
    await waitFor(() => expect(location.pathname).toBe('/chat'));
    fireEvent.click(screen.getByRole('button', { name: '收件箱' }));
    await waitFor(() => expect(location.pathname).toBe('/inbox'));
    fireEvent.click(screen.getByRole('button', { name: '笔记' }));
    await screen.findByRole('heading', { name: '笔记' });
    expect(calls.some((url) => url.startsWith('/api/knowledge/'))).toBe(false);
  });

  it('restores the Knowledge route directly and keeps it available in the mobile navigation', async () => {
    const calls = mockAppFetch();
    startAt('/knowledge');
    expect(await screen.findByRole('heading', { name: '知识库' })).toBeTruthy();
    expect(location.pathname).toBe('/knowledge');
    expect(calls.some((url) => url.startsWith('/api/knowledge/'))).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: '打开导航菜单' }));
    const sidebar = document.querySelector('aside.sidebar') as HTMLElement;
    fireEvent.click(within(sidebar).getByRole('button', { name: '知识库' }));
    expect(location.pathname).toBe('/knowledge');
    expect(await screen.findByRole('heading', { name: '知识库' })).toBeTruthy();
  });

  it('isolates rapid source changes when an older exact Notes read returns last', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const calls: string[] = [];
    let finishFirstRead!: (response: Response) => void;
    const firstRead = new Promise<Response>((resolve) => { finishFirstRead = resolve; });
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      calls.push(url);
      if (url === '/api/auth/session' || url === '/api/home') return new Response('{}', { status: 200 });
      if (url === `/api/notes/drafts/${singleDraftId}`) return firstRead;
      if (url === `/api/notes/drafts/${secondDraftId}`) return new Response(JSON.stringify({ collection: 'drafts', path: secondDraftId, content: '# New source B\n', etag: 'b'.repeat(64), read_only: false, safety_reasons: [] }), { status: 200 });
      if (url.startsWith('/api/inbox/proposals?')) return new Response(JSON.stringify({ proposals: [] }), { status: 200 });
      return new Response('{}', { status: 200 });
    });
    startAt(`/inbox/source?collection=drafts&path=${singleDraftId}`);
    await waitFor(() => expect(calls).toContain(`/api/notes/drafts/${singleDraftId}`));

    history.pushState({}, '', `/inbox/source?collection=drafts&path=${secondDraftId}`);
    await act(async () => { window.dispatchEvent(new PopStateEvent('popstate', { state: {} })); });
    expect(await screen.findByRole('heading', { name: 'New source B' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: '指定合成 Draft' })).toBeNull();

    await act(async () => {
      finishFirstRead(new Response(JSON.stringify({ collection: 'drafts', path: singleDraftId, content: '# Old source A\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] }), { status: 200 }));
      await firstRead;
    });
    expect(await screen.findByRole('heading', { name: 'New source B' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Old source A' })).toBeNull();
    expect(calls.filter((url) => url.startsWith('/api/notes/drafts/'))).toEqual([
      `/api/notes/drafts/${singleDraftId}`, `/api/notes/drafts/${secondDraftId}`,
    ]);
    const proposalReads = calls.filter((url) => url.startsWith('/api/inbox/proposals?'));
    expect(proposalReads).toHaveLength(1);
    expect(new URLSearchParams(proposalReads[0].split('?')[1]).get('source_id')).toBe(`drafts:${secondDraftId}`);
    expect(calls.some((url) => url === '/api/home')).toBe(false);
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

describe('Inbox explicit source scopes', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    history.replaceState({}, '', '/');
    localStorage.clear();
    sessionStorage.clear();
  });

  it('opens /inbox with no business-source requests even when stale scope values exist', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const calls = mockAppFetch();
    localStorage.clear();
    localStorage.setItem('secondbrain.inbox.scope', 'capture');
    localStorage.setItem('secondbrain.notes.collection', 'authorized');
    sessionStorage.setItem('secondbrain.inbox.scope', 'drafts');
    history.replaceState({ sbInboxScope: 'capture' }, '', '/inbox');
    render(<App />);

    expect(await screen.findByRole('heading', { name: '选择收件箱范围' })).toBeTruthy();
    expect(calls).toEqual(['/api/auth/session']);
    expect(screen.getByRole('button', { name: /Capture 待处理/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Notes Draft 草稿/ })).toBeTruthy();
  });

  it.each([401, 403, 503])('keeps Capture scope fail-closed after HTTP %i', async (status) => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const calls = mockAppFetch(200, undefined, status);
    startAt('/inbox');
    fireEvent.click(await screen.findByRole('button', { name: /Capture 待处理/ }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(calls).toEqual(['/api/auth/session', '/api/inbox/summary?limit=100']);
    expect(calls.some((url) => url === '/api/home' || url === '/api/inbox' || url === '/api/notes' || url === '/api/notes/drafts')).toBe(false);
  });

  it('loads only Capture metadata after selection and exact detail only after clicking one item', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const calls = mockAppFetch();
    startAt('/inbox');
    fireEvent.click(await screen.findByRole('button', { name: /Capture 待处理/ }));
    expect(await screen.findByRole('heading', { name: 'synthetic.txt' })).toBeTruthy();
    expect(calls).toEqual(['/api/auth/session', '/api/inbox/summary?limit=100']);
    expect(screen.queryByText('SYNTHETIC EXACT CAPTURE BODY')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '打开此 Capture' }));
    expect(await screen.findByRole('dialog', { name: 'synthetic.txt' })).toBeTruthy();
    await screen.findByText('SYNTHETIC EXACT CAPTURE BODY');
    expect(calls).toEqual([
      '/api/auth/session', '/api/inbox/summary?limit=100', `/api/capture/${captureId}`, `/api/inbox/${captureId}/preview`,
    ]);
    expect(calls.some((url) => url === '/api/notes' || url === '/api/notes/drafts' || url === '/api/home')).toBe(false);
  });

  it('keeps retry scoped to the explicitly selected Capture', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const calls: string[] = [];
    let summaryRequests = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input); calls.push(`${init?.method || 'GET'} ${url}`);
      if (url === '/api/auth/session') return new Response('{}', { status: 200 });
      if (url === '/api/inbox/summary?limit=100') {
        summaryRequests += 1;
        const status = summaryRequests === 1 ? 'partial_success' : 'completed';
        return new Response(JSON.stringify({ items: [{ capture_id: captureId, source_type: 'image', input_type: 'png', captured_at: '2026-10-18T00:00:00Z', display_filename: 'synthetic.png', status, error_code: status === 'partial_success' ? 'processor_unavailable' : null, has_review: false }] }), { status: 200 });
      }
      if (url === `/api/capture/${captureId}`) return new Response(JSON.stringify({ capture_id: captureId, source_type: 'image', input_type: 'png', captured_at: '2026-10-18T00:00:00Z', raw_path: 'synthetic.png', display_filename: 'synthetic.png', status: 'partial_success', error: { code: 'processor_unavailable' }, review_path: null }), { status: 200 });
      if (url === `/api/capture/${captureId}/retry`) return new Response(JSON.stringify({ capture_id: captureId, source_type: 'image', input_type: 'png', captured_at: '2026-10-18T00:00:00Z', raw_path: 'synthetic.png', display_filename: 'synthetic.png', status: 'completed', review_path: 'synthetic-review.md' }), { status: 200 });
      return new Response('{}', { status: 200 });
    });
    startAt('/inbox');
    fireEvent.click(await screen.findByRole('button', { name: /Capture 待处理/ }));
    fireEvent.click(await screen.findByRole('button', { name: '打开此 Capture' }));
    expect(await screen.findByRole('button', { name: '重试此 Capture' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '重试此 Capture' }));
    await waitFor(() => expect(summaryRequests).toBe(2));
    expect(screen.queryByRole('button', { name: '重试此 Capture' })).toBeNull();
    expect(calls).toEqual([
      'GET /api/auth/session', 'GET /api/inbox/summary?limit=100', `GET /api/capture/${captureId}`,
      `POST /api/capture/${captureId}/retry`, 'GET /api/inbox/summary?limit=100',
    ]);
  });

  it.each(['success', 'failure'] as const)('ignores a late Capture A retry %s after Capture B is selected', async (outcome) => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const calls: string[] = [];
    let resolveRetry!: (response: Response) => void;
    const delayedRetry = new Promise<Response>((resolve) => { resolveRetry = resolve; });
    const state = (id: string, displayFilename: string, status: string) => ({ capture_id: id, source_type: 'image', input_type: 'png', captured_at: '2026-10-18T00:00:00Z', raw_path: `${displayFilename}`, display_filename: displayFilename, status, error: status === 'partial_success' ? { code: 'processor_unavailable' } : null, review_path: null });
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input); calls.push(`${init?.method || 'GET'} ${url}`);
      if (url === '/api/auth/session') return new Response('{}', { status: 200 });
      if (url === '/api/inbox/summary?limit=100') return new Response(JSON.stringify({ items: [
        { capture_id: captureId, source_type: 'image', input_type: 'png', captured_at: '2026-10-18T00:00:00Z', display_filename: 'capture-a.png', status: 'partial_success', error_code: 'processor_unavailable', has_review: false },
        { capture_id: secondCaptureId, source_type: 'image', input_type: 'png', captured_at: '2026-10-18T00:01:00Z', display_filename: 'capture-b.png', status: 'completed', error_code: null, has_review: false },
      ] }), { status: 200 });
      if (url === `/api/capture/${captureId}`) return new Response(JSON.stringify(state(captureId, 'capture-a.png', 'partial_success')), { status: 200 });
      if (url === `/api/capture/${secondCaptureId}`) return new Response(JSON.stringify(state(secondCaptureId, 'capture-b.png', 'completed')), { status: 200 });
      if (url === `/api/capture/${captureId}/retry`) return delayedRetry;
      return new Response('{}', { status: 200 });
    });
    startAt('/inbox');
    fireEvent.click(await screen.findByRole('button', { name: /Capture 待处理/ }));
    await screen.findByRole('heading', { name: 'capture-a.png' });
    fireEvent.click(screen.getAllByRole('button', { name: '打开此 Capture' })[0]);
    const dialogA = await screen.findByRole('dialog');
    expect(within(dialogA).getByRole('heading', { name: 'capture-a.png' })).toBeTruthy();
    fireEvent.click(await within(dialogA).findByRole('button', { name: '重试此 Capture' }));
    await waitFor(() => expect(calls).toContain(`POST /api/capture/${captureId}/retry`));

    fireEvent.click(within(dialogA).getAllByRole('button', { name: '关闭' })[0]);
    fireEvent.click(screen.getAllByRole('button', { name: '打开此 Capture' })[1]);
    const dialogB = await screen.findByRole('dialog');
    expect(within(dialogB).getByRole('heading', { name: 'capture-b.png' })).toBeTruthy();

    await act(async () => {
      resolveRetry(outcome === 'success'
        ? new Response(JSON.stringify(state(captureId, 'capture-a.png', 'completed')), { status: 200 })
        : new Response(JSON.stringify({ detail: 'synthetic retry failure' }), { status: 503 }));
      for (let i = 0; i < 8; i += 1) await Promise.resolve();
    });
    expect(screen.getByRole('dialog')).toBe(dialogB);
    expect(within(dialogB).getByRole('heading', { name: 'capture-b.png' })).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(calls).toEqual([
      'GET /api/auth/session', 'GET /api/inbox/summary?limit=100', `GET /api/capture/${captureId}`,
      `POST /api/capture/${captureId}/retry`, `GET /api/capture/${secondCaptureId}`,
    ]);
  });

  it('refreshes only the selected Capture scope and stops scoped refresh on exit', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const calls: string[] = [];
    const intervalSpy = vi.spyOn(window, 'setInterval');
    let summaryRequests = 0;
    let organizerRequests = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input); calls.push(url);
      if (url === '/api/auth/session') return new Response('{}', { status: 200 });
      if (url === '/api/inbox/summary?limit=100') { summaryRequests += 1; return new Response(JSON.stringify({ items: [] }), { status: 200 }); }
      if (url === '/api/automation/organize/status') { organizerRequests += 1; return new Response(JSON.stringify({ execution_available: false, blocked_reason: 'Synthetic disabled' }), { status: 200 }); }
      return new Response('{}', { status: 200 });
    });
    startAt('/inbox');
    expect(await screen.findByRole('heading', { name: '选择收件箱范围' })).toBeTruthy();
    expect(intervalSpy.mock.calls.some(([, delay]) => delay === 5000)).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: /Capture 待处理/ }));
    await waitFor(() => expect(summaryRequests).toBe(1));
    expect(intervalSpy.mock.calls.some(([, delay]) => delay === 5000)).toBe(true);
    expect(organizerRequests).toBe(0);

    await act(async () => { window.dispatchEvent(new Event('sb-inbox-refresh')); });
    await waitFor(() => expect(summaryRequests).toBe(2));
    expect(organizerRequests).toBe(0);

    fireEvent.click(screen.getByRole('button', { name: '查看自动整理状态' }));
    await waitFor(() => expect(organizerRequests).toBe(1));
    expect(calls.filter((url) => url === '/api/automation/organize/run')).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: '更换范围' }));
    await act(async () => { window.dispatchEvent(new Event('sb-inbox-refresh')); });
    expect(summaryRequests).toBe(2);
    expect(organizerRequests).toBe(1);
  });

  it('runs Organizer only after its explicit action is enabled and clicked', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input); calls.push(`${init?.method || 'GET'} ${url}`);
      if (url === '/api/auth/session') return new Response('{}', { status: 200 });
      if (url === '/api/inbox/summary?limit=100') return new Response(JSON.stringify({ items: [] }), { status: 200 });
      if (url === '/api/automation/organize/status') return new Response(JSON.stringify({ execution_available: true, blocked_reason: '' }), { status: 200 });
      if (url === '/api/automation/organize/run' && init?.method === 'POST') return new Response(JSON.stringify({ status: 'no_new_messages' }), { status: 200 });
      return new Response('{}', { status: 200 });
    });
    startAt('/inbox');
    fireEvent.click(await screen.findByRole('button', { name: /Capture 待处理/ }));
    await screen.findByText('没有 Capture 条目。');
    expect(calls.some((entry) => entry.endsWith('/api/automation/organize/status'))).toBe(false);
    expect(calls.some((entry) => entry.endsWith('/api/automation/organize/run'))).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: '查看自动整理状态' }));
    await waitFor(() => expect(calls).toContain('GET /api/automation/organize/status'));
    expect(calls.some((entry) => entry.endsWith('/api/automation/organize/run'))).toBe(false);
    fireEvent.click(await screen.findByRole('button', { name: '立即整理' }));
    await screen.findByText('没有新增对话，无需整理。');
    expect(calls).toContain('POST /api/automation/organize/run');
  });

  it('loads only Draft metadata after explicit selection and reads one exact Draft after click', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const calls = mockAppFetch();
    startAt('/inbox');
    fireEvent.click(await screen.findByRole('button', { name: /Notes Draft 草稿/ }));
    expect(await screen.findByRole('heading', { name: 'Inbox 合成草稿' })).toBeTruthy();
    expect(calls).toEqual(['/api/auth/session', '/api/notes/drafts']);
    expect(calls.some((url) => url.startsWith('/api/notes/drafts/'))).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: '打开此 Draft' }));
    expect(await screen.findByRole('heading', { name: '指定合成 Draft' })).toBeTruthy();
    await waitFor(() => expect(calls.some((url) => url.startsWith('/api/inbox/proposals?'))).toBe(true));
    expect(calls).toContain(`/api/notes/drafts/${singleDraftId}`);
    expect(calls.filter((url) => url.startsWith('/api/notes/drafts/'))).toEqual([`/api/notes/drafts/${singleDraftId}`]);
    expect(calls.some((url) => url === '/api/notes' || url === '/api/inbox' || url === '/api/home')).toBe(false);
  });

  it.each([401, 403, 503])('keeps Notes Drafts scope fail-closed after HTTP %i', async (status) => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input); calls.push(url);
      if (url === '/api/auth/session') return new Response('{}', { status: 200 });
      if (url === '/api/notes/drafts') return new Response(JSON.stringify({ detail: 'synthetic denial' }), { status });
      return new Response('{}', { status: 200 });
    });
    startAt('/inbox');
    fireEvent.click(await screen.findByRole('button', { name: /Notes Draft 草稿/ }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(calls).toEqual(['/api/auth/session', '/api/notes/drafts']);
  });

  it('resets an explicitly selected Inbox scope to neutral after refresh', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const calls = mockAppFetch();
    startAt('/inbox');
    fireEvent.click(await screen.findByRole('button', { name: /Capture 待处理/ }));
    expect(await screen.findByRole('heading', { name: 'synthetic.txt' })).toBeTruthy();
    await waitFor(() => expect(calls).toContain('/api/inbox/summary?limit=100'));
    cleanup();
    history.replaceState({}, '', '/inbox');
    render(<App />);
    expect(await screen.findByRole('heading', { name: '选择收件箱范围' })).toBeTruthy();
    expect(calls).toEqual(['/api/auth/session', '/api/inbox/summary?limit=100', '/api/auth/session']);
  });

  it('stays neutral for an invalid Inbox deep path', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const invalidPathCalls = mockAppFetch();
    history.replaceState({}, '', '/inbox/invalid-scope');
    render(<App />);
    expect(await screen.findByRole('heading', { name: '选择收件箱范围' })).toBeTruthy();
    expect(invalidPathCalls).toEqual(['/api/auth/session']);
  });

  it('does not let a late Capture summary response cross into a newly chosen Draft scope', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const calls: string[] = [];
    let resolveSummary!: (response: Response) => void;
    const delayedSummary = new Promise<Response>((resolve) => { resolveSummary = resolve; });
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input); calls.push(url);
      if (url === '/api/auth/session') return new Response('{}', { status: 200 });
      if (url === '/api/inbox/summary?limit=100') return delayedSummary;
      if (url === '/api/notes/drafts') return new Response(JSON.stringify({ items: [{ path: singleDraftId, title: 'Draft after switch' }] }), { status: 200 });
      return new Response('{}', { status: 200 });
    });
    startAt('/inbox');
    fireEvent.click(await screen.findByRole('button', { name: /Capture 待处理/ }));
    await waitFor(() => expect(calls).toContain('/api/inbox/summary?limit=100'));
    fireEvent.click(screen.getByRole('button', { name: '更换范围' }));
    fireEvent.click(screen.getByRole('button', { name: /Notes Draft 草稿/ }));
    expect(await screen.findByRole('heading', { name: 'Draft after switch' })).toBeTruthy();
    await act(async () => { resolveSummary(new Response(JSON.stringify({ items: [{ capture_id: captureId, display_filename: 'stale capture body' }] }), { status: 200 })); });
    expect(screen.queryByText('stale capture body')).toBeNull();
    expect(calls).toEqual(['/api/auth/session', '/api/inbox/summary?limit=100', '/api/notes/drafts']);
  });
});
