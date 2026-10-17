import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
});
