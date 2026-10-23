import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { TaskPage } from './TaskPage';

afterEach(() => { cleanup(); window.sessionStorage.clear(); window.history.replaceState({}, '', '/'); vi.unstubAllGlobals(); });

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

  it('loads Companion only after explicit expansion and evaluates only after explicit click', async () => {
    const request = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith('/api/tasks?')) return ok({ tasks: [] });
      if (url === '/api/companion/preferences' && init?.method === 'PUT') {
        const body = JSON.parse(String(init.body));
        return ok({ event: 'companion.preferences.receipt', version: 1, status: 'saved', revision: 1,
          settings: { enabled: body.enabled, categories: body.categories } });
      }
      if (url === '/api/companion/preferences') return ok({ event: 'companion.preferences', version: 1, revision: 0, enabled: false, categories: [] });
      if (url === '/api/companion/suggestions' || url === '/api/companion/suggestions/evaluate') return ok({ revision: 0, status: 'disabled', items: [] });
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

  it('creates a task from Today and safely retries an ambiguous response with the same key', async () => {
    const created = { ...task, id: 'c'.repeat(32), title: '直接新建的任务', due_date: '2026-10-24', status: 'open' as const };
    let posts = 0;
    let stored: typeof created | null = null;
    const request = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith('/api/tasks?')) return ok({ tasks: stored ? [stored] : [] });
      if (url === '/api/tasks' && init?.method === 'POST') {
        posts += 1;
        const body = JSON.parse(String(init.body));
        expect(body).toEqual({ title: '直接新建的任务', due_date: '2026-10-24', original_command: 'Task page explicit create' });
        stored = created;
        if (posts === 1) return { ok: false, status: 500, json: async () => ({ detail: 'response lost after commit' }) };
        return ok({ status: 'duplicate', task: stored });
      }
      return ok({});
    });
    vi.stubGlobal('fetch', request);
    render(<TaskPage locale="zh-CN" />);
    await screen.findByText('此视图中暂无待办。');
    fireEvent.click(screen.getByRole('button', { name: '新建待办' }));
    fireEvent.change(screen.getByLabelText('待办内容'), { target: { value: '直接新建的任务' } });
    fireEvent.change(screen.getByLabelText('新待办截止日期'), { target: { value: '2026-10-24' } });
    fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    expect((await screen.findByRole('alert')).textContent).toContain('response lost after commit');
    expect((screen.getByLabelText('待办内容') as HTMLInputElement).value).toBe('直接新建的任务');
    fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    expect(await screen.findByRole('heading', { name: '直接新建的任务' })).toBeTruthy();
    expect(posts).toBe(2);
    const postCalls = request.mock.calls.filter(([url, init]) => url === '/api/tasks' && init?.method === 'POST');
    expect(new Headers(postCalls[0][1]?.headers).get('Idempotency-Key')).toBeTruthy();
    expect(new Headers(postCalls[1][1]?.headers).get('Idempotency-Key')).toBe(new Headers(postCalls[0][1]?.headers).get('Idempotency-Key'));
    expect(await screen.findByRole('status')).toBeTruthy();
  });

  it('uses a new key after cancelling an ambiguous create and reopening with identical content', async () => {
    const second = { ...task, id: 'd'.repeat(32), title: '重复内容', due_date: null };
    let posts = 0;
    const keys: string[] = [];
    const request = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith('/api/tasks?')) return ok({ tasks: posts > 1 ? [second] : [] });
      if (url === '/api/tasks' && init?.method === 'POST') {
        posts += 1;
        keys.push(new Headers(init.headers).get('Idempotency-Key') ?? '');
        return posts === 1
          ? { ok: false, status: 500, json: async () => ({ detail: 'response lost after commit' }) }
          : ok({ status: 'created', task: second });
      }
      return ok({});
    });
    vi.stubGlobal('fetch', request);
    render(<TaskPage locale="zh-CN" />);
    await screen.findByText('此视图中暂无待办。');
    const startCreate = () => {
      fireEvent.click(screen.getByRole('button', { name: '新建待办' }));
      fireEvent.change(screen.getByLabelText('待办内容'), { target: { value: '重复内容' } });
      fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    };
    startCreate();
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: '收起' }));
    startCreate();
    expect(await screen.findByRole('heading', { name: '重复内容' })).toBeTruthy();
    expect(posts).toBe(2);
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBeTruthy();
    expect(keys[1]).not.toBe(keys[0]);
    expect((await screen.findAllByRole('heading', { name: '重复内容' })).length).toBe(1);
  });

  it.each([
    ['unknown status', { status: 'updated' }],
    ['missing task receipt', { task: undefined }],
    ['wrong title', { task: { ...task, title: '另一项任务' } }],
    ['wrong due date', { task: { ...task, title: '回执任务', due_date: '2026-10-25' } }],
    ['wrong task status', { task: { ...task, title: '回执任务', status: 'completed' } }],
    ['malformed task id', { task: { ...task, id: 'task-1', title: '回执任务' } }],
    ['untrusted task source', { task: { ...task, title: '回执任务', source: 'unverified' } }],
    ['missing task timestamps', { task: { ...task, title: '回执任务', created_at: undefined } }],
  ])('keeps the form open when the create receipt has %s', async (_caseName, patch) => {
    const response = { status: 'created', task: { ...task, title: '回执任务', due_date: null }, ...patch };
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => url === '/api/tasks' && init?.method === 'POST'
      ? ok(response) : ok({ tasks: [] })));
    render(<TaskPage locale="zh-CN" />);
    await screen.findByText('此视图中暂无待办。');
    fireEvent.click(screen.getByRole('button', { name: '新建待办' }));
    fireEvent.change(screen.getByLabelText('待办内容'), { target: { value: '回执任务' } });
    fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    expect((await screen.findByRole('alert')).textContent).toContain('无法核实保存回执');
    expect((screen.getByLabelText('待办内容') as HTMLInputElement).value).toBe('回执任务');
    expect(screen.queryByText('待办已创建。')).toBeNull();
  });

  it('reports a list refresh failure separately after a verified create receipt', async () => {
    let listReads = 0;
    const created = { ...task, id: 'e'.repeat(32), title: '已创建任务' };
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/tasks' && init?.method === 'POST') return ok({ status: 'created', task: created });
      if (url.startsWith('/api/tasks?')) {
        listReads += 1;
        return listReads === 1 ? ok({ tasks: [] }) : { ok: false, status: 503, json: async () => ({ detail: 'list unavailable' }) };
      }
      return ok({});
    }));
    render(<TaskPage locale="zh-CN" />);
    await screen.findByText('此视图中暂无待办。');
    fireEvent.click(screen.getByRole('button', { name: '新建待办' }));
    fireEvent.change(screen.getByLabelText('待办内容'), { target: { value: '已创建任务' } });
    fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    expect(await screen.findByText('待办已创建，但列表刷新失败：list unavailable')).toBeTruthy();
    expect(screen.getByRole('status').textContent).toBe('待办已创建。');
    expect(screen.getByRole('heading', { name: '已创建任务' })).toBeTruthy();
    expect(screen.queryByLabelText('待办内容')).toBeNull();
  });

  it('locks the whole create intent during a pending POST and ignores duplicate submits', async () => {
    let finishPost!: (value: ReturnType<typeof ok>) => void;
    const pendingPost = new Promise<ReturnType<typeof ok>>((resolve) => { finishPost = resolve; });
    const created = { ...task, id: 'f'.repeat(32), title: '并发提交任务' };
    const request = vi.fn((url: string, init?: RequestInit) => url === '/api/tasks' && init?.method === 'POST'
      ? pendingPost : Promise.resolve(ok({ tasks: [] })));
    vi.stubGlobal('fetch', request);
    render(<TaskPage locale="zh-CN" />);
    await screen.findByText('此视图中暂无待办。');
    fireEvent.click(screen.getByRole('button', { name: '新建待办' }));
    fireEvent.change(screen.getByLabelText('待办内容'), { target: { value: '并发提交任务' } });
    const form = screen.getByLabelText('待办内容').closest('form')!;
    fireEvent.submit(form);
    fireEvent.submit(form);

    await waitFor(() => expect(request.mock.calls.filter(([url, init]) => url === '/api/tasks' && init?.method === 'POST')).toHaveLength(1));
    expect((screen.getByLabelText('待办内容') as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText('状态') as HTMLSelectElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: '收起' }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: '刷新' }) as HTMLButtonElement).disabled).toBe(true);
    expect(window.sessionStorage.length).toBe(1);

    await act(async () => { finishPost(ok({ status: 'created', task: created })); await pendingPost; });
    expect(await screen.findByRole('heading', { name: '并发提交任务' })).toBeTruthy();
    expect(window.sessionStorage.length).toBe(0);
  });

  it('restores an ambiguous in-flight create after unmount and safely reconciles it with the same key', async () => {
    let finishFirst!: (value: ReturnType<typeof ok>) => void;
    let finishSecond!: (value: ReturnType<typeof ok>) => void;
    const firstPost = new Promise<ReturnType<typeof ok>>((resolve) => { finishFirst = resolve; });
    const secondPost = new Promise<ReturnType<typeof ok>>((resolve) => { finishSecond = resolve; });
    const created = { ...task, id: '1'.repeat(32), title: '离开页面时创建' };
    const keys: string[] = [];
    let postNumber = 0;
    const request = vi.fn((url: string, init?: RequestInit) => {
      if (url === '/api/tasks' && init?.method === 'POST') {
        keys.push(new Headers(init.headers).get('Idempotency-Key') ?? '');
        postNumber += 1;
        return postNumber === 1 ? firstPost : secondPost;
      }
      return Promise.resolve(ok({ tasks: [] }));
    });
    vi.stubGlobal('fetch', request);
    const first = render(<TaskPage locale="zh-CN" />);
    await screen.findByText('此视图中暂无待办。');
    fireEvent.click(screen.getByRole('button', { name: '新建待办' }));
    fireEvent.change(screen.getByLabelText('待办内容'), { target: { value: '离开页面时创建' } });
    fireEvent.submit(screen.getByLabelText('待办内容').closest('form')!);
    await waitFor(() => expect(postNumber).toBe(1));

    first.unmount();
    render(<TaskPage locale="zh-CN" />);
    expect(await screen.findByText('上次创建结果尚未确认；可用相同内容安全重试，或取消后重新创建。')).toBeTruthy();
    expect((screen.getByLabelText('待办内容') as HTMLInputElement).value).toBe('离开页面时创建');
    fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    await waitFor(() => expect(postNumber).toBe(2));
    expect(keys[1]).toBe(keys[0]);

    await act(async () => { finishFirst(ok({ status: 'created', task: created })); await firstPost; });
    await act(async () => { finishSecond(ok({ status: 'duplicate', task: created })); await secondPost; });
    expect(await screen.findByRole('heading', { name: '离开页面时创建' })).toBeTruthy();
    expect(screen.getAllByRole('heading', { name: '离开页面时创建' })).toHaveLength(1);
  });

  it('keeps a newer restored attempt when an older unmounted request succeeds', async () => {
    let finishFirst!: (value: ReturnType<typeof ok>) => void;
    let finishSecond!: (value: { ok: boolean; status: number; json: () => Promise<unknown> }) => void;
    const firstPost = new Promise<ReturnType<typeof ok>>((resolve) => { finishFirst = resolve; });
    const secondPost = new Promise<{ ok: boolean; status: number; json: () => Promise<unknown> }>((resolve) => { finishSecond = resolve; });
    const created = { ...task, id: '9'.repeat(32), title: '并发离页恢复' };
    const keys: string[] = [];
    let postNumber = 0;
    const request = vi.fn((url: string, init?: RequestInit) => {
      if (url === '/api/tasks' && init?.method === 'POST') {
        keys.push(new Headers(init.headers).get('Idempotency-Key') ?? '');
        postNumber += 1;
        return postNumber === 1 ? firstPost : secondPost;
      }
      return Promise.resolve(ok({ tasks: [] }));
    });
    vi.stubGlobal('fetch', request);
    const first = render(<TaskPage locale="zh-CN" />);
    await screen.findByText('此视图中暂无待办。');
    fireEvent.click(screen.getByRole('button', { name: '新建待办' }));
    fireEvent.change(screen.getByLabelText('待办内容'), { target: { value: '并发离页恢复' } });
    fireEvent.submit(screen.getByLabelText('待办内容').closest('form')!);
    await waitFor(() => expect(postNumber).toBe(1));

    first.unmount();
    const second = render(<TaskPage locale="zh-CN" />);
    expect(await screen.findByText('上次创建结果尚未确认；可用相同内容安全重试，或取消后重新创建。')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    await waitFor(() => expect(postNumber).toBe(2));
    expect(keys[1]).toBe(keys[0]);

    await act(async () => { finishFirst(ok({ status: 'created', task: created })); await firstPost; });
    await act(async () => { finishSecond({ ok: false, status: 500, json: async () => ({ detail: 'response lost after commit' }) }); await secondPost; });
    expect((await screen.findByRole('alert')).textContent).toContain('response lost after commit');
    second.unmount();

    render(<TaskPage locale="zh-CN" />);
    expect(await screen.findByText('上次创建结果尚未确认；可用相同内容安全重试，或取消后重新创建。')).toBeTruthy();
    expect((screen.getByLabelText('待办内容') as HTMLInputElement).value).toBe('并发离页恢复');
  });

  it('keeps a verified create visible when the following list response is stale', async () => {
    const created = { ...task, id: '2'.repeat(32), title: '列表快照落后的任务' };
    let listReads = 0;
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/tasks' && init?.method === 'POST') return ok({ status: 'created', task: created });
      if (url.startsWith('/api/tasks?')) { listReads += 1; return ok({ tasks: [] }); }
      return ok({});
    }));
    render(<TaskPage locale="zh-CN" />);
    await screen.findByText('此视图中暂无待办。');
    fireEvent.click(screen.getByRole('button', { name: '新建待办' }));
    fireEvent.change(screen.getByLabelText('待办内容'), { target: { value: '列表快照落后的任务' } });
    fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    expect(await screen.findByRole('heading', { name: '列表快照落后的任务' })).toBeTruthy();
    await waitFor(() => expect(listReads).toBe(2));
    expect(screen.getByRole('heading', { name: '列表快照落后的任务' })).toBeTruthy();
    expect(screen.getByRole('status').textContent).toBe('待办已创建。');
  });

  it('aborts and ignores a list request that was already in flight when create starts', async () => {
    let finishList!: (value: ReturnType<typeof ok>) => void;
    let listSignal: AbortSignal | undefined;
    const pendingList = new Promise<ReturnType<typeof ok>>((resolve) => { finishList = resolve; });
    const created = { ...task, id: '5'.repeat(32), title: '避免旧列表覆盖' };
    let listCalls = 0;
    const request = vi.fn((url: string, init?: RequestInit) => {
      if (url === '/api/tasks' && init?.method === 'POST') return Promise.resolve(ok({ status: 'created', task: created }));
      if (url.startsWith('/api/tasks?')) {
        listCalls += 1;
        if (listCalls === 1) { listSignal = init?.signal as AbortSignal; return pendingList; }
      }
      return Promise.resolve(ok({ tasks: [] }));
    });
    vi.stubGlobal('fetch', request);
    render(<TaskPage locale="zh-CN" />);
    fireEvent.click(screen.getByRole('button', { name: '新建待办' }));
    fireEvent.change(screen.getByLabelText('待办内容'), { target: { value: '避免旧列表覆盖' } });
    fireEvent.submit(screen.getByLabelText('待办内容').closest('form')!);
    expect(listSignal?.aborted).toBe(true);
    await act(async () => { finishList(ok({ tasks: [task] })); await pendingList; });
    expect(await screen.findByRole('heading', { name: '避免旧列表覆盖' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: '合成任务' })).toBeNull();
  });

  it.each([403, 409, 429, 500])('preserves create input and its retry key after HTTP %i', async (status) => {
    const keys: string[] = [];
    let posts = 0;
    const created = { ...task, id: '3'.repeat(32), title: '保留输入的任务' };
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/tasks' && init?.method === 'POST') {
        posts += 1;
        keys.push(new Headers(init.headers).get('Idempotency-Key') ?? '');
        return posts === 1 ? { ok: false, status, json: async () => ({ detail: `synthetic ${status}` }) }
          : ok({ status: 'duplicate', task: created });
      }
      return ok({ tasks: [] });
    }));
    render(<TaskPage locale="zh-CN" />);
    await screen.findByText('此视图中暂无待办。');
    fireEvent.click(screen.getByRole('button', { name: '新建待办' }));
    fireEvent.change(screen.getByLabelText('待办内容'), { target: { value: '保留输入的任务' } });
    fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    const message = (await screen.findByRole('alert')).textContent ?? '';
    expect(message).toContain(status === 409 ? '创建请求发生冲突' : `synthetic ${status}`);
    expect((screen.getByLabelText('待办内容') as HTMLInputElement).value).toBe('保留输入的任务');
    fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    expect(await screen.findByRole('heading', { name: '保留输入的任务' })).toBeTruthy();
    expect(keys[1]).toBe(keys[0]);
  });

  it('starts a fresh intent key after an unresolved payload is edited', async () => {
    const keys: string[] = [];
    let posts = 0;
    const created = { ...task, id: '4'.repeat(32), title: '改过内容' };
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/tasks' && init?.method === 'POST') {
        posts += 1;
        keys.push(new Headers(init.headers).get('Idempotency-Key') ?? '');
        return posts === 1 ? { ok: false, status: 500, json: async () => ({ detail: 'unknown result' }) }
          : ok({ status: 'created', task: created });
      }
      return ok({ tasks: [] });
    }));
    render(<TaskPage locale="zh-CN" />);
    await screen.findByText('此视图中暂无待办。');
    fireEvent.click(screen.getByRole('button', { name: '新建待办' }));
    fireEvent.change(screen.getByLabelText('待办内容'), { target: { value: '原始内容' } });
    fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    await screen.findByRole('alert');
    fireEvent.change(screen.getByLabelText('待办内容'), { target: { value: '改过内容' } });
    fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    expect(await screen.findByRole('heading', { name: '改过内容' })).toBeTruthy();
    expect(keys[0]).not.toBe(keys[1]);
  });

  it('switches back to the open view without briefly mixing completed tasks into a create result', async () => {
    const completed = { ...task, id: '6'.repeat(32), title: '既有已完成', status: 'completed' as const };
    const created = { ...task, id: '7'.repeat(32), title: '从全部视图新建' };
    const request = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/tasks' && init?.method === 'POST') return ok({ status: 'created', task: created });
      if (url.startsWith('/api/tasks?')) return ok({ tasks: url.includes('status=all') ? [completed] : [] });
      return ok({});
    });
    vi.stubGlobal('fetch', request);
    render(<TaskPage locale="zh-CN" />);
    await screen.findByText('此视图中暂无待办。');
    fireEvent.change(screen.getByLabelText('状态'), { target: { value: 'all' } });
    expect(await screen.findByRole('heading', { name: '既有已完成' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '新建待办' }));
    fireEvent.change(screen.getByLabelText('待办内容'), { target: { value: '从全部视图新建' } });
    fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    expect(await screen.findByRole('heading', { name: '从全部视图新建' })).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole('heading', { name: '既有已完成' })).toBeNull());
  });

  it('preserves an ambiguous network failure for same-key retry', async () => {
    const keys: string[] = [];
    let posts = 0;
    const created = { ...task, id: '8'.repeat(32), title: '网络中断重试' };
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/tasks' && init?.method === 'POST') {
        posts += 1;
        keys.push(new Headers(init.headers).get('Idempotency-Key') ?? '');
        if (posts === 1) throw new TypeError('network disconnected');
        return ok({ status: 'duplicate', task: created });
      }
      return ok({ tasks: [] });
    }));
    render(<TaskPage locale="zh-CN" />);
    await screen.findByText('此视图中暂无待办。');
    fireEvent.click(screen.getByRole('button', { name: '新建待办' }));
    fireEvent.change(screen.getByLabelText('待办内容'), { target: { value: '网络中断重试' } });
    fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    expect((await screen.findByRole('alert')).textContent).toContain('network disconnected');
    fireEvent.click(screen.getByRole('button', { name: '创建待办' }));
    expect(await screen.findByRole('heading', { name: '网络中断重试' })).toBeTruthy();
    expect(keys[1]).toBe(keys[0]);
  });
});
