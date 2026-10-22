import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { TaskPage } from './TaskPage';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const task = {
  id: 'a'.repeat(32), title: '合成任务', due_date: null, status: 'open' as const,
  created_at: '2026-10-17T00:00:00+00:00', updated_at: '2026-10-17T00:00:00+00:00',
  source: 'web_app_explicit_task', original_command: '添加待办：合成任务',
  history: [{ at: '2026-10-17T00:00:00+00:00', event: 'created', changes: { title: '合成任务' } }],
};
const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });

describe('TaskPage', () => {
  it('loads persisted tasks, modifies title/date and completes then reopens with version checks', async () => {
    let current = task;
    const request = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith('/api/tasks?')) {
        const filter = new URLSearchParams(url.split('?')[1]).get('status');
        return ok({ tasks: filter === 'all' || filter === current.status ? [current] : [] });
      }
      if (url.endsWith(`/${task.id}`)) {
        const body = JSON.parse(String(init?.body));
        current = { ...current, ...body, updated_at: `2026-10-17T00:00:0${current.history.length}+00:00`, history: [...current.history, { at: '2026-10-17T00:00:01+00:00', event: 'updated', changes: body }] };
        delete (current as unknown as Record<string, unknown>).expected_updated_at;
        return ok({ task: current });
      }
      return ok({});
    });
    vi.stubGlobal('fetch', request);
    render(<TaskPage locale="zh-CN" />);
    expect(await screen.findByRole('heading', { name: '合成任务' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '编辑' }));
    fireEvent.change(screen.getByLabelText('标题'), { target: { value: '修改的任务' } });
    fireEvent.change(screen.getByLabelText('编辑截止日期'), { target: { value: '2026-10-21' } });
    fireEvent.click(screen.getByRole('button', { name: '保存' }));
    await screen.findByRole('heading', { name: '修改的任务' });
    expect(JSON.parse(request.mock.calls[1][1]?.body as string)).toMatchObject({ title: '修改的任务', due_date: '2026-10-21', expected_updated_at: task.updated_at });
    fireEvent.change(screen.getByLabelText('按截止日期筛选'), { target: { value: '2026-10-21' } });
    await waitFor(() => expect(request.mock.calls.some(([url]) => url === '/api/tasks?status=open&due_date=2026-10-21')).toBe(true));
    fireEvent.click(screen.getByRole('button', { name: '标记完成' }));
    await waitFor(() => expect(request.mock.calls.some(([, init]) => init?.body && JSON.parse(init.body as string).status === 'completed')).toBe(true));
    fireEvent.change(screen.getByLabelText('状态'), { target: { value: 'completed' } });
    expect(await screen.findByText('已完成')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '恢复未完成' }));
    await waitFor(() => expect(current.status).toBe('open'));
    expect(request.mock.calls.some(([, init]) => init?.body && JSON.parse(init.body as string).status === 'open')).toBe(true);
  });

  it('reports unconfigured Task storage instead of showing a fake empty list', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({ detail: 'Task is not enabled' }) }));
    render(<TaskPage locale="zh-CN" />);
    expect((await screen.findByRole('alert')).textContent).toContain('当前环境未启用 Task 存储。');
  });

  it('reads Companion only after explicit expand and evaluates only after explicit click', async () => {
    const request = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith('/api/tasks?')) return ok({ tasks: [] });
      if (url === '/api/companion/preferences' && init?.method === 'PUT') {
        const body = JSON.parse(String(init.body));
        return ok({ event: 'companion.preferences.receipt', version: 1, status: 'saved', revision: 1,
          settings: { enabled: body.enabled, categories: body.categories } });
      }
      if (url === '/api/companion/preferences') return ok({ event: 'companion.preferences', version: 1, revision: 0, enabled: false, categories: [] });
      if (url === '/api/companion/suggestions') return ok({ revision: 0, status: 'disabled', items: [] });
      if (url === '/api/companion/suggestions/evaluate') return ok({ revision: 0, status: 'disabled', items: [] });
      throw new Error(`Unexpected request ${url} ${init?.method ?? 'GET'}`);
    });
    vi.stubGlobal('fetch', request);
    render(<TaskPage locale="zh-CN" />);
    await screen.findByRole('heading', { name: '待办' });
    expect(request.mock.calls.some(([url]) => String(url).startsWith('/api/companion/'))).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: '主动建议' }));
    await screen.findByRole('group', { name: '建议来源' });
    expect(request.mock.calls.some(([url]) => url === '/api/companion/preferences')).toBe(true);
    expect(request.mock.calls.some(([url]) => url === '/api/companion/suggestions/evaluate')).toBe(false);
    fireEvent.click(screen.getByLabelText('启用建议'));
    await waitFor(() => expect(request.mock.calls.some(([url, init]) => url === '/api/companion/preferences' && init?.method === 'PUT')).toBe(true));
    await waitFor(() => expect((screen.getByRole('button', { name: '立即计算' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: '立即计算' }));
    await waitFor(() => expect(request.mock.calls.some(([url]) => url === '/api/companion/suggestions/evaluate')).toBe(true));
    expect(request.mock.calls.find(([url]) => url === '/api/companion/suggestions/evaluate')?.[1]?.body).toBe('{}');
  });

  it('clears the previous filter results when the next Task read fails', async () => {
    const request = vi.fn(async (url: string) => url.endsWith('status=open')
      ? ok({ tasks: [task] })
      : ({ ok: false, status: 503, json: async () => ({ detail: 'Task is temporarily unavailable' }) }));
    vi.stubGlobal('fetch', request);
    render(<TaskPage locale="zh-CN" />);
    expect(await screen.findByRole('heading', { name: '合成任务' })).toBeTruthy();

    fireEvent.change(screen.getByLabelText('状态'), { target: { value: 'completed' } });
    expect(screen.queryByRole('heading', { name: '合成任务' })).toBeNull();
    expect((await screen.findByRole('alert')).textContent).toContain('Task is temporarily unavailable');
    expect(screen.queryByRole('heading', { name: '合成任务' })).toBeNull();
  });

  it('aborts an older filter request and ignores its late Task response', async () => {
    let finishOpen!: (value: ReturnType<typeof ok>) => void;
    let openSignal: AbortSignal | undefined;
    const pendingOpen = new Promise<ReturnType<typeof ok>>((resolve) => { finishOpen = resolve; });
    const completedTask = { ...task, id: 'b'.repeat(32), title: '已完成的合成任务', status: 'completed' as const };
    const request = vi.fn((url: string, init?: RequestInit) => {
      if (url.endsWith('status=open')) { openSignal = init?.signal as AbortSignal; return pendingOpen; }
      return Promise.resolve(ok({ tasks: [completedTask] }));
    });
    vi.stubGlobal('fetch', request);
    render(<TaskPage locale="zh-CN" />);
    await screen.findByLabelText('状态');
    fireEvent.change(screen.getByLabelText('状态'), { target: { value: 'completed' } });

    expect(await screen.findByRole('heading', { name: '已完成的合成任务' })).toBeTruthy();
    expect(openSignal?.aborted).toBe(true);
    await act(async () => { finishOpen(ok({ tasks: [task] })); await pendingOpen; });
    expect(screen.getByRole('heading', { name: '已完成的合成任务' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: '合成任务' })).toBeNull();
  });

  it('opens all Task states and highlights a Task linked from a Daily Brief', async () => {
    window.history.replaceState({}, '', `/today?task_id=${task.id}#task-${task.id}`);
    const request = vi.fn(async (url: string) => {
      expect(url).toBe('/api/tasks?status=all');
      return ok({ tasks: [task] });
    });
    vi.stubGlobal('fetch', request);
    render(<TaskPage locale="zh-CN" />);
    expect(await screen.findByText('此待办被每日简报引用。')).toBeTruthy();
    expect(document.getElementById(`task-${task.id}`)).toBeTruthy();
  });

  it('creates a Task through Core and verifies it with a read-only list refresh', async () => {
    const created = { ...task, id: 'c'.repeat(32), title: '新建的合成待办', due_date: '2026-10-25', original_command: 'Task page explicit create' };
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'task-create-key-1') });
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input); calls.push({ url, init });
      if (url.startsWith('/api/tasks?')) return ok({ tasks: calls.some((call) => call.url === '/api/tasks' && call.init?.method === 'POST') ? [created] : [] });
      if (url === '/api/tasks' && init?.method === 'POST') return ok({ status: 'created', task: created });
      return ok({});
    }));
    render(<TaskPage locale="zh-CN" />);
    await screen.findByRole('heading', { name: '待办' });
    fireEvent.change(screen.getByLabelText('待办内容'), { target: { value: '新建的合成待办' } });
    fireEvent.change(screen.getByLabelText('新待办截止日期'), { target: { value: '2026-10-25' } });
    fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    expect(await screen.findByRole('heading', { name: '新建的合成待办' })).toBeTruthy();
    expect(await screen.findByText('待办已创建并在已保存列表中核对。')).toBeTruthy();
    const post = calls.find((call) => call.url === '/api/tasks' && call.init?.method === 'POST');
    expect(JSON.parse(String(post?.init?.body))).toEqual({ title: '新建的合成待办', due_date: '2026-10-25', original_command: 'Task page explicit create' });
    expect(new Headers(post?.init?.headers).get('Idempotency-Key')).toBe('task-create-key-1');
    expect(calls.filter((call) => call.url.startsWith('/api/tasks?'))).toHaveLength(2);
  });

  it('clears a filter that would hide a newly created open Task and verifies it in the visible list', async () => {
    const created = { ...task, id: 'e'.repeat(32), title: '筛选后仍可见的合成待办', original_command: 'Task page explicit create' };
    let posts = 0;
    const reads: string[] = [];
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'task-filter-key') });
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input); reads.push(url);
      if (url.startsWith('/api/tasks?')) return ok({ tasks: posts && url.endsWith('status=open') ? [created] : [] });
      if (url === '/api/tasks' && init?.method === 'POST') { posts += 1; return ok({ status: 'created', task: created }); }
      return ok({});
    }));
    render(<TaskPage locale="zh-CN" />);
    await screen.findByRole('heading', { name: '待办' });
    fireEvent.change(screen.getByLabelText('状态'), { target: { value: 'completed' } });
    await screen.findByText('此视图中暂无待办。');
    fireEvent.change(screen.getByLabelText('待办内容'), { target: { value: created.title } });
    fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    expect(await screen.findByRole('heading', { name: created.title })).toBeTruthy();
    expect(await screen.findByText('待办已创建并核对成功；已清除筛选条件以显示这条记录。')).toBeTruthy();
    expect((screen.getByLabelText('状态') as HTMLSelectElement).value).toBe('open');
    expect(reads).toContain('/api/tasks?status=open');
  });

  it('reports list-readback failure separately after Core has confirmed Task creation', async () => {
    let created = false;
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'task-readback-key') });
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.startsWith('/api/tasks?')) {
        return created ? { ok: false, status: 503, json: async () => ({ detail: 'Synthetic list unavailable' }) } : ok({ tasks: [] });
      }
      if (url === '/api/tasks' && init?.method === 'POST') { created = true; return ok({ status: 'created', task: { ...task, id: 'f'.repeat(32), title: 'Core 已创建但暂不可回读' } }); }
      return ok({});
    }));
    render(<TaskPage locale="zh-CN" />);
    await screen.findByRole('heading', { name: '待办' });
    fireEvent.change(screen.getByLabelText('待办内容'), { target: { value: 'Core 已创建但暂不可回读' } });
    fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    expect(await screen.findByText('Core 已确认创建成功，但列表暂时无法核对；请刷新列表查看。')).toBeTruthy();
    expect((await screen.findByRole('alert')).textContent).toContain('Synthetic list unavailable');
    expect((screen.getByLabelText('待办内容') as HTMLInputElement).value).toBe('');
  });

  it('reuses the exact idempotency key after a lost Task creation response', async () => {
    const created = { ...task, id: 'd'.repeat(32), title: '可安全重试的合成待办', original_command: 'Task page explicit create' };
    const keys: string[] = [];
    let posts = 0;
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'task-create-retry-key') });
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.startsWith('/api/tasks?')) return ok({ tasks: posts > 1 ? [created] : [] });
      if (url === '/api/tasks' && init?.method === 'POST') {
        posts += 1; keys.push(new Headers(init.headers).get('Idempotency-Key') ?? '');
        if (posts === 1) throw new TypeError('synthetic response lost');
        return ok({ status: 'duplicate', task: created });
      }
      return ok({});
    }));
    render(<TaskPage locale="zh-CN" />);
    await screen.findByRole('heading', { name: '待办' });
    fireEvent.change(screen.getByLabelText('待办内容'), { target: { value: '可安全重试的合成待办' } });
    fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    expect((await screen.findByRole('alert')).textContent).toContain('synthetic response lost');
    expect((screen.getByLabelText('待办内容') as HTMLInputElement).value).toBe('可安全重试的合成待办');
    fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    expect(await screen.findByRole('heading', { name: '可安全重试的合成待办' })).toBeTruthy();
    expect(keys).toEqual(['task-create-retry-key', 'task-create-retry-key']);
  });
});
