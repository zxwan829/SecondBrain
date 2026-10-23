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

function mockAppFetch(notesStatus = 200, deferPut?: () => Promise<Response>, summaryStatus = 200, homeBody: unknown = {}) {
  const calls: string[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push(url);
    if (url === '/api/auth/session') return new Response('{}', { status: 200 });
    if (url === '/api/home') return new Response(JSON.stringify(homeBody), { status: 200 });
    if (/^\/api\/journal\/\d{4}-\d{2}-\d{2}$/.test(url)) return new Response(JSON.stringify({ date: url.slice(-10), entries: [] }), { status: 200 });
    if (url === '/api/projects?limit=50&offset=0') return new Response(JSON.stringify({ status: 'not_configured', items: [], pagination: { limit: 50, offset: 0, has_more: false }, source: null, freshness: { checked_at: '2026-10-20T01:30:00Z' } }), { status: 200 });
    if (url === '/api/activity?limit=50&offset=0') return new Response(JSON.stringify({ status: 'ok', items: [{ activity_id: 'opaque-synth-event-1', kind: 'journal', status: 'succeeded', occurred_at: '2026-10-20T09:30:00+08:00', journal_date: '2026-10-20' }], pagination: { limit: 50, offset: 0, has_more: false }, source: ['journal'], freshness: { checked_at: '2026-10-20T01:30:00Z' } }), { status: 200 });
    if (url.startsWith('/api/daily-brief?')) return new Response(JSON.stringify({ status: 'not_configured', items: [], source: null, freshness: { checked_at: '2026-10-20T01:30:00Z' } }), { status: 200 });
    if (url === '/api/agent/health') return new Response(JSON.stringify({ status: 'not_configured', source: null, checked_at: '2026-10-20T01:30:00Z' }), { status: 200 });
    if (url.startsWith('/api/calendar?')) {
      const query = new URLSearchParams(url.split('?')[1]);
      return new Response(JSON.stringify({ status: 'ok', items: [{ id: 'opaque-calendar-synth-1', kind: 'task', date: query.get('from'), status: 'open' }], source: ['tasks'], freshness: { checked_at: '2026-10-20T01:30:00Z' } }), { status: 200 });
    }
    if (url.startsWith('/api/knowledge/search?')) return new Response(JSON.stringify({ items: [], status: 'ok' }), { status: 200 });
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
    expect(calls).toEqual(['/api/auth/session', '/api/home']);
    fireEvent.click(screen.getByRole('button', { name: '查看完整日历' }));
    expect(await screen.findByRole('heading', { name: '日历' })).toBeTruthy();
    expect(calls.filter((url) => url === '/api/home')).toHaveLength(1);
    expect(calls.filter((url) => url.startsWith('/api/calendar?'))).toHaveLength(1);
  });

  it('routes the Home task action to the usable Task creation page', async () => {
    mockAppFetch(200, undefined, 200, { today: { items: [] } });
    startAt('/');
    await screen.findByRole('heading', { name: '你的工作台' });
    fireEvent.click(await screen.findByRole('button', { name: '新建待办' }));
    expect(await screen.findByRole('heading', { name: '今日与待办' })).toBeTruthy();
    expect(screen.getByRole('form', { name: '新建待办' })).toBeTruthy();
    expect(location.pathname).toBe('/today');
    expect(location.search).toBe('');
  });

  it('opens the existing real Projects, Daily Brief, Activity, Agent Health, and Journal destinations from Home', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'false');
    const calls = mockAppFetch();
    startAt('/');
    await screen.findByRole('heading', { name: '你的工作台' });

    fireEvent.click(screen.getAllByRole('button', { name: '打开项目' })[0]);
    expect(await screen.findByRole('heading', { name: '项目' })).toBeTruthy();
    await waitFor(() => expect(calls.some((url) => url.startsWith('/api/projects?'))).toBe(true));
    fireEvent.click(screen.getAllByRole('button', { name: '首页' })[0]);
    await screen.findByRole('heading', { name: '你的工作台' });

    fireEvent.click(screen.getAllByRole('button', { name: '打开每日简报' })[0]);
    expect(await screen.findByRole('heading', { name: '每日简报' })).toBeTruthy();
    await waitFor(() => expect(calls.some((url) => url.startsWith('/api/daily-brief?'))).toBe(true));
    fireEvent.click(screen.getAllByRole('button', { name: '首页' })[0]);
    await screen.findByRole('heading', { name: '你的工作台' });

    fireEvent.click(screen.getAllByRole('button', { name: '打开动态' })[0]);
    expect(await screen.findByRole('heading', { name: '动态' })).toBeTruthy();
    await waitFor(() => expect(calls.some((url) => url.startsWith('/api/activity?'))).toBe(true));
    fireEvent.click(screen.getAllByRole('button', { name: '首页' })[0]);
    await screen.findByRole('heading', { name: '你的工作台' });

    fireEvent.click(screen.getAllByRole('button', { name: '查看 Agent 状态' })[0]);
    expect(await screen.findByRole('heading', { name: 'Agent 状态' })).toBeTruthy();
    await waitFor(() => expect(calls).toContain('/api/agent/health'));
    fireEvent.click(screen.getAllByRole('button', { name: '首页' })[0]);
    await screen.findByRole('heading', { name: '你的工作台' });

    fireEvent.click(screen.getByRole('button', { name: /新建日记/ }));
    expect(await screen.findByRole('heading', { name: '日记' })).toBeTruthy();
    expect(location.pathname).toBe('/journal');
  });

  it('returns Home from Agent Health through the mobile navigation and closes the menu', async () => {
    mockAppFetch();
    startAt('/');
    await screen.findByRole('heading', { name: '你的工作台' });

    fireEvent.click(await screen.findByRole('button', { name: '查看 Agent 状态' }));
    await screen.findByRole('heading', { name: 'Agent 状态' });
    expect(location.pathname).toBe('/agent-health');

    fireEvent.click(screen.getByRole('button', { name: '打开导航菜单' }));
    const sidebar = document.querySelector('aside.sidebar') as HTMLElement;
    expect(sidebar.classList.contains('is-open')).toBe(true);
    fireEvent.click(within(sidebar).getByRole('button', { name: /^首页$/ }));

    await screen.findByRole('heading', { name: '你的工作台' });
    expect(location.pathname).toBe('/');
    expect(screen.getByRole('button', { name: '打开导航菜单' }).getAttribute('aria-expanded')).toBe('false');
  });

  it('opens Today from the mobile navigation and closes the menu after routing', async () => {
    const calls = mockAppFetch();
    startAt('/');
    await screen.findByRole('heading', { name: '你的工作台' });

    fireEvent.click(screen.getByRole('button', { name: '打开导航菜单' }));
    const sidebar = document.querySelector('aside.sidebar') as HTMLElement;
    const menu = document.querySelector('.mobile-menu-button') as HTMLButtonElement;
    expect(sidebar.classList.contains('is-open')).toBe(true);
    expect(menu.getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(within(sidebar).getByRole('button', { name: /^今日$/ }));

    expect(await screen.findByRole('heading', { name: '今日与待办' })).toBeTruthy();
    expect(location.pathname).toBe('/today');
    await waitFor(() => expect(calls).toContain('/api/tasks?status=open'));
    expect(menu.getAttribute('aria-expanded')).toBe('false');
    expect(sidebar.classList.contains('is-open')).toBe(false);
  });

  it('renders the expanded Activity source and status contract from Core', async () => {
    mockAppFetch();
    const fetchMock = vi.mocked(globalThis.fetch);
    const fallback = fetchMock.getMockImplementation()!;
    const base = '2026-10-23T08:00:00Z';
    fetchMock.mockImplementation(async (input, init) => {
      if (String(input) === '/api/activity?limit=50&offset=0') {
        return new Response(JSON.stringify({
          status: 'partial',
          items: [
            { activity_id: 'activity-project', kind: 'project', status: 'updated', occurred_at: base, project_id: 'SYNTH-PROJECT-1', project_status: 'active' },
            { activity_id: 'activity-brief', kind: 'daily_brief', status: 'created', occurred_at: base, daily_brief_date: '2026-10-23' },
            { activity_id: 'activity-memory', kind: 'personal_memory', status: 'revoked', occurred_at: base },
            ...(['pending', 'prepared', 'processing', 'completed', 'partial_success', 'failed'] as const).map((status, index) => ({
              activity_id: `activity-capture-${index}`, kind: 'capture' as const, status, occurred_at: base,
            })),
          ],
          pagination: { limit: 50, offset: 0, has_more: false },
          source: ['projects', 'daily_brief', 'personal_memory', 'capture'],
          freshness: { checked_at: base },
        }), { status: 200 });
      }
      return fallback(input, init);
    });
    startAt('/activity');

    expect(await screen.findByRole('heading', { name: '项目更新' })).toBeTruthy();
    expect(screen.getByText('已更新')).toBeTruthy();
    expect(screen.getAllByText('每日简报').length).toBeGreaterThan(0);
    expect(screen.getAllByText('2026-10-23').length).toBeGreaterThan(0);
    expect(screen.getByText('个人记忆操作')).toBeTruthy();
    expect(screen.getByText('已撤销')).toBeTruthy();
    expect(screen.getAllByText('采集状态')).toHaveLength(6);
    expect(screen.getByText('待处理')).toBeTruthy();
    expect(screen.getByText('已准备')).toBeTruthy();
    expect(screen.getByText('处理中')).toBeTruthy();
    expect(screen.getAllByText('已完成').length).toBeGreaterThan(0);
    expect(screen.getByText('部分完成')).toBeTruthy();
    expect(screen.getByText('失败')).toBeTruthy();
    expect(screen.getAllByText('采集')).toHaveLength(6);
  });

  it('fails closed on an unknown Capture Activity lifecycle status', async () => {
    mockAppFetch();
    const fetchMock = vi.mocked(globalThis.fetch);
    const fallback = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (input, init) => {
      if (String(input) === '/api/activity?limit=50&offset=0') return new Response(JSON.stringify({
        status: 'ok', items: [{ activity_id: 'opaque-synth-capture', kind: 'capture', status: 'deleted', occurred_at: '2026-10-23T08:00:00Z' }],
        pagination: { limit: 50, offset: 0, has_more: false }, source: ['capture'], freshness: { checked_at: '2026-10-23T08:00:00Z' },
      }), { status: 200 });
      return fallback(input, init);
    });
    startAt('/activity');

    expect((await screen.findByRole('alert')).textContent).toContain('该页面数据暂不可用');
    expect(screen.queryByText('opaque-synth-capture')).toBeNull();
  });

  it('fails closed when a Capture Activity event includes fields outside its frozen DTO', async () => {
    mockAppFetch();
    const fetchMock = vi.mocked(globalThis.fetch);
    const fallback = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (input, init) => {
      if (String(input) === '/api/activity?limit=50&offset=0') return new Response(JSON.stringify({
        status: 'ok', items: [{ activity_id: 'opaque-synth-capture', kind: 'capture', status: 'completed',
          occurred_at: '2026-10-23T08:00:00Z', project_id: 'synthetic-project' }],
        pagination: { limit: 50, offset: 0, has_more: false }, source: ['capture'], freshness: { checked_at: '2026-10-23T08:00:00Z' },
      }), { status: 200 });
      return fallback(input, init);
    });
    startAt('/activity');

    expect((await screen.findByRole('alert')).textContent).toContain('该页面数据暂不可用');
    expect(screen.queryByText('opaque-synth-capture')).toBeNull();
  });

  it('does not style an unavailable Home Agent as online', async () => {
    mockAppFetch(200, undefined, 200, { agent: { status: 'unavailable', source: 'hermes-runtime' } });
    startAt('/');

    await screen.findByRole('heading', { name: '你的工作台' });
    const statusBadge = document.querySelector('.header-agent') as HTMLElement | null;
    expect(statusBadge).not.toBeNull();
    expect(statusBadge!.textContent).toBe('尚未统计');
    expect(statusBadge!.className).toContain('is-unavailable');
    expect(statusBadge!.className).not.toContain('is-real');
  });

  it('reads a selected historical Daily Brief date without exposing the current-date save form', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'false');
    const calls = mockAppFetch();
    startAt('/brief');
    expect(await screen.findByRole('heading', { name: '每日简报' })).toBeTruthy();
    const date = screen.getByLabelText('选择日期') as HTMLInputElement;
    fireEvent.change(date, { target: { value: '2020-01-02' } });
    await waitFor(() => expect(calls.some((url) => url.includes('date=2020-01-02'))).toBe(true));
    expect(date.value).toBe('2020-01-02');
    expect(screen.getByRole('note').textContent).toContain('历史日期为只读');
    expect(screen.queryByRole('button', { name: '手动准备简报' })).toBeNull();
  });

  it('keeps Journal in an explicit error state when the Core response has no entries array', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'false');
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (String(input) === '/api/auth/session') return new Response('{}', { status: 200 });
      if (/^\/api\/journal\/\d{4}-\d{2}-\d{2}$/.test(String(input))) return new Response(JSON.stringify({ date: '2026-10-23', entries: null }), { status: 200 });
      return new Response('{}', { status: 200 });
    });
    startAt('/journal');
    expect(await screen.findByRole('heading', { name: '日记' })).toBeTruthy();
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.queryByText('当天还没有记录。')).toBeNull();
  });

  it('loads Calendar only for a bounded Shanghai month and never requests bodies or Home', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const calls = mockAppFetch();
    startAt('/calendar');

    expect(await screen.findByRole('heading', { name: '日历' })).toBeTruthy();
    const calendarRequest = calls.find((url) => url.startsWith('/api/calendar?'));
    expect(calendarRequest).toBeTruthy();
    const query = new URLSearchParams(calendarRequest!.split('?')[1]);
    expect(query.get('timezone')).toBe('Asia/Shanghai');
    const from = query.get('from')!;
    const to = query.get('to')!;
    expect(from).toMatch(/^\d{4}-\d{2}-01$/);
    expect(to).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86400000 + 1).toBeLessThanOrEqual(31);
    await screen.findByText('待办');
    expect(document.querySelector(`[data-date="${from}"]`)).toBeTruthy();
    expect(calls).toEqual(['/api/auth/session', calendarRequest]);
    expect(calls.some((url) => /home|tasks|journal\/|sessions|messages|promote|run/i.test(url))).toBe(false);
  });

  it('rejects Calendar events containing body or unknown private fields', async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      calls.push(url);
      if (url === '/api/auth/session') return new Response('{}', { status: 200 });
      if (url.startsWith('/api/calendar?')) {
        const query = new URLSearchParams(url.split('?')[1]);
        return new Response(JSON.stringify({ status: 'ok', items: [{ id: 'opaque-calendar-synth-1', kind: 'journal', date: query.get('from'), body: 'private journal text' }], source: ['journal'], freshness: { checked_at: '2026-10-20T01:30:00Z' } }), { status: 200 });
      }
      return new Response('{}', { status: 200 });
    });
    startAt('/calendar');

    expect((await screen.findByRole('alert')).textContent).toContain('日历数据暂不可用');
    expect(screen.queryByText('private journal text')).toBeNull();
    expect(calls).toHaveLength(2);
    expect(calls.some((url) => /home|tasks|journal\/|sessions|messages/i.test(url))).toBe(false);
  });

  it('loads Projects only from its explicit read endpoint and keeps unconfigured state distinct', async () => {
    const calls = mockAppFetch();
    startAt('/projects');

    expect(await screen.findByRole('heading', { name: '项目' })).toBeTruthy();
    expect(await screen.findByText(/尚未配置可信项目数据源/)).toBeTruthy();
    expect(document.querySelector('[data-fixture-id="SYNTH-PROJECT-001"]')).toBeNull();
    expect(location.pathname).toBe('/projects');
    expect(calls).toEqual(['/api/auth/session', '/api/projects?limit=50&offset=0']);
    fireEvent.click(screen.getByRole('button', { name: '查看本地合成预览' }));
    expect(screen.getByText('LOCAL_CANDIDATE · SYNTHETIC FIXTURE')).toBeTruthy();
    expect(document.querySelector('[data-fixture-id="SYNTH-PROJECT-001"]')).toBeTruthy();
    expect(calls).toEqual(['/api/auth/session', '/api/projects?limit=50&offset=0']);
  });

  it('fails closed when Projects violates its explicitly empty response contract', async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      calls.push(url);
      if (url === '/api/auth/session') return new Response('{}', { status: 200 });
      if (url === '/api/projects?limit=50&offset=0') return new Response(JSON.stringify({ status: 'not_configured', items: [{ title: 'must not render' }], pagination: { limit: 50, offset: 0, has_more: false }, source: null }), { status: 200 });
      return new Response('{}', { status: 200 });
    });
    startAt('/projects');

    expect((await screen.findByRole('alert')).textContent).toContain('该页面数据暂不可用');
    expect(screen.queryByText('must not render')).toBeNull();
    expect(calls).toEqual(['/api/auth/session', '/api/projects?limit=50&offset=0']);
  });

  it('loads Activity from its explicit read endpoint without session/message or Home reads', async () => {
    const calls = mockAppFetch();
    startAt('/activity');

    expect(await screen.findByRole('heading', { name: '动态' })).toBeTruthy();
    expect((await screen.findAllByText('日记操作')).length).toBeGreaterThan(0);
    expect(screen.getByText('已完成')).toBeTruthy();
    expect(calls).toEqual(['/api/auth/session', '/api/activity?limit=50&offset=0']);
    expect(calls.some((url) => /sessions|messages|journal\/|tasks/.test(url))).toBe(false);
  });

  it('loads Activity pages on demand, preserves earlier rows after a page failure, and retries the same page', async () => {
    const calls: string[] = [];
    let laterPageAttempts = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      calls.push(url);
      if (url === '/api/auth/session') return new Response('{}', { status: 200 });
      if (url === '/api/activity?limit=50&offset=0') return new Response(JSON.stringify({
        status: 'partial', items: [{ activity_id: 'activity-page-1', kind: 'journal', status: 'succeeded', occurred_at: '2026-10-20T09:30:00+08:00', journal_date: '2026-10-20' }],
        pagination: { limit: 50, offset: 0, has_more: true }, source: ['journal', 'tasks'], freshness: { checked_at: '2026-10-20T01:30:00Z' },
      }), { status: 200 });
      if (url === '/api/activity?limit=50&offset=50') {
        laterPageAttempts += 1;
        if (laterPageAttempts === 1) return new Response('{}', { status: 503 });
        return new Response(JSON.stringify({
          status: 'ok', items: [{ activity_id: 'activity-page-2', kind: 'task', status: 'failed', occurred_at: '2026-10-19T16:00:00+08:00', task_status: 'open' }],
          pagination: { limit: 50, offset: 50, has_more: true }, source: ['journal', 'tasks'], freshness: { checked_at: '2026-10-20T01:30:01Z' },
        }), { status: 200 });
      }
      if (url === '/api/activity?limit=50&offset=100') return new Response(JSON.stringify({
        status: 'ok', items: [{ activity_id: 'activity-page-3', kind: 'journal', status: 'succeeded', occurred_at: '2026-10-18T09:30:00+08:00', journal_date: '2026-10-18' }],
        pagination: { limit: 50, offset: 100, has_more: false }, source: ['journal', 'tasks'], freshness: { checked_at: '2026-10-20T01:30:02Z' },
      }), { status: 200 });
      return new Response('{}', { status: 404 });
    });
    startAt('/activity');

    expect(await screen.findByRole('heading', { name: '动态' })).toBeTruthy();
    expect((await screen.findAllByText('日记操作')).length).toBeGreaterThan(0);
    expect((await screen.findByRole('status')).textContent).toContain('来源或时间范围不完整');
    fireEvent.click(screen.getByRole('button', { name: '加载更多动态' }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getAllByText('日记操作').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: '加载更多动态' }).hasAttribute('disabled')).toBe(true);
    expect(calls.filter((url) => url === '/api/activity?limit=50&offset=50')).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: '重试加载' }));
    expect((await screen.findAllByText('待办操作')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('日记操作').length).toBeGreaterThan(0);
    expect(calls.filter((url) => url === '/api/activity?limit=50&offset=50')).toHaveLength(2);
    expect(screen.getByRole('button', { name: '加载更多动态' }).hasAttribute('disabled')).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: '加载更多动态' }));
    expect(await screen.findByText('2026-10-18')).toBeTruthy();
    expect(calls.filter((url) => url.startsWith('/api/activity?'))).toEqual([
      '/api/activity?limit=50&offset=0',
      '/api/activity?limit=50&offset=50',
      '/api/activity?limit=50&offset=50',
      '/api/activity?limit=50&offset=100',
    ]);
    expect(screen.queryByRole('button', { name: '加载更多动态' })).toBeNull();
    expect(calls.some((url) => /sessions|messages|journal\/|tasks/.test(url))).toBe(false);
  });

  it('clears previously loaded Activity immediately when permission is revoked during pagination', async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      calls.push(url);
      if (url === '/api/auth/session') return new Response('{}', { status: 200 });
      if (url === '/api/activity?limit=50&offset=0') return new Response(JSON.stringify({
        status: 'ok', items: [{ activity_id: 'activity-before-revocation', kind: 'journal', status: 'succeeded', occurred_at: '2026-10-20T09:30:00+08:00', journal_date: '2026-10-20' }],
        pagination: { limit: 50, offset: 0, has_more: true }, source: ['journal', 'tasks'], freshness: { checked_at: '2026-10-20T01:30:00Z' },
      }), { status: 200 });
      if (url === '/api/activity?limit=50&offset=50') return new Response('{}', { status: 403 });
      return new Response('{}', { status: 404 });
    });
    startAt('/activity');

    expect(await screen.findByRole('heading', { name: '动态' })).toBeTruthy();
    expect((await screen.findAllByText('日记操作')).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: '加载更多动态' }));

    expect((await screen.findByRole('alert')).textContent).toContain('当前账户无权读取此页面数据。');
    expect(screen.queryAllByText('日记操作')).toHaveLength(0);
    expect(screen.queryByRole('button', { name: '加载更多动态' })).toBeNull();
    expect(calls.filter((url) => url.startsWith('/api/activity?'))).toEqual([
      '/api/activity?limit=50&offset=0', '/api/activity?limit=50&offset=50',
    ]);
    expect(calls.some((url) => /sessions|messages|journal\/|tasks/.test(url))).toBe(false);
  });

  it('rejects an Activity response containing Journal or Task body fields', async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      calls.push(url);
      if (url === '/api/auth/session') return new Response('{}', { status: 200 });
      if (url === '/api/activity?limit=50&offset=0') return new Response(JSON.stringify({ status: 'ok', items: [{ activity_id: 'opaque-synth-event-1', kind: 'journal', status: 'succeeded', occurred_at: '2026-10-20T09:30:00+08:00', original_text: 'must not render' }], pagination: { limit: 50, offset: 0, has_more: false }, source: ['journal'], freshness: { checked_at: '2026-10-20T01:30:00Z' } }), { status: 200 });
      return new Response('{}', { status: 200 });
    });
    startAt('/activity');

    expect((await screen.findByRole('alert')).textContent).toContain('该页面数据暂不可用');
    expect(screen.queryByText('must not render')).toBeNull();
    expect(calls).toEqual(['/api/auth/session', '/api/activity?limit=50&offset=0']);
  });

  it('loads Daily Brief only for Shanghai date and never generates or reads source content', async () => {
    const calls = mockAppFetch();
    startAt('/brief');

    expect(await screen.findByRole('heading', { name: '每日简报' })).toBeTruthy();
    expect((await screen.findByRole('status')).textContent).toContain('DAILY_BRIEF_NOT_CONFIGURED');
    const briefRequest = calls.find((url) => url.startsWith('/api/daily-brief?'));
    expect(briefRequest).toMatch(/^\/api\/daily-brief\?date=\d{4}-\d{2}-\d{2}&timezone=Asia%2FShanghai$/);
    expect(calls).toEqual(['/api/auth/session', briefRequest]);
    expect(calls.some((url) => /home|sessions|messages|journal\/|tasks|promote|run/i.test(url))).toBe(false);
  });

  it('marks Daily Brief API absence explicitly instead of generating a fallback', async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      calls.push(url);
      if (url === '/api/auth/session') return new Response('{}', { status: 200 });
      if (url.startsWith('/api/daily-brief?')) return new Response('{}', { status: 404 });
      return new Response('{}', { status: 200 });
    });
    startAt('/brief');

    expect(await screen.findByText(/BACKEND_NOT_IMPLEMENTED/)).toBeTruthy();
    expect(calls).toHaveLength(2);
    expect(calls.every((url) => !/sessions|messages|journal\/|tasks|home|run/i.test(url))).toBe(true);
  });

  it('loads Agent Health from the capability-only endpoint and rejects session/message payloads', async () => {
    const calls = mockAppFetch();
    startAt('/agent-health');

    expect(await screen.findByRole('heading', { name: 'Agent 状态' })).toBeTruthy();
    expect(await screen.findByText('未配置')).toBeTruthy();
    expect(calls).toEqual(['/api/auth/session', '/api/agent/health']);
    expect(calls.some((url) => /home|sessions|messages|runs|journal|tasks/i.test(url))).toBe(false);
  });

  it('fails closed when Agent Health includes session or message data', async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      calls.push(url);
      if (url === '/api/auth/session') return new Response('{}', { status: 200 });
      if (url === '/api/agent/health') return new Response(JSON.stringify({ status: 'online', source: 'hermes-runtime', checked_at: '2026-10-20T01:30:00Z', session_id: 'private-session' }), { status: 200 });
      return new Response('{}', { status: 200 });
    });
    startAt('/agent-health');

    expect((await screen.findByRole('alert')).textContent).toContain('该页面数据暂不可用');
    expect(screen.queryByText('private-session')).toBeNull();
    expect(calls).toEqual(['/api/auth/session', '/api/agent/health']);
  });

  it('rejects an Agent Health status whose source does not match configuration state', async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input); calls.push(url);
      if (url === '/api/auth/session') return new Response('{}', { status: 200 });
      if (url === '/api/agent/health') return new Response(JSON.stringify({ status: 'online', source: null, checked_at: '2026-10-20T01:30:00Z' }), { status: 200 });
      return new Response('{}', { status: 200 });
    });
    startAt('/agent-health');
    expect((await screen.findByRole('alert')).textContent).toContain('该页面数据暂不可用');
    expect(calls).toEqual(['/api/auth/session', '/api/agent/health']);
  });

  it.each(['/chat/blank', '/review'])('does not fetch the Home aggregate after login on direct route %s', async (path) => {
    let authenticated = false;
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push(url);
      if (url === '/api/auth/session') return new Response('{}', { status: authenticated ? 200 : 401 });
      if (url === '/api/auth/login' && init?.method === 'POST') {
        authenticated = true;
        return new Response('{}', { status: 200 });
      }
      if (url === '/api/promote/review/items') return new Response(JSON.stringify({ items: [] }), { status: 200 });
      if (url === '/api/promote/status') return new Response(JSON.stringify({ promote_enabled: false }), { status: 200 });
      if (url === '/api/home') return new Response('{}', { status: 200 });
      return new Response('{}', { status: 200 });
    });
    startAt(path);

    await screen.findByRole('heading', { name: '欢迎回来' });
    fireEvent.change(screen.getByLabelText('SecondBrain 登录口令'), { target: { value: 'synthetic-only-passphrase' } });
    fireEvent.click(screen.getByRole('button', { name: '登录' }));

    if (path === '/chat/blank') {
      expect(await screen.findByRole('heading', { name: '空白验收' })).toBeTruthy();
    } else {
      expect(await screen.findByRole('heading', { name: '待审核' })).toBeTruthy();
      await waitFor(() => expect(calls).toContain('/api/promote/review/items'));
    }
    expect(calls).toContain('/api/auth/login');
    expect(calls.filter((url) => url === '/api/auth/session')).toHaveLength(1);
    expect(calls).not.toContain('/api/home');
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
    expect(calls.filter((url) => url === '/api/home' || url.startsWith('/api/knowledge/') || url.startsWith('/api/promote/'))).toEqual([]);
    expect(calls.some((url) => url.startsWith('/api/knowledge/'))).toBe(false);

    fireEvent.change(screen.getByLabelText('搜索关键词'), { target: { value: 'synthetic' } });
    fireEvent.click(screen.getByRole('button', { name: '搜索' }));
    await waitFor(() => expect(calls.filter((url) => url.startsWith('/api/knowledge/search?'))).toHaveLength(1));
    expect(calls.filter((url) => url === '/api/home' || url.startsWith('/api/promote/'))).toEqual([]);

    fireEvent.click(screen.getByRole('button', { name: '对话' }));
    await waitFor(() => expect(location.pathname).toBe('/chat'));
    expect(calls.filter((url) => url === '/api/home')).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: '首页' }));
    expect(await screen.findByRole('heading', { name: '你的工作台' })).toBeTruthy();
    await waitFor(() => expect(calls.filter((url) => url === '/api/home')).toHaveLength(1));

    fireEvent.click(screen.getByRole('button', { name: '打开导航菜单' }));
    const sidebar = document.querySelector('aside.sidebar') as HTMLElement;
    fireEvent.click(within(sidebar).getByRole('button', { name: '知识库' }));
    expect(location.pathname).toBe('/knowledge');
    expect(await screen.findByRole('heading', { name: '知识库' })).toBeTruthy();
  });

  it('isolates an in-flight Home response when navigating to Knowledge and restores Home loading on return', async () => {
    const calls: string[] = [];
    let finishFirstHome!: (response: Response) => void;
    const firstHome = new Promise<Response>((resolve) => { finishFirstHome = resolve; });
    let homeRequests = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      calls.push(url);
      if (url === '/api/auth/session') return new Response('{}', { status: 200 });
      if (url === '/api/home') {
        homeRequests += 1;
        return homeRequests === 1 ? firstHome : new Response('{}', { status: 200 });
      }
      if (url.startsWith('/api/knowledge/search?')) return new Response(JSON.stringify({ items: [], status: 'ok' }), { status: 200 });
      return new Response('{}', { status: 200 });
    });
    startAt('/');
    await waitFor(() => expect(calls.filter((url) => url === '/api/home')).toHaveLength(1));

    fireEvent.click(screen.getByRole('button', { name: '知识库' }));
    expect(await screen.findByRole('heading', { name: '知识库' })).toBeTruthy();
    expect(calls.filter((url) => url.startsWith('/api/knowledge/') || url.startsWith('/api/promote/'))).toEqual([]);

    await act(async () => {
      finishFirstHome(new Response('{}', { status: 503 }));
      await firstHome;
    });
    fireEvent.click(screen.getByRole('button', { name: '首页' }));
    expect(await screen.findByRole('heading', { name: '你的工作台' })).toBeTruthy();
    await waitFor(() => expect(calls.filter((url) => url === '/api/home')).toHaveLength(2));
    expect(screen.queryByRole('alert')).toBeNull();
    expect(calls.filter((url) => url.startsWith('/api/knowledge/') || url.startsWith('/api/promote/'))).toEqual([]);

    fireEvent.click(screen.getByRole('button', { name: '知识库' }));
    expect(await screen.findByRole('heading', { name: '知识库' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '对话' }));
    await waitFor(() => expect(location.pathname).toBe('/chat'));
    expect(calls.filter((url) => url === '/api/home')).toHaveLength(2);
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

  it('keeps Organizer disabled when an older available response arrives after a newer 403', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    let resolveInitial!: (response: Response) => void;
    const initialStatus = new Promise<Response>((resolve) => { resolveInitial = resolve; });
    let statusRequests = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url === '/api/auth/session') return new Response('{}', { status: 200 });
      if (url === '/api/inbox/summary?limit=100') return new Response(JSON.stringify({ items: [] }), { status: 200 });
      if (url === '/api/automation/organize/status') {
        statusRequests += 1;
        if (statusRequests === 1) return initialStatus;
        return new Response(JSON.stringify({ detail: 'synthetic authorization revoked' }), { status: 403 });
      }
      return new Response('{}', { status: 200 });
    });
    startAt('/inbox');
    fireEvent.click(await screen.findByRole('button', { name: /Capture 待处理/ }));
    await screen.findByText('没有 Capture 条目。');
    fireEvent.click(screen.getByRole('button', { name: '查看自动整理状态' }));
    await waitFor(() => expect(statusRequests).toBe(1));

    await act(async () => { window.dispatchEvent(new Event('sb-inbox-refresh')); });
    await waitFor(() => expect(statusRequests).toBe(2));
    const run = screen.getByRole('button', { name: '立即整理' }) as HTMLButtonElement;
    await waitFor(() => expect(run.disabled).toBe(true));

    await act(async () => { resolveInitial(new Response(JSON.stringify({ execution_available: true, blocked_reason: '' }), { status: 200 })); });
    await waitFor(() => expect(run.disabled).toBe(true));
    expect(screen.getByText('HTTP 403')).toBeTruthy();
    expect((screen.getByRole('button', { name: '立即整理' }) as HTMLButtonElement).disabled).toBe(true);
    expect(vi.mocked(globalThis.fetch).mock.calls.some(([input]) => String(input) === '/api/automation/organize/run')).toBe(false);
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

  it.each([
    ['no_candidates', '整理完成，没有可生成的 Review 草稿。'],
    ['unexpected_status', '整理结果暂无法核验。请先查看 Organizer 状态，不要立即重复执行。'],
  ])('reports Organizer result %s accurately without inventing a draft count', async (status, message) => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/auth/session') return new Response('{}', { status: 200 });
      if (url === '/api/inbox/summary?limit=100') return new Response(JSON.stringify({ items: [] }), { status: 200 });
      if (url === '/api/automation/organize/status') return new Response(JSON.stringify({ execution_available: true, blocked_reason: '' }), { status: 200 });
      if (url === '/api/automation/organize/run' && init?.method === 'POST') return new Response(JSON.stringify({ status }), { status: 200 });
      return new Response('{}', { status: 200 });
    });
    startAt('/inbox');
    fireEvent.click(await screen.findByRole('button', { name: /Capture 待处理/ }));
    await screen.findByText('没有 Capture 条目。');
    fireEvent.click(screen.getByRole('button', { name: '查看自动整理状态' }));
    fireEvent.click(await screen.findByRole('button', { name: '立即整理' }));
    expect(await screen.findByText(message)).toBeTruthy();
    expect(screen.queryByText(/新增 NaN 条 Review 草稿/)).toBeNull();
    expect(screen.queryByText('整理完成，新增 0 条 Review 草稿。')).toBeNull();
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
