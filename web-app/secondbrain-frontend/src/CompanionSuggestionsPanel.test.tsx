import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { CompanionSuggestionsPanel } from './CompanionSuggestionsPanel';

const suggestion = { id: 'a'.repeat(32), category: 'task_due', title: 'Synthetic task', reason: 'Due soon',
  source_ref: { kind: 'task', id: 'task-1', version: 'b'.repeat(64) }, state: 'shown', expires_at: '2099-01-01T00:00:00Z', revision: 3 };
const prefs = { event: 'companion.preferences', version: 1, revision: 2, enabled: true, categories: ['task_due'] };
const rows = { event: 'companion.suggestions', version: 1, status: 'available', revision: 5, items: [suggestion] };
const disabledPrefs = { event: 'companion.preferences', version: 1, revision: 0, enabled: false, categories: [] };

function installLoad(fetchMock: ReturnType<typeof vi.fn>, suggestionBody: unknown = rows) {
  fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith('/preferences')) return Response.json(prefs);
    if (url.endsWith('/suggestions')) return Response.json(suggestionBody);
    throw new Error(`Unexpected request ${url}`);
  });
}

afterEach(() => { vi.unstubAllGlobals(); });

describe('CompanionSuggestionsPanel feedback contract', () => {
  it('consumes the nested Core settings receipt without crashing the Today panel', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/preferences') && !init?.method) return Response.json(disabledPrefs);
      if (url.endsWith('/suggestions')) return Response.json({ ...rows, status: 'disabled', items: [] });
      if (url.endsWith('/preferences') && init?.method === 'PUT') {
        expect(JSON.parse(String(init.body))).toEqual({ enabled: true, categories: ['task_due'], expected_revision: 0 });
        return Response.json({ event: 'companion.preferences.receipt', version: 1, status: 'saved', revision: 1,
          settings: { enabled: true, categories: ['task_due'] } });
      }
      throw new Error(`Unexpected request ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('crypto', { randomUUID: () => 'e'.repeat(32) });
    render(<CompanionSuggestionsPanel locale="en" />);
    const enabled = await screen.findByRole('checkbox', { name: 'Enable suggestions' });
    fireEvent.click(enabled);
    await waitFor(() => expect((screen.getByRole('button', { name: 'Check now' }) as HTMLButtonElement).disabled).toBe(false));
    expect(screen.queryByRole('alert')).toBeNull();
    expect((screen.getByRole('checkbox', { name: 'Enable suggestions' }) as HTMLInputElement).checked).toBe(true);
  });

  it('sends the surfaced revision and reuses the exact idempotency key after an ambiguous failure', async () => {
    const fetchMock = vi.fn();
    installLoad(fetchMock);
    const keys: string[] = [];
    const bodies: string[] = [];
    let attempts = 0;
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/preferences')) return Response.json(prefs);
      if (url.endsWith('/suggestions')) return Response.json(rows);
      if (url.includes('/feedback')) {
        attempts += 1;
        keys.push(new Headers(init?.headers).get('Idempotency-Key') ?? '');
        bodies.push(String(init?.body));
        if (attempts === 1) return Response.json({ detail: 'temporary failure' }, { status: 503 });
        return Response.json({ event: 'companion.suggestion.feedback', version: 1, status: 'accepted',
          id: suggestion.id, revision: 4, state: 'accepted' });
      }
      throw new Error(`Unexpected request ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('crypto', { randomUUID: () => 'c'.repeat(32) });
    render(<CompanionSuggestionsPanel locale="en" />);
    const accept = await screen.findByRole('button', { name: 'Accept' });
    fireEvent.click(accept);
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));
    await waitFor(() => expect(screen.queryByText('Synthetic task')).toBeNull());
    expect(keys).toEqual(['c'.repeat(32), 'c'.repeat(32)]);
    expect(JSON.parse(bodies[0])).toEqual({ decision: 'accepted', expected_revision: 3 });
    expect(bodies[1]).toBe(bodies[0]);
  });

  it('refreshes visible suggestions after a stale revision conflict', async () => {
    const fetchMock = vi.fn();
    let suggestionReads = 0;
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/preferences')) return Response.json(prefs);
      if (url.endsWith('/suggestions')) {
        suggestionReads += 1;
        return Response.json(suggestionReads === 1 ? rows : { ...rows, status: 'none', items: [] });
      }
      if (url.includes('/feedback')) return Response.json({ detail: 'Suggestion changed' }, { status: 409 });
      throw new Error(`Unexpected request ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('crypto', { randomUUID: () => 'd'.repeat(32) });
    render(<CompanionSuggestionsPanel locale="en" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Accept' }));
    expect((await screen.findByRole('alert')).textContent).toContain('This suggestion changed. The list has been refreshed');
    await waitFor(() => expect(screen.queryByText('Synthetic task')).toBeNull());
    expect(suggestionReads).toBe(2);
  });
});
