import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { V1BriefHealthPage } from './V1BriefHealthPages';
import { DailyBriefApproval } from './DailyBriefApproval';

const checkedAt = '2026-10-20T01:30:00Z';
function currentShanghaiDate(): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date());
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? '';
  return `${part('year')}-${part('month')}-${part('day')}`;
}
function cryptoFor(randomUUID: () => string = () => '11111111-1111-4111-8111-111111111111') {
  return { randomUUID } as unknown as Crypto;
}
const task = {
  id: 'a'.repeat(32), title: 'Synthetic task source', due_date: null, status: 'open',
  created_at: '2026-10-20T01:00:00+00:00', updated_at: '2026-10-20T01:00:00+00:00',
  source: 'web_app_explicit_task', source_ref: { id: 'a'.repeat(32), version: 'a'.repeat(64) },
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
  expect(screen.getByRole('button', { name: '加载 Journal 来源' })).toBeTruthy();
}

describe('Daily Brief explicit approval UI draft', () => {
  afterEach(() => { cleanup(); window.sessionStorage.clear(); vi.unstubAllGlobals(); vi.useRealTimers(); });

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
    expect(screen.getByRole('note').textContent).toContain('暂不支持导入已批准的简报');
    expect(screen.queryByText(/approved_import/i)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '手动准备简报' }));
    expect(await screen.findByRole('checkbox', { name: /Synthetic task source/ })).toBeTruthy();
    expect(screen.getByRole('checkbox', { name: /Synthetic project source/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: '加载 Journal 来源' })).toBeTruthy();
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
    await waitFor(() => expect(screen.getByText('写入已确认，当前回读待核验。')).toBeTruthy());
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

  it('loads Journal only on click, submits the exact Core ref after confirmation, then verifies by GET', async () => {
    vi.stubGlobal('crypto', cryptoFor());
    const sourceDate = currentShanghaiDate();
    const calls: Array<{ path: string; method: string; body?: Record<string, unknown> }> = [];
    const sourceId = `${sourceDate}:${'e'.repeat(64)}`;
    const sourceVersion = 'e'.repeat(64);
    let posted: Record<string, unknown> | null = null;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input); const method = init?.method ?? 'GET';
      const body = typeof init?.body === 'string' ? JSON.parse(init.body) as Record<string, unknown> : undefined;
      calls.push({ path, method, ...(body ? { body } : {}) });
      if (path.startsWith('/api/daily-brief/source-options/journal?')) return Response.json({
        status: 'real', items: [{ kind: 'journal', id: sourceId, date: sourceDate, version: sourceVersion }],
        freshness: { checked_at: checkedAt },
      });
      if (path === '/api/daily-brief' && method === 'POST') {
        posted = body ?? null;
        return Response.json({ status: 'created', brief_id: 'brief_journal_synthetic', date: body?.date,
          timezone: 'Asia/Shanghai', record_version: 'f'.repeat(64), operation_id: `dbi-${'a'.repeat(64)}` }, { status: 201 });
      }
      if (path.startsWith('/api/daily-brief?')) {
        if (!posted) return Response.json(brief('not_configured', sourceDate));
        return Response.json({ status: 'real', items: [{ brief_id: 'brief_journal_synthetic', date: sourceDate,
          timezone: 'Asia/Shanghai', generated_at: checkedAt, generation_status: 'generated', categories: ['Journal 回顾'],
          summary: 'Synthetic Journal brief', source_refs: (posted.source_refs as unknown[]) }],
          source: { kind: 'core-daily-brief-store' }, freshness: { checked_at: checkedAt } });
      }
      return sourceResponse(path);
    }));

    render(<DailyBriefApproval locale="zh-CN" onSaved={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: '手动准备简报' }));
    expect(await screen.findByRole('checkbox', { name: /Synthetic task source/ })).toBeTruthy();
    expect(calls.some((call) => call.path.startsWith('/api/daily-brief/source-options/journal'))).toBe(false);
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: '加载 Journal 来源' }));
    const journalChoice = await screen.findByRole('checkbox', { name: /Journal 来源 1/ });
    expect(calls.filter((call) => call.path.startsWith('/api/daily-brief/source-options/journal'))).toHaveLength(1);
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0);
    fireEvent.click(journalChoice);
    fireEvent.change(screen.getByLabelText(/简报正文/), { target: { value: 'Synthetic Journal brief' } });
    fireEvent.change(screen.getByLabelText('分类（逗号分隔）'), { target: { value: 'Journal 回顾' } });
    fireEvent.click(screen.getByRole('button', { name: '预览并确认' }));
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: '确认并创建简报' }));
    await waitFor(() => expect(screen.getByText('当前简报已核验：Brief 和来源版本与本次提交一致。')).toBeTruthy());

    const post = calls.find((call) => call.method === 'POST');
    expect(post?.body?.source_refs).toEqual([{ kind: 'journal', id: sourceId, version: sourceVersion }]);
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(1);
    expect(calls.some((call) => call.path === `/api/daily-brief?date=${sourceDate}&timezone=Asia%2FShanghai`)).toBe(true);
    expect(screen.queryByText(/Journal 正文/)).toBeNull();
  });

  it('retries readback only after a confirmed receipt whose GET is unavailable', async () => {
    vi.stubGlobal('crypto', cryptoFor());
    let postCount = 0; let getCount = 0;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.startsWith('/api/daily-brief?')) {
        getCount += 1;
        return Response.json({ detail: 'SENSITIVE_SYNTHETIC' }, { status: 503 });
      }
      if (path === '/api/daily-brief' && init?.method === 'POST') {
        postCount += 1; const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        return Response.json({ status: 'created', brief_id: 'brief_readback', date: body.date, timezone: 'Asia/Shanghai',
          record_version: 'c'.repeat(64), operation_id: `dbi-${'d'.repeat(64)}` }, { status: 201 });
      }
      return sourceResponse(path);
    }));
    render(<DailyBriefApproval locale="zh-CN" onSaved={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: '手动准备简报' }));
    expect(await screen.findByRole('checkbox', { name: /Synthetic task source/ })).toBeTruthy();
    fireEvent.click(screen.getByRole('checkbox', { name: /Synthetic task source/ }));
    fireEvent.change(screen.getByLabelText(/简报正文/), { target: { value: 'Synthetic GET retry' } });
    fireEvent.click(screen.getByRole('button', { name: '预览并确认' }));
    fireEvent.click(screen.getByRole('button', { name: '确认并创建简报' }));
    expect(await screen.findByText(/写入已确认，当前回读不可用/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '只读重试当前状态核验' }));
    await waitFor(() => expect(getCount).toBe(2));
    expect(postCount).toBe(1);
    expect(screen.getByText(/写入已确认，当前回读不可用/)).toBeTruthy();
  });

  it('keeps an unknown POST unknown when original-date GET finds identical pre-existing content', async () => {
    const instant = { value: new Date('2026-10-20T15:59:59.000Z') };
    vi.stubGlobal('crypto', cryptoFor());
    const posts: Array<Record<string, unknown>> = [];
    const gets: string[] = [];
    const onSaved = vi.fn();
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.startsWith('/api/daily-brief?')) {
        gets.push(path);
        const body = posts[0];
        // Represents an identical record that may have existed before the lost POST or
        // may have been written concurrently; GET has no trusted operation binding.
        return Response.json({ status: 'real', items: [{ brief_id: 'preexisting_identical_brief', date: body?.date,
          timezone: 'Asia/Shanghai', generated_at: checkedAt, generation_status: 'generated',
          categories: body?.categories, summary: body?.summary, source_refs: body?.source_refs }],
          source: { kind: 'core-daily-brief-store' }, freshness: { checked_at: checkedAt } });
      }
      if (path === '/api/daily-brief' && init?.method === 'POST') {
        posts.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        throw new Error('synthetic response lost');
      }
      return sourceResponse(path);
    }));
    render(<DailyBriefApproval locale="zh-CN" onSaved={onSaved} dateNow={() => new Date(instant.value)} />);
    fireEvent.click(screen.getByRole('button', { name: '手动准备简报' }));
    expect(await screen.findByRole('checkbox', { name: /Synthetic task source/ })).toBeTruthy();
    fireEvent.click(screen.getByRole('checkbox', { name: /Synthetic task source/ }));
    fireEvent.change(screen.getByLabelText(/简报正文/), { target: { value: 'Synthetic midnight recovery' } });
    fireEvent.click(screen.getByRole('button', { name: '预览并确认' }));
    fireEvent.click(screen.getByRole('button', { name: '确认并创建简报' }));
    expect(await screen.findByText(/写入结果未知/)).toBeTruthy();
    expect(posts).toHaveLength(1);
    const exactBody = JSON.stringify(posts[0]);

    instant.value = new Date('2026-10-20T16:00:01.000Z');
    fireEvent.click(screen.getByRole('button', { name: '用同一请求安全重试' }));
    expect(await screen.findByText(/当前可读取到内容与原请求匹配的简报，但无法确认它由原 POST 创建/)).toBeTruthy();
    expect(gets).toEqual(['/api/daily-brief?date=2026-10-20&timezone=Asia%2FShanghai']);
    expect(posts).toHaveLength(1);
    expect(JSON.stringify(posts[0])).toBe(exactBody);
    expect(screen.queryByRole('button', { name: '完成核对' })).toBeNull();
    expect(screen.queryByText(/写入已确认/)).toBeNull();
    expect(onSaved).not.toHaveBeenCalled();
    const stored = JSON.parse(window.sessionStorage.getItem('secondbrain.dailyBrief.pending.v1') ?? 'null');
    expect(stored).toEqual({ body: posts[0], receipt: null });

    fireEvent.click(screen.getByRole('button', { name: '只读核对原日期结果' }));
    await waitFor(() => expect(gets).toHaveLength(2));
    expect(posts).toHaveLength(1);
    expect(JSON.parse(window.sessionStorage.getItem('secondbrain.dailyBrief.pending.v1') ?? 'null')).toEqual({ body: posts[0], receipt: null });
  });

  it('fails closed when the selected Journal version drifts before POST', async () => {
    vi.stubGlobal('crypto', cryptoFor());
    const sourceDate = currentShanghaiDate();
    const posts: Array<Record<string, unknown>> = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.startsWith('/api/daily-brief/source-options/journal?')) return Response.json({
        status: 'real', items: [{ kind: 'journal', id: `${sourceDate}:${'e'.repeat(64)}`, date: sourceDate, version: 'e'.repeat(64) }],
        freshness: { checked_at: checkedAt },
      });
      if (path === '/api/daily-brief' && init?.method === 'POST') {
        posts.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return Response.json({ detail: 'SENSITIVE_SYNTHETIC_SOURCE_VERSION' }, { status: 422 });
      }
      return sourceResponse(path);
    }));
    render(<DailyBriefApproval locale="zh-CN" onSaved={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: '手动准备简报' }));
    await screen.findByRole('checkbox', { name: /Synthetic task source/ });
    fireEvent.click(screen.getByRole('button', { name: '加载 Journal 来源' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: /Journal 来源 1/ }));
    fireEvent.change(screen.getByLabelText(/简报正文/), { target: { value: 'Synthetic source drift' } });
    fireEvent.click(screen.getByRole('button', { name: '预览并确认' }));
    fireEvent.click(screen.getByRole('button', { name: '确认并创建简报' }));
    expect(await screen.findByText(/未通过 Core 校验/)).toBeTruthy();
    expect(screen.queryByRole('checkbox', { name: /Journal 来源 1/ })).toBeNull();
    expect(screen.queryByText(/SENSITIVE_SYNTHETIC_SOURCE_VERSION/)).toBeNull();
    expect(posts).toHaveLength(1);
    expect(posts[0].source_refs).toEqual([{ kind: 'journal', id: `${sourceDate}:${'e'.repeat(64)}`, version: 'e'.repeat(64) }]);
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
    expect(await screen.findByText(/写入结果未知/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '用同一请求安全重试' }));
    expect(await screen.findByText('写入已确认（Core 判定为相同请求的重复回执），当前回读待核验。')).toBeTruthy();
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

  it('uses only the Core-issued Task ID and version as the Brief source reference', async () => {
    const sourceTask = { ...task, title: 'Café 東京 😀', updated_at: '2026-10-20T01:01:02.123456+08:00',
      source_ref: { id: task.id, version: 'f'.repeat(64) } };
    const posts: Array<Record<string, unknown>> = [];
    vi.stubGlobal('crypto', cryptoFor());
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.startsWith('/api/daily-brief?')) return Response.json(brief('not_configured', new URL(`http://test${path}`).searchParams.get('date') ?? ''));
      if (path === '/api/daily-brief' && init?.method === 'POST') {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>; posts.push(body);
        return Response.json({ status: 'created', brief_id: 'brief_core_ref', date: body.date, timezone: 'Asia/Shanghai', record_version: 'c'.repeat(64), operation_id: `dbi-${'d'.repeat(64)}` }, { status: 201 });
      }
      return sourceResponse(path, [sourceTask]);
    }));
    render(<DailyBriefApproval locale="zh-CN" onSaved={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: '手动准备简报' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: /Café 東京/ }));
    fireEvent.change(screen.getByLabelText(/简报正文/), { target: { value: 'Synthetic Core reference' } });
    fireEvent.click(screen.getByRole('button', { name: '预览并确认' }));
    fireEvent.click(screen.getByRole('button', { name: '确认并创建简报' }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect((posts[0].source_refs as Array<{ kind: string; id: string; version: string }>)[0]).toEqual({
      kind: 'task', id: task.id, version: 'f'.repeat(64),
    });
  });

  it('does not offer an older Task candidate without a valid Core-issued source_ref', async () => {
    const unsupportedTask = { ...task, source_ref: undefined };
    vi.stubGlobal('crypto', cryptoFor());
    const calls: string[] = [];
    const posts: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input); calls.push(path);
      if (path.startsWith('/api/daily-brief?')) return Response.json(brief('not_configured', '2026-10-20'));
      if (path === '/api/tasks?status=all') return Response.json({ tasks: [unsupportedTask] });
      if (path === '/api/projects?limit=50&offset=0') return Response.json({ status: 'empty', items: [],
        pagination: { limit: 50, offset: 0, has_more: false }, source: { kind: 'explicit-project-index' }, freshness: { checked_at: checkedAt } });
      if (path === '/api/daily-brief' && init?.method === 'POST') { posts.push(path); return Response.json({}); }
      throw new Error('Unexpected source request');
    }));
    render(<V1BriefHealthPage page="brief" locale="zh-CN" />);
    expect(await screen.findByText(/DAILY_BRIEF_NOT_CONFIGURED/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '手动准备简报' }));
    expect(await screen.findByLabelText(/简报正文/)).toBeTruthy();
    expect(screen.queryByRole('checkbox', { name: /Synthetic task source/ })).toBeNull();
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
    await waitFor(() => expect(screen.getByText('写入已确认，当前回读待核验。')).toBeTruthy());
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
    expect(await screen.findByText(/相同请求的重复回执/)).toBeTruthy();
    expect(posts).toHaveLength(2);
    expect(posts[0]).toEqual(posts[1]);
  });
});
