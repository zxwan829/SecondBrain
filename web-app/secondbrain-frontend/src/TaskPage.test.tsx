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
        expect(body).toEqual({ title: '直接新建的任务', due_date: '2026-10-24', original_command: '添加待办：直接新建的任务；截止：2026-10-24' });
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
    ['wrong due date', { task: { ...task, title: '回执任务', due_date: '2026-10-25' } }],
    ['malformed task id', { task: { ...task, id: 'task-1', title: '回执任务' } }],
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
});
