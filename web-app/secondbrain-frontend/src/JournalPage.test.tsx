import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { JournalPage } from './JournalPage';

describe('JournalPage', () => {
  afterEach(() => vi.restoreAllMocks());

  it('reads real entries and submits an explicit original phrase with a stable retry key', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.startsWith('/api/journal/')) return new Response(JSON.stringify({ entries: [] }), { status: 200 });
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
});
