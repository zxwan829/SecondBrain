import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { PersonalMemoryPage } from './PersonalMemoryPage';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const row = { memory_id: 'memory-synthetic-1', revision: 1, content: { text: 'synthetic preference' },
  category: 'preference', fact_kind: 'user_stated', status: 'active', recorded_at: '2026-10-22T00:00:00Z',
  source: { type: 'user_message', ref: 'synthetic-session/message-1' } };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status,
  headers: { 'Content-Type': 'application/json', 'Cache-Control': 'private, no-store' } });

describe('Personal Memory page', () => {
  it('does not write on load and retries an explicit correction with the same idempotency key', async () => {
    const posts: string[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.startsWith('/api/personal-memory?')) return json({ items: posts.length ? [] : [row] });
      if (url.endsWith('/correct')) {
        posts.push(String(init?.body));
        return posts.length === 1 ? json({ detail: 'synthetic timeout recovery' }, 503)
          : json({ ...row, revision: 2, content: { text: 'corrected synthetic preference' } });
      }
      throw new Error(`unexpected synthetic request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<PersonalMemoryPage locale="en" />);
    await screen.findByText('synthetic preference');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Correct' }));
    fireEvent.change(screen.getByLabelText('Replacement text'), { target: { value: 'corrected synthetic preference' } });
    fireEvent.change(screen.getByLabelText('Type CONFIRM'), { target: { value: 'CONFIRM' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm change' }));
    await screen.findByText('The result is unconfirmed. Retry the same request with its original key.');
    expect((screen.getByLabelText('Replacement text') as HTMLTextAreaElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Retry same request' }));
    await screen.findByText('Core confirmed the saved revision');
    await waitFor(() => expect(posts).toHaveLength(2));
    expect(JSON.parse(posts[0])).toEqual(JSON.parse(posts[1]));
    expect(JSON.parse(posts[0])).toMatchObject({ expected_revision: 1, content: { text: 'corrected synthetic preference' } });
    expect(JSON.parse(posts[0]).idempotency_key).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });
});
