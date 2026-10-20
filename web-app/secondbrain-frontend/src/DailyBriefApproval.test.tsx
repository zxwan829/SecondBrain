import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { V1BriefHealthPage } from './V1BriefHealthPages';

const checkedAt = '2026-10-20T01:30:00Z';
const cryptoMock = { subtle: { digest: async () => new Uint8Array(32).buffer }, randomUUID: () => '11111111-1111-4111-8111-111111111111' } as unknown as Crypto;
const task = {
  id: 'a'.repeat(32), title: 'Synthetic task source', due_date: null, status: 'open',
  created_at: '2026-10-20T01:00:00+00:00', updated_at: '2026-10-20T01:00:00+00:00',
  source: 'web_app_explicit_task',
};
const project = { id: 'project_synthetic_1', title: 'Synthetic project source', status: 'active',
  source_ref: { id: 'project_synthetic_1', version: 'b'.repeat(64) } };

function brief(status: 'not_configured' | 'real', date: string, body?: Record<string, unknown>) {
  return {
    status, items: status === 'real' ? [{ brief_id: 'brief_ui_synthetic', date, timezone: 'Asia/Shanghai', generated_at: checkedAt,
      generation_status: 'generated', categories: ['今日任务'], summary: 'SYNTHETIC APPROVED BRIEF',
      source_refs: body?.source_refs ?? [] }] : [],
    source: status === 'not_configured' ? null : { kind: 'core-daily-brief-store' },
    freshness: { checked_at: checkedAt },
  };
}

function sourceResponse(path: string) {
  if (path === '/api/tasks?status=all') return Response.json({ tasks: [task] });
  if (path === '/api/projects?limit=50&offset=0') return Response.json({ status: 'real', items: [project],
    pagination: { limit: 50, offset: 0, has_more: false }, source: { kind: 'explicit-project-index' }, freshness: { checked_at: checkedAt } });
  throw new Error(`Unexpected source request: ${path}`);
}

async function openComposer() {
  render(<V1BriefHealthPage page="brief" locale="zh-CN" />);
  expect(await screen.findByText(/DAILY_BRIEF_NOT_CONFIGURED/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '手动准备简报' }));
  expect(await screen.findByRole('checkbox', { name: /Synthetic task source/ })).toBeTruthy();
  expect(screen.getByRole('checkbox', { name: /Synthetic project source/ })).toBeTruthy();
  expect(screen.getByText(/Journal 来源暂不可选/)).toBeTruthy();
}

describe('Daily Brief explicit approval UI draft', () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it('does not load source lists or POST on page load; waits for explicit review and confirmation', async () => {
    vi.stubGlobal('crypto', cryptoMock);
    const calls: Array<{ path: string; method: string; body?: Record<string, unknown> }> = [];
    let saved = false;
    let savedBody: Record<string, unknown> | undefined;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input); const method = init?.method ?? 'GET';
      calls.push({ path, method, ...(typeof init?.body === 'string' ? { body: JSON.parse(init.body) as Record<string, unknown> } : {}) });
      if (path.startsWith('/api/daily-brief?')) return Response.json(brief(saved ? 'real' : 'not_configured', new URL(`http://test${path}`).searchParams.get('date') ?? '', savedBody));
      if (path.startsWith('/api/daily-brief') && method === 'POST') { saved = true; savedBody = calls.at(-1)?.body; return Response.json({ status: 'created', brief_id: 'brief_ui_synthetic', date: calls.at(-1)?.body?.date, timezone: 'Asia/Shanghai', record_version: 'c'.repeat(64), operation_id: `dbi-${'d'.repeat(64)}` }, { status: 201 }); }
      return sourceResponse(path);
    }));

    await openComposer();
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0);
    expect(calls.filter((call) => call.path === '/api/tasks?status=all')).toHaveLength(1);
    expect(calls.filter((call) => call.path === '/api/projects?limit=50&offset=0')).toHaveLength(1);
    expect(screen.queryByText('project_synthetic_1')).toBeNull();

    fireEvent.click(screen.getByRole('checkbox', { name: /Task.*Synthetic task source/ }));
    fireEvent.click(screen.getByRole('checkbox', { name: /Project.*Synthetic project source/ }));
    fireEvent.change(screen.getByLabelText(/简报正文/), { target: { value: 'Synthetic user-approved text' } });
    fireEvent.change(screen.getByLabelText('分类（逗号分隔）'), { target: { value: '今日任务' } });
    fireEvent.click(screen.getByRole('button', { name: '预览并确认' }));
    expect(screen.getByText('确认要保存这份简报？')).toBeTruthy();
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: '确认并创建简报' }));
    await waitFor(() => expect(screen.getByText('简报已保存。正在重新读取 Core 当前状态。')).toBeTruthy());
    const posts = calls.filter((call) => call.method === 'POST');
    expect(posts).toHaveLength(1);
    expect(posts[0].path).toBe('/api/daily-brief');
    expect(posts[0].body).toMatchObject({ mode: 'manual_generate', timezone: 'Asia/Shanghai', categories: ['今日任务'], summary: 'Synthetic user-approved text', approved: true });
    expect(posts[0].body?.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(posts[0].body?.idempotency_key).toMatch(/^ui-[0-9a-f-]{36}$/);
    expect(posts[0].body?.source_refs).toHaveLength(2);
    expect(new Set((posts[0].body?.source_refs as Array<{kind:string}>).map((ref) => ref.kind))).toEqual(new Set(['task', 'project']));
    expect(Object.keys(posts[0].body ?? {}).sort()).toEqual(['approved', 'categories', 'date', 'idempotency_key', 'mode', 'source_refs', 'summary', 'timezone'].sort());
    expect(await screen.findByText('SYNTHETIC APPROVED BRIEF')).toBeTruthy();
  });

  it('retries an unknown transport result with identical key and body', async () => {
    vi.stubGlobal('crypto', cryptoMock);
    const posts: Array<{ path: string; body: Record<string, unknown> }> = [];
    let postCount = 0;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.startsWith('/api/daily-brief?')) return Response.json(brief('not_configured', new URL(`http://test${path}`).searchParams.get('date') ?? ''));
      if (path.startsWith('/api/daily-brief') && init?.method === 'POST') {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>; posts.push({ path, body }); postCount += 1;
        if (postCount === 1) throw new Error('synthetic response lost');
        return Response.json({ status: 'duplicate', brief_id: 'brief_ui_synthetic', date: body.date, timezone: 'Asia/Shanghai', record_version: 'c'.repeat(64), operation_id: `dbi-${'d'.repeat(64)}` }, { status: 200 });
      }
      return sourceResponse(path);
    }));
    await openComposer();
    fireEvent.click(screen.getByRole('checkbox', { name: /Task.*Synthetic task source/ }));
    fireEvent.change(screen.getByLabelText(/简报正文/), { target: { value: 'Synthetic retry text' } });
    fireEvent.click(screen.getByRole('button', { name: '预览并确认' }));
    fireEvent.click(screen.getByRole('button', { name: '确认并创建简报' }));
    expect(await screen.findByText(/无法确认保存结果/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '用同一请求安全重试' }));
    expect(await screen.findByText('这项操作此前已保存；没有创建第二条简报。')).toBeTruthy();
    expect(posts).toHaveLength(2);
    expect(posts[0]).toEqual(posts[1]);
  });

  it('fails closed on a same-day conflict and offers no new-key retry', async () => {
    vi.stubGlobal('crypto', cryptoMock);
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.startsWith('/api/daily-brief?')) return Response.json(brief('not_configured', '2026-10-20'));
      if (path.startsWith('/api/daily-brief') && init?.method === 'POST') return Response.json({ detail: 'Daily Brief conflict' }, { status: 409 });
      return sourceResponse(path);
    }));
    await openComposer();
    fireEvent.click(screen.getByRole('checkbox', { name: /Task.*Synthetic task source/ }));
    fireEvent.change(screen.getByLabelText(/简报正文/), { target: { value: 'Synthetic conflict text' } });
    fireEvent.click(screen.getByRole('button', { name: '预览并确认' }));
    fireEvent.click(screen.getByRole('button', { name: '确认并创建简报' }));
    expect(await screen.findByText(/Core 检测到同日或同幂等键冲突/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: '用同一请求安全重试' })).toBeNull();
  });
});
