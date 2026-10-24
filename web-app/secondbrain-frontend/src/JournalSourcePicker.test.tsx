import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { JournalSourcePicker } from './JournalSourcePicker';

const date = new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
}).formatToParts(new Date()).reduce<Record<string, string>>((parts, part) => {
  parts[part.type] = part.value;
  return parts;
}, {});
const today = `${date.year}-${date.month}-${date.day}`;
const version = 'e'.repeat(64);

function options(status: 'real' | 'empty' | 'unavailable' = 'real') {
  return {
    status,
    items: status === 'real' ? [
      { kind: 'journal', id: `${today}:${'a'.repeat(64)}`, date: today, version },
      { kind: 'journal', id: `${today}:${'b'.repeat(64)}`, date: today, version },
    ] : [],
    freshness: { checked_at: '2026-10-20T01:30:00Z' },
  };
}

describe('Journal source picker', () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it('does not request sources until the user explicitly asks to load them', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => Response.json(options()));
    vi.stubGlobal('fetch', fetchMock);
    render(<JournalSourcePicker locale="zh-CN" />);
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '加载 Journal 来源' }));
    expect(await screen.findByText(/已选择 0 条来源|尚未选择来源/)).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/daily-brief/source-options/journal?date=${today}`);
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ credentials: 'same-origin', cache: 'no-store' });
  });

  it('allows transient source selection but never submits or claims to create a brief', async () => {
    const calls: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      calls.push(String(input)); return Response.json(options());
    }));
    render(<JournalSourcePicker locale="zh-CN" />);
    fireEvent.click(screen.getByRole('button', { name: '加载 Journal 来源' }));
    const checkboxes = await screen.findAllByRole('checkbox');
    expect(checkboxes).toHaveLength(2);
    fireEvent.click(checkboxes[0]!);
    expect(await screen.findByText(/已选择 1 条来源/)).toBeTruthy();
    expect(screen.getByText(/不会生成或修改简报/)).toBeTruthy();
    expect(screen.queryByText(/SYNTHETIC.*BODY/)).toBeNull();
    expect(calls).toEqual([`/api/daily-brief/source-options/journal?date=${today}`]);
  });

  it('shows an empty state without options', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json(options('empty'))));
    render(<JournalSourcePicker locale="zh-CN" />);
    fireEvent.click(screen.getByRole('button', { name: '加载 Journal 来源' }));
    expect(await screen.findByText('当天没有可选择的 Journal 来源。')).toBeTruthy();
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
  });

  it('withholds partial results on unavailable or authorization failures', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json(options('unavailable'))));
    const { rerender } = render(<JournalSourcePicker locale="zh-CN" />);
    fireEvent.click(screen.getByRole('button', { name: '加载 Journal 来源' }));
    expect(await screen.findByText(/未显示部分结果/)).toBeTruthy();
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);

    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 403 })));
    rerender(<JournalSourcePicker locale="zh-CN" />);
    fireEvent.click(screen.getByRole('button', { name: '重新加载' }));
    expect(await screen.findByText('Journal 来源请求未获授权；请检查登录状态或请求安全策略。')).toBeTruthy();
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
  });

  it('aborts an in-flight source request when the picker unmounts', async () => {
    let observedSignal: AbortSignal | undefined;
    vi.stubGlobal('fetch', vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      observedSignal = init?.signal as AbortSignal;
      return new Promise<Response>(() => {});
    }));
    const { unmount } = render(<JournalSourcePicker locale="en" />);
    fireEvent.click(screen.getByRole('button', { name: 'Load Journal sources' }));
    await waitFor(() => expect(observedSignal).toBeDefined());
    unmount();
    expect(observedSignal?.aborted).toBe(true);
  });
});
