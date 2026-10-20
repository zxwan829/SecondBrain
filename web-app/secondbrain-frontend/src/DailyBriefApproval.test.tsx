import React from 'react';
// @ts-expect-error Node's Web Crypto is used only by this Vitest test, not shipped in the browser bundle.
import { webcrypto } from 'node:crypto';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { V1BriefHealthPage } from './V1BriefHealthPages';
import { DailyBriefApproval } from './DailyBriefApproval';

const checkedAt = '2026-10-20T01:30:00Z';
function cryptoFor(randomUUID: () => string = () => '11111111-1111-4111-8111-111111111111') {
  return { subtle: webcrypto.subtle, randomUUID } as unknown as Crypto;
}
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

function sourceResponse(path: string, tasks: Array<Record<string, unknown>> = [task]) {
  if (path === '/api/tasks?status=all') return Response.json({ tasks });
  if (path === '/api/projects?limit=50&offset=0') return Response.json({ status: 'real', items: [project],
    pagination: { limit: 50, offset: 0, has_more: false }, source: { kind: 'explicit-project-index' }, freshness: { checked_at: checkedAt } });
  throw new Error(`Unexpected source request: ${path}`);
}

async function openComposer(tasks: Array<Record<string, unknown>> = [task]) {
  render(<V1BriefHealthPage page="brief" locale="zh-CN" />);
  expect(await screen.findByText(/DAILY_BRIEF_NOT_CONFIGURED/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '手动准备简报' }));
  if (tasks.length) expect(await screen.findByRole('checkbox', { name: new RegExp(String(tasks[0].title ?? '')) })).toBeTruthy();
  expect(screen.getByRole('checkbox', { name: /Synthetic project source/ })).toBeTruthy();
  expect(screen.getByText(/Journal 来源暂不可选/)).toBeTruthy();
}

describe('Daily Brief explicit approval UI draft', () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

  it('does not load source lists or POST on page load; waits for explicit review and confirmation', async () => {
    const randomUUID = vi.fn(() => '11111111-1111-4111-8111-111111111111');
    vi.stubGlobal('crypto', cryptoFor(randomUUID));
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

    render(<V1BriefHealthPage page="brief" locale="zh-CN" />);
    expect(await screen.findByText(/DAILY_BRIEF_NOT_CONFIGURED/)).toBeTruthy();
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0);
    expect(calls.some((call) => call.path.startsWith('/api/tasks') || call.path.startsWith('/api/projects'))).toBe(false);
    expect(screen.queryByText(/approved_import|导入已批准简报/i)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '手动准备简报' }));
    expect(await screen.findByRole('checkbox', { name: /Synthetic task source/ })).toBeTruthy();
    expect(screen.getByRole('checkbox', { name: /Synthetic project source/ })).toBeTruthy();
    expect(screen.getByText(/Journal 来源暂不可选/)).toBeTruthy();
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
    expect(posts[0].body?.idempotency_key).toBe('ui-11111111-1111-4111-8111-111111111111');
    expect(randomUUID).toHaveBeenCalledTimes(1);
    expect(posts[0].body?.source_refs).toHaveLength(2);
    expect(new Set((posts[0].body?.source_refs as Array<{kind:string}>).map((ref) => ref.kind))).toEqual(new Set(['task', 'project']));
    expect(Object.keys(posts[0].body ?? {}).sort()).toEqual(['approved', 'categories', 'date', 'idempotency_key', 'mode', 'source_refs', 'summary', 'timezone'].sort());
    expect(await screen.findByText('SYNTHETIC APPROVED BRIEF')).toBeTruthy();
  });

  it('retries an unknown transport result with identical key and body', async () => {
    vi.stubGlobal('crypto', cryptoFor());
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
    vi.stubGlobal('crypto', cryptoFor());
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.startsWith('/api/daily-brief?')) return Response.json(brief('not_configured', '2026-10-20'));
      if (path.startsWith('/api/daily-brief') && init?.method === 'POST') return Response.json({ detail: 'SENSITIVE_SYNTHETIC_DIAGNOSTIC' }, { status: 409 });
      return sourceResponse(path);
    }));
    await openComposer();
    fireEvent.click(screen.getByRole('checkbox', { name: /Task.*Synthetic task source/ }));
    fireEvent.change(screen.getByLabelText(/简报正文/), { target: { value: 'Synthetic conflict text' } });
    fireEvent.click(screen.getByRole('button', { name: '预览并确认' }));
    fireEvent.click(screen.getByRole('button', { name: '确认并创建简报' }));
    expect(await screen.findByText(/Core 检测到同日或同幂等键冲突/)).toBeTruthy();
    expect(screen.queryByText(/SENSITIVE_SYNTHETIC_DIAGNOSTIC/)).toBeNull();
    expect(screen.queryByRole('button', { name: '用同一请求安全重试' })).toBeNull();
  });

  it('matches Core task_source_version for Unicode, dates, field ordering, and updated versions', async () => {
    const variants = [
      { id: 'a'.repeat(32), title: 'Café 東京 😀 - "Daily"', due_date: '2026-10-21', status: 'open', created_at: '2026-10-20T01:00:00.123456+00:00', updated_at: '2026-10-20T01:01:02.123456+08:00', source: 'web_app_explicit_task' },
      { source: 'web_app_explicit_task', updated_at: '2026-10-20T01:01:03.123456+08:00', title: 'Café 東京 😀 - "Daily"', status: 'open', created_at: '2026-10-20T01:00:00.123456+00:00', id: 'a'.repeat(32), due_date: '2026-10-21' },
    ];
    const expected = [
      '69f9cca6aec30b645f23b302ae92425945bfa53e6b190672d9a18e5b07b64c3c',
      '9ea3fef0a8083a5d2d0366882d3dc7de9f2259147ebabce6fcdc65ecf81e8e5f',
    ];
    for (const [index, sourceTask] of variants.entries()) {
      cleanup();
      vi.stubGlobal('crypto', cryptoFor());
      const posts: Array<Record<string, unknown>> = [];
      vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path.startsWith('/api/daily-brief?')) return Response.json(brief('not_configured', new URL(`http://test${path}`).searchParams.get('date') ?? ''));
        if (path === '/api/daily-brief' && init?.method === 'POST') {
          const body = JSON.parse(String(init.body)) as Record<string, unknown>; posts.push(body);
          return Response.json({ status: 'created', brief_id: 'brief_hash_vector', date: body.date, timezone: 'Asia/Shanghai', record_version: 'c'.repeat(64), operation_id: `dbi-${'d'.repeat(64)}` }, { status: 201 });
        }
        return sourceResponse(path, [sourceTask]);
      }));
      await openComposer([sourceTask]);
      fireEvent.click(screen.getByRole('checkbox', { name: /Café 東京/ }));
      fireEvent.change(screen.getByLabelText(/简报正文/), { target: { value: 'Synthetic hash vector' } });
      fireEvent.click(screen.getByRole('button', { name: '预览并确认' }));
      fireEvent.click(screen.getByRole('button', { name: '确认并创建简报' }));
      await waitFor(() => expect(posts).toHaveLength(1));
      expect((posts[0].source_refs as Array<{ kind: string; id: string; version: string }>)[0]).toEqual({
        kind: 'task', id: 'a'.repeat(32), version: expected[index],
      });
    }
  });

  it.each([
    ['invalid due date', { due_date: '2026-02-30' }],
    ['invalid timestamp', { updated_at: '2026-10-20T25:00:00+00:00' }],
    ['missing canonical field', { source: undefined }],
  ])('fails closed when a Task source has %s', async (_caseName, patch) => {
    const invalidTask = { ...task, ...patch };
    vi.stubGlobal('crypto', cryptoFor());
    const calls: string[] = [];
    const posts: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input); calls.push(path);
      if (path.startsWith('/api/daily-brief?')) return Response.json(brief('not_configured', '2026-10-20'));
      if (path === '/api/tasks?status=all') return Response.json({ tasks: [invalidTask] });
      if (path === '/api/projects?limit=50&offset=0') return Response.json({ status: 'empty', items: [],
        pagination: { limit: 50, offset: 0, has_more: false }, source: { kind: 'explicit-project-index' }, freshness: { checked_at: checkedAt } });
      if (path === '/api/daily-brief' && init?.method === 'POST') { posts.push(path); return Response.json({}); }
      throw new Error('Unexpected source request');
    }));
    render(<V1BriefHealthPage page="brief" locale="zh-CN" />);
    expect(await screen.findByText(/DAILY_BRIEF_NOT_CONFIGURED/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '手动准备简报' }));
    expect((await screen.findByRole('alert')).textContent).toMatch(/来源读取失败/);
    expect(screen.queryByRole('checkbox')).toBeNull();
    expect(posts).toHaveLength(0);
  });

  it('rechecks Asia/Shanghai date at final confirmation and requires a new review after midnight', async () => {
    const initialDate = '2026-10-20';
    let instant = new Date('2026-10-20T15:59:59.000Z');
    vi.stubGlobal('crypto', cryptoFor());
    const posts: Array<Record<string, unknown>> = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.startsWith('/api/daily-brief?')) return Response.json(brief('not_configured', new URL(`http://test${path}`).searchParams.get('date') ?? ''));
      if (path === '/api/daily-brief' && init?.method === 'POST') {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>; posts.push(body);
        return Response.json({ status: 'created', brief_id: 'brief_rollover', date: body.date, timezone: 'Asia/Shanghai', record_version: 'c'.repeat(64), operation_id: `dbi-${'d'.repeat(64)}` }, { status: 201 });
      }
      return sourceResponse(path);
    }));
    render(<DailyBriefApproval locale="zh-CN" onSaved={() => {}} dateNow={() => new Date(instant)} />);
    fireEvent.click(screen.getByRole('button', { name: '手动准备简报' }));
    expect(await screen.findByRole('checkbox', { name: /Synthetic task source/ })).toBeTruthy();
    fireEvent.click(screen.getByRole('checkbox', { name: /Synthetic task source/ }));
    fireEvent.change(screen.getByLabelText(/简报正文/), { target: { value: 'Synthetic rollover content' } });
    fireEvent.click(screen.getByRole('button', { name: '预览并确认' }));
    expect(screen.getByText(`业务日期：${initialDate}`)).toBeTruthy();

    const nextDate = '2026-10-21';
    instant = new Date('2026-10-20T16:00:01.000Z');
    fireEvent.click(screen.getByRole('button', { name: '确认并创建简报' }));
    expect(await screen.findByText(/上海日期已变化/)).toBeTruthy();
    expect(screen.getByText(`业务日期：${nextDate}`)).toBeTruthy();
    expect(posts).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: '预览并确认' }));
    fireEvent.click(screen.getByRole('button', { name: '确认并创建简报' }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].date).toBe(nextDate);
  });

  it.each([401, 403, 422, 503])('shows a sanitized safe message for HTTP %i without exposing response details', async (status) => {
    vi.stubGlobal('crypto', cryptoFor());
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.startsWith('/api/daily-brief?')) return Response.json(brief('not_configured', '2026-10-20'));
      if (path === '/api/daily-brief' && init?.method === 'POST') return Response.json({ detail: 'SENSITIVE_SYNTHETIC_DIAGNOSTIC' }, { status });
      return sourceResponse(path);
    }));
    await openComposer();
    fireEvent.click(screen.getByRole('checkbox', { name: /Synthetic task source/ }));
    fireEvent.change(screen.getByLabelText(/简报正文/), { target: { value: 'Synthetic error case' } });
    fireEvent.click(screen.getByRole('button', { name: '预览并确认' }));
    fireEvent.click(screen.getByRole('button', { name: '确认并创建简报' }));
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).not.toContain('SENSITIVE_SYNTHETIC_DIAGNOSTIC');
    expect(alert.textContent).toMatch(status === 401 || status === 403 ? /登录或写入权限/ : status === 422 ? /未通过 Core 校验/ : /暂不可用/);
    if (status === 503) expect(screen.getByRole('button', { name: '用同一请求安全重试' })).toBeTruthy();
  });

  it('prevents duplicate submits from rapid confirm clicks', async () => {
    vi.stubGlobal('crypto', cryptoFor());
    let resolvePost: ((response: Response) => void) | undefined;
    const posts: Array<Record<string, unknown>> = [];
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.startsWith('/api/daily-brief?')) return Promise.resolve(Response.json(brief('not_configured', new URL(`http://test${path}`).searchParams.get('date') ?? '')));
      if (path === '/api/daily-brief' && init?.method === 'POST') {
        posts.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return new Promise<Response>((resolve) => { resolvePost = resolve; });
      }
      return Promise.resolve(sourceResponse(path));
    }));
    await openComposer();
    fireEvent.click(screen.getByRole('checkbox', { name: /Synthetic task source/ }));
    fireEvent.change(screen.getByLabelText(/简报正文/), { target: { value: 'Synthetic double-click' } });
    fireEvent.click(screen.getByRole('button', { name: '预览并确认' }));
    const confirm = screen.getByRole('button', { name: '确认并创建简报' });
    fireEvent.click(confirm); fireEvent.click(confirm);
    expect(posts).toHaveLength(1);
    const body = posts[0];
    resolvePost?.(Response.json({ status: 'created', brief_id: 'brief_double', date: body.date, timezone: 'Asia/Shanghai', record_version: 'c'.repeat(64), operation_id: `dbi-${'d'.repeat(64)}` }, { status: 201 }));
    await waitFor(() => expect(screen.getByText('简报已保存。正在重新读取 Core 当前状态。')).toBeTruthy());
  });

  it('preserves the exact POST body and idempotency key after a sanitized 503 retry', async () => {
    vi.stubGlobal('crypto', cryptoFor());
    const posts: Array<{ body: Record<string, unknown> }> = [];
    let postCount = 0;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.startsWith('/api/daily-brief?')) return Response.json(brief('not_configured', new URL(`http://test${path}`).searchParams.get('date') ?? ''));
      if (path === '/api/daily-brief' && init?.method === 'POST') {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>; posts.push({ body }); postCount += 1;
        if (postCount === 1) return Response.json({ detail: 'SENSITIVE_SYNTHETIC_DIAGNOSTIC' }, { status: 503 });
        return Response.json({ status: 'duplicate', brief_id: 'brief_retry_503', date: body.date, timezone: 'Asia/Shanghai', record_version: 'c'.repeat(64), operation_id: `dbi-${'d'.repeat(64)}` }, { status: 200 });
      }
      return sourceResponse(path);
    }));
    await openComposer();
    fireEvent.click(screen.getByRole('checkbox', { name: /Synthetic task source/ }));
    fireEvent.change(screen.getByLabelText(/简报正文/), { target: { value: 'Synthetic 503 retry' } });
    fireEvent.click(screen.getByRole('button', { name: '预览并确认' }));
    fireEvent.click(screen.getByRole('button', { name: '确认并创建简报' }));
    expect(await screen.findByText(/Core 暂不可用/)).toBeTruthy();
    expect(screen.queryByText(/SENSITIVE_SYNTHETIC_DIAGNOSTIC/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '用同一请求安全重试' }));
    expect(await screen.findByText(/此前已保存/)).toBeTruthy();
    expect(posts).toHaveLength(2);
    expect(posts[0]).toEqual(posts[1]);
  });
});
