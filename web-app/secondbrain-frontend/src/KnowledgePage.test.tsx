import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { KnowledgePage } from './KnowledgePage';

const itemA = { id: 'opaque-a', title: 'Synthetic Alpha', snippet: 'Needle in safe summary', match: 'content', updated: '2026-10-18T00:00:00Z', sha256: 'a'.repeat(64), provenance_status: 'unverified' };
const itemB = { id: 'opaque-b', title: 'Synthetic Beta', snippet: 'Second safe summary', match: 'title', updated: '2026-10-18T00:00:01Z', sha256: 'b'.repeat(64), provenance_status: 'missing' };

function searchResponse(items = [itemA, itemB], status = 'ok') {
  return new Response(JSON.stringify({ items, status }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

function detailResponse(id: string, content = '# Synthetic detail\n\nSafe body.') {
  return new Response(JSON.stringify({ id, content, sha256: 'c'.repeat(64), updated: '2026-10-18T00:00:02Z', provenance_status: 'unverified' }), { status: 200 });
}

function submitSearch(value = 'Needle') {
  fireEvent.change(screen.getByRole('searchbox', { name: /搜索关键词|Search terms/ }), { target: { value } });
  fireEvent.click(screen.getByRole('button', { name: /搜索|Search/ }));
}

describe('Knowledge read-only page', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('makes no request until a non-empty search is explicitly submitted', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(searchResponse());
    render(<KnowledgePage locale="zh-CN" />);
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '搜索' }));
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole('searchbox', { name: '搜索关键词' }), { target: { value: '  ' } });
    fireEvent.click(screen.getByRole('button', { name: '搜索' }));
    expect(fetch).not.toHaveBeenCalled();
  });

  it('uses the frozen API contract, opens only a selected result and renders Markdown as safe React text', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      if (url.startsWith('/api/knowledge/search?')) return searchResponse([itemA]);
      if (url === '/api/knowledge/items/opaque-a') return detailResponse('opaque-a', '# Synthetic detail\n\n<script>window.bad = true</script>');
      return new Response('{}', { status: 404 });
    });
    render(<KnowledgePage locale="zh-CN" />);
    submitSearch();
    expect(await screen.findByRole('button', { name: /Synthetic Alpha/ })).toBeTruthy();
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe('/api/knowledge/search?q=Needle&limit=50');
    expect(calls[0].init?.credentials).toBe('same-origin');
    expect(calls[0].init?.cache).toBe('no-store');
    expect(calls.some((call) => call.url.endsWith('/source'))).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: /Synthetic Alpha/ }));
    expect(await screen.findByRole('heading', { name: 'Synthetic detail' })).toBeTruthy();
    expect(screen.getAllByText(/来源声明不可验证/)).toHaveLength(2);
    expect(screen.queryByText(/来源已验证/)).toBeNull();
    expect(document.querySelector('script')).toBeNull();
    expect(screen.getByText('<script>window.bad = true</script>')).toBeTruthy();
    expect(calls.map((call) => call.url)).toEqual([
      '/api/knowledge/search?q=Needle&limit=50', '/api/knowledge/items/opaque-a',
    ]);
  });

  it('shows truncated coverage without implying complete results and clears query without fetching', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(searchResponse([itemA], 'truncated'));
    render(<KnowledgePage locale="en" />);
    submitSearch('Needle');
    expect(await screen.findByText(/Results are partial/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('Synthetic Alpha')).toBeNull();
    expect((screen.getByRole('searchbox', { name: 'Search terms' }) as HTMLInputElement).value).toBe('');
  });

  it('aborts and ignores an older search response that arrives after the newer query', async () => {
    let finishOld!: (response: Response) => void;
    const oldSearch = new Promise<Response>((resolve) => { finishOld = resolve; });
    const calls: Array<{ url: string; signal?: AbortSignal }> = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input);
      calls.push({ url, signal: init?.signal as AbortSignal | undefined });
      if (url.includes('q=Old')) return oldSearch;
      if (url.includes('q=New')) return Promise.resolve(searchResponse([itemB]));
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    render(<KnowledgePage locale="en" />);
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search terms' }), { target: { value: 'Old' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(calls.some((call) => call.url.includes('q=Old'))).toBe(true));
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search terms' }), { target: { value: 'New' } });
    fireEvent.click(screen.getByRole('button', { name: 'Searching…' }));
    expect(calls[0].signal?.aborted).toBe(true);
    expect(await screen.findByRole('button', { name: /Synthetic Beta/ })).toBeTruthy();
    await act(async () => { finishOld(searchResponse([itemA])); await oldSearch; });
    expect(screen.getByRole('button', { name: /Synthetic Beta/ })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Synthetic Alpha/ })).toBeNull();
  });

  it('keeps only the current selection when detail requests resolve out of order', async () => {
    let finishA!: (response: Response) => void;
    const pendingA = new Promise<Response>((resolve) => { finishA = resolve; });
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input);
      if (url.startsWith('/api/knowledge/search?')) return Promise.resolve(searchResponse());
      if (url.endsWith('/opaque-a')) return pendingA;
      if (url.endsWith('/opaque-b')) return Promise.resolve(detailResponse('opaque-b', '# Current Beta'));
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    render(<KnowledgePage locale="en" />);
    submitSearch();
    fireEvent.click(await screen.findByRole('button', { name: /Synthetic Alpha/ }));
    fireEvent.click(screen.getByRole('button', { name: /Synthetic Beta/ }));
    expect(await screen.findByRole('heading', { name: 'Current Beta' })).toBeTruthy();
    await act(async () => { finishA(detailResponse('opaque-a', '# Stale Alpha')); await pendingA; });
    expect(screen.getByRole('heading', { name: 'Current Beta' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Stale Alpha' })).toBeNull();
  });

  it('clears the prior body and results when authorization or service is unavailable', async () => {
    let failDetail = false;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.startsWith('/api/knowledge/search?')) return searchResponse();
      if (url.endsWith('/opaque-a') && failDetail) return new Response('{}', { status: 403 });
      return detailResponse(url.split('/').at(-1) ?? 'opaque-a', '# Previous private-looking body');
    });
    render(<KnowledgePage locale="en" />);
    submitSearch();
    fireEvent.click(await screen.findByRole('button', { name: /Synthetic Beta/ }));
    expect(await screen.findByRole('heading', { name: 'Previous private-looking body' })).toBeTruthy();
    failDetail = true;
    fireEvent.click(screen.getByRole('button', { name: /Synthetic Alpha/ }));
    expect((await screen.findByRole('alert')).textContent).toMatch(/not permitted/);
    expect(screen.queryByRole('heading', { name: 'Previous private-looking body' })).toBeNull();
    expect(screen.queryByText('Synthetic Alpha')).toBeNull();
    expect(screen.queryByText('Synthetic Beta')).toBeNull();
  });

  it.each([404, 409])('offers an explicit fresh search after stale detail HTTP %s', async (status) => {
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      calls.push(url);
      if (url.startsWith('/api/knowledge/search?')) return searchResponse([itemA]);
      return new Response('{}', { status });
    });
    render(<KnowledgePage locale="zh-CN" />);
    submitSearch();
    fireEvent.click(await screen.findByRole('button', { name: /Synthetic Alpha/ }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByRole('button', { name: '重新搜索' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '重新搜索' }));
    await waitFor(() => expect(calls.filter((url) => url.startsWith('/api/knowledge/search?'))).toHaveLength(2));
  });

  it('aborts an in-flight detail request when the selection is closed or the page unmounts', async () => {
    const signals: AbortSignal[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input);
      if (url.startsWith('/api/knowledge/search?')) return Promise.resolve(searchResponse([itemA]));
      if (url.endsWith('/opaque-a')) {
        signals.push(init?.signal as AbortSignal);
        return new Promise<Response>(() => {});
      }
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    const page = render(<KnowledgePage locale="en" />);
    submitSearch();
    fireEvent.click(await screen.findByRole('button', { name: /Synthetic Alpha/ }));
    await waitFor(() => expect(signals).toHaveLength(1));
    fireEvent.click(screen.getByRole('button', { name: 'Back to results' }));
    expect(signals[0].aborted).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: /Synthetic Alpha/ }));
    await waitFor(() => expect(signals).toHaveLength(2));
    page.unmount();
    expect(signals[1].aborted).toBe(true);
  });
});
