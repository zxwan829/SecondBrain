import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { JournalPage } from './JournalPage';

describe('JournalPage', () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); window.history.replaceState({}, '', '/'); });

  it('reads real entries and submits an explicit original phrase with a stable retry key', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (!init?.method || init.method === 'GET') return new Response(JSON.stringify({ entries: [] }), { status: 200 });
      expect(url).toBe('/api/journal/entries');
      expect(new Headers(init?.headers).get('Idempotency-Key')).toBeTruthy();
      expect(JSON.parse(String(init?.body)).text).toBe('记一下：测试原话');
      return new Response(JSON.stringify({ status: 'created', entry: { id: 'entry-1' } }), { status: 200 });
    });
    render(<JournalPage />);
    const field = await screen.findByLabelText('自然语言记录');
    fireEvent.change(field, { target: { value: '记一下：测试原话' } });
    fireEvent.click(screen.getByRole('button', { name: '追加原话' }));
    await screen.findByText('已追加到当日日记。');
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
  });

  it('keeps the successful save receipt visible when refreshing the entry list fails', async () => {
    let reads = 0;
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (!init?.method || init.method === 'GET') {
        reads += 1;
        return reads === 1
          ? Response.json({ entries: [] })
          : new Response('{}', { status: 503 });
      }
      expect(new Headers(init?.headers).get('Idempotency-Key')).toBeTruthy();
      return Response.json({ status: 'created', entry: { id: 'entry-2' } });
    });
    render(<JournalPage />);
    fireEvent.change(await screen.findByLabelText('自然语言记录'), { target: { value: '记一下：已保存' } });
    fireEvent.click(screen.getByRole('button', { name: '追加原话' }));
    expect(await screen.findByText('已追加到当日日记。')).toBeTruthy();
    expect(await screen.findByText('无法刷新 Journal 列表；已保存的记录不会因此撤销。')).toBeTruthy();
    expect(screen.queryByText('Journal 保存未获成功回执')).toBeNull();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
  });

  it('restores the selected Shanghai Journal date and highlights a referenced entry', async () => {
    window.history.replaceState({}, '', '/journal?date=2026-10-20&entry_id=entry-synth');
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(Response.json({ entries: [
      { id: 'entry-synth', created_at: '2026-10-20T01:00:00Z', source: 'manual', original_text: '合成日记原文' },
    ] }));
    render(<JournalPage />);
    expect((await screen.findByLabelText('日期') as HTMLInputElement).value).toBe('2026-10-20');
    expect(await screen.findByText('此记录被简报引用')).toBeTruthy();
    expect(document.getElementById('journal-entry-entry-synth')).toBeTruthy();
  });

  it('highlights a Journal entry from the date-qualified Daily Brief source ref', async () => {
    window.history.replaceState({}, '', `/journal?date=2026-10-22&entry_id=${encodeURIComponent(`2026-10-22:${'b'.repeat(64)}`)}`);
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(Response.json({ entries: [
      { id: 'b'.repeat(64), created_at: '2026-10-22T01:00:00Z', source: 'manual', original_text: '合成简报来源日记' },
    ] }));
    render(<JournalPage />);
    expect(await screen.findByText('此记录被简报引用')).toBeTruthy();
    expect(document.getElementById(`journal-entry-${'b'.repeat(64)}`)).toBeTruthy();
  });

  it('ignores a late Journal response after the user changes the business date', async () => {
    let finishFirst!: (response: Response) => void;
    const first = new Promise<Response>((resolve) => { finishFirst = resolve; });
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith('/2026-10-21')) return first;
      if (url.endsWith('/2026-10-22')) return Promise.resolve(Response.json({ entries: [
        { id: 'new-entry', created_at: '2026-10-22T01:00:00Z', source: 'manual', original_text: '新日期记录' },
      ] }));
      return Promise.resolve(Response.json({ entries: [] }));
    });
    window.history.replaceState({}, '', '/journal?date=2026-10-21');
    render(<JournalPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText('日期'), { target: { value: '2026-10-22' } });
    expect(await screen.findByText('新日期记录')).toBeTruthy();
    await act(async () => { finishFirst(Response.json({ entries: [
      { id: 'old-entry', created_at: '2026-10-21T01:00:00Z', source: 'manual', original_text: '旧日期迟到记录' },
    ] })); await first; });
    expect(screen.getByText('新日期记录')).toBeTruthy();
    expect(screen.queryByText('旧日期迟到记录')).toBeNull();
  });
});
