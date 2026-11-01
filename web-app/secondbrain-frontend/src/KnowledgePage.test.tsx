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

function sourceResponse(value: unknown) {
  return new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

function foldersResponse(path: string, folders: Array<{ name: string; path: string }> = []) {
  return new Response(JSON.stringify({ status: 'ok', path, folders, scan: { entries: folders.length, complete: true } }), { status: 200 });
}

function browseResponse(path = '', items: Array<Record<string, unknown>> = [], tags: Array<{ name: string; count: number; count_complete: boolean }> = []) {
  return new Response(JSON.stringify({ status: 'ok', path, tag_facets: tags, items, total: items.length, total_complete: true,
    offset: 0, limit: 20, next_offset: null, scan: { entries: items.length, complete: true } }), { status: 200 });
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
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/api/knowledge/search'))).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: '搜索' }));
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/api/knowledge/search'))).toBe(false);
    fireEvent.change(screen.getByRole('searchbox', { name: '搜索关键词' }), { target: { value: '  ' } });
    fireEvent.click(screen.getByRole('button', { name: '搜索' }));
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/api/knowledge/search'))).toBe(false);
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
    const searchCalls = calls.filter((call) => call.url.startsWith('/api/knowledge/search?'));
    expect(searchCalls).toHaveLength(1);
    expect(searchCalls[0].url).toBe('/api/knowledge/search?q=Needle&limit=50');
    expect(searchCalls[0].init?.credentials).toBe('same-origin');
    expect(searchCalls[0].init?.cache).toBe('no-store');
    expect(calls.some((call) => call.url.endsWith('/source'))).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: /Synthetic Alpha/ }));
    expect(await screen.findByRole('heading', { name: 'Synthetic detail' })).toBeTruthy();
    expect(screen.getAllByText(/来源声明不可验证/)).toHaveLength(2);
    expect(screen.queryByText(/来源已验证/)).toBeNull();
    expect(document.querySelector('script')).toBeNull();
    expect(screen.getByText('<script>window.bad = true</script>')).toBeTruthy();
    expect(calls.filter((call) => !call.url.startsWith('/api/knowledge/folders?') && !call.url.startsWith('/api/knowledge/browse?')).map((call) => call.url)).toEqual([
      '/api/knowledge/search?q=Needle&limit=50', '/api/knowledge/items/opaque-a',
    ]);
  });

  it('checks the Core source only after an explicit action and links only a validated verified Review ref', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      if (url.startsWith('/api/knowledge/search?')) return searchResponse([itemA]);
      if (url === '/api/knowledge/items/opaque-a') return detailResponse('opaque-a');
      if (url === '/api/knowledge/items/opaque-a/source') return sourceResponse({
        status: 'available', provenance_status: 'verified',
        source: { kind: 'review', ref: 'candidate.md', sha256: 'f'.repeat(64), request_id: 'b1b-synthetic-1' },
      });
      return new Response('{}', { status: 404 });
    });
    render(<KnowledgePage locale="zh-CN" />);
    submitSearch();
    fireEvent.click(await screen.findByRole('button', { name: /Synthetic Alpha/ }));
    await screen.findByRole('heading', { name: 'Synthetic detail' });
    expect(calls.some((call) => call.url.endsWith('/source'))).toBe(false);
    expect(screen.queryByRole('link', { name: '打开已验证的来源 Review' })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '检查来源回溯' }));
    const sourceLink = await screen.findByRole('link', { name: '打开已验证的来源 Review' });
    expect(sourceLink.getAttribute('href')).toBe('/review?review_path=candidate.md');
    expect(screen.getByText('Core 已验证此 Review 来源。')).toBeTruthy();
    expect(screen.getByText('b1b-synthetic-1')).toBeTruthy();
    const sourceCall = calls.find((call) => call.url.endsWith('/source'))!;
    expect(sourceCall.url).toBe('/api/knowledge/items/opaque-a/source');
    expect(sourceCall.init?.credentials).toBe('same-origin');
    expect(sourceCall.init?.cache).toBe('no-store');
  });

  it.each([
    ['unverified source', { status: 'unavailable', provenance_status: 'unverified', source: null }, 'Core 无法验证该来源；不提供来源链接。'],
    ['missing source', { status: 'missing', provenance_status: 'missing', source: null }, '此条目没有来源记录。'],
  ])('does not invent a Review link for a %s', async (_name, source, message) => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.startsWith('/api/knowledge/search?')) return searchResponse([itemA]);
      if (url === '/api/knowledge/items/opaque-a') return detailResponse('opaque-a');
      if (url.endsWith('/source')) return sourceResponse(source);
      return new Response('{}', { status: 404 });
    });
    render(<KnowledgePage locale="zh-CN" />);
    submitSearch();
    fireEvent.click(await screen.findByRole('button', { name: /Synthetic Alpha/ }));
    await screen.findByRole('heading', { name: 'Synthetic detail' });
    fireEvent.click(screen.getByRole('button', { name: '检查来源回溯' }));
    expect(await screen.findByText(message)).toBeTruthy();
    expect(screen.queryByRole('link', { name: '打开已验证的来源 Review' })).toBeNull();
  });

  it.each([
    ['path traversal', { status: 'available', provenance_status: 'verified', source: { kind: 'review', ref: '../private.md', sha256: 'f'.repeat(64), request_id: 'b1b-synthetic-1' } }],
    ['mismatched status', { status: 'available', provenance_status: 'unverified', source: null }],
  ])('fails closed for malformed %s source responses', async (_name, source) => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.startsWith('/api/knowledge/search?')) return searchResponse([itemA]);
      if (url === '/api/knowledge/items/opaque-a') return detailResponse('opaque-a');
      if (url.endsWith('/source')) return sourceResponse(source);
      return new Response('{}', { status: 404 });
    });
    render(<KnowledgePage locale="zh-CN" />);
    submitSearch();
    fireEvent.click(await screen.findByRole('button', { name: /Synthetic Alpha/ }));
    await screen.findByRole('heading', { name: 'Synthetic detail' });
    fireEvent.click(screen.getByRole('button', { name: '检查来源回溯' }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByText('知识库加载失败，请重试。')).toBeTruthy();
    expect(screen.queryByRole('link', { name: '打开已验证的来源 Review' })).toBeNull();
    expect(screen.queryByText('../private.md')).toBeNull();
  });

  it('aborts a source lookup when the selected Knowledge result changes', async () => {
    let finishSource!: (response: Response) => void;
    const pendingSource = new Promise<Response>((resolve) => { finishSource = resolve; });
    let sourceSignal: AbortSignal | undefined;
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input);
      if (url.startsWith('/api/knowledge/search?')) return Promise.resolve(searchResponse());
      if (url === '/api/knowledge/items/opaque-a') return Promise.resolve(detailResponse('opaque-a', '# Alpha detail'));
      if (url === '/api/knowledge/items/opaque-b') return Promise.resolve(detailResponse('opaque-b', '# Beta detail'));
      if (url === '/api/knowledge/items/opaque-a/source') {
        sourceSignal = init?.signal as AbortSignal | undefined;
        return pendingSource;
      }
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    render(<KnowledgePage locale="en" />);
    submitSearch();
    fireEvent.click(await screen.findByRole('button', { name: /Synthetic Alpha/ }));
    expect(await screen.findByRole('heading', { name: 'Alpha detail' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Check source trace' }));
    await waitFor(() => expect(sourceSignal).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /Synthetic Beta/ }));
    expect(await screen.findByRole('heading', { name: 'Beta detail' })).toBeTruthy();
    expect(sourceSignal?.aborted).toBe(true);
    await act(async () => { finishSource(sourceResponse({
      status: 'available', provenance_status: 'verified',
      source: { kind: 'review', ref: 'stale-alpha.md', sha256: 'f'.repeat(64), request_id: 'b1b-synthetic-old' },
    })); await pendingSource; });
    expect(screen.queryByText('Core verified the Review source.')).toBeNull();
    expect(screen.queryByText('stale-alpha.md')).toBeNull();
    expect(screen.getByRole('heading', { name: 'Beta detail' })).toBeTruthy();
  });

  it('shows truncated coverage without implying complete results and clears query without fetching', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve(searchResponse([itemA], 'truncated')));
    render(<KnowledgePage locale="en" />);
    submitSearch('Needle');
    expect(await screen.findByText(/Results are partial/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    expect(fetch.mock.calls.filter(([url]) => String(url).startsWith('/api/knowledge/search?'))).toHaveLength(1);
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
    expect(calls.find((call) => call.url.includes('q=Old'))?.signal?.aborted).toBe(true);
    expect(await screen.findByRole('button', { name: /Synthetic Beta/ })).toBeTruthy();
    await act(async () => { finishOld(searchResponse([itemA])); await oldSearch; });
    expect(screen.getByRole('button', { name: /Synthetic Beta/ })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Synthetic Alpha/ })).toBeNull();
  });

  it('browses real folder and tag responses, resets filters on folder change, and opens through the existing item endpoint', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    const browseItem = { id: 'browse-id', path: 'Work/Note.md', title: 'Synthetic Note', updated: '2026-11-02T00:00:00Z', tags: ['AI', '研究'], metadata_status: 'ok' };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      const parsed = new URL(url, 'http://localhost');
      if (parsed.pathname.endsWith('/folders')) return foldersResponse(parsed.searchParams.get('path') ?? '', parsed.searchParams.get('path') ? [] : [{ name: 'Work', path: 'Work' }]);
      if (parsed.pathname.endsWith('/browse')) return browseResponse(parsed.searchParams.get('path') ?? '', parsed.searchParams.get('path') === 'Work' ? [browseItem] : [], [
        { name: 'AI', count: 1, count_complete: true }, { name: '研究', count: 1, count_complete: true },
      ]);
      if (parsed.pathname === '/api/knowledge/items/browse-id') return detailResponse('browse-id', '# Opened synthetic note');
      return new Response('{}', { status: 404 });
    });
    render(<KnowledgePage locale="zh-CN" />);
    await screen.findByRole('button', { name: 'Expand Work' });
    fireEvent.click(screen.getByRole('button', { name: 'Work' }));
    expect(await screen.findByRole('button', { name: /Synthetic Note/ })).toBeTruthy();
    fireEvent.click(screen.getByRole('checkbox', { name: /AI/ }));
    expect(await screen.findByRole('checkbox', { name: /AI/ })).toBeTruthy();
    await waitFor(() => expect(calls.some((call) => call.url.includes('/api/knowledge/browse?path=Work&match=and&offset=0&limit=20&tag=AI'))).toBe(true));
    fireEvent.click(screen.getByRole('checkbox', { name: /研究/ }));
    expect(await screen.findByRole('combobox', { name: '匹配' })).toBeTruthy();
    fireEvent.change(screen.getByRole('combobox', { name: '匹配' }), { target: { value: 'or' } });
    await waitFor(() => expect(calls.some((call) => call.url.includes('match=or'))).toBe(true));
    fireEvent.click(screen.getByRole('button', { name: '全部知识' }));
    await screen.findByRole('checkbox', { name: /AI/ });
    expect((screen.getByRole('checkbox', { name: /AI/ }) as HTMLInputElement).checked).toBe(false);
    expect(screen.queryByRole('combobox', { name: '匹配' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Work' }));
    fireEvent.click(await screen.findByRole('button', { name: /Synthetic Note/ }));
    expect(await screen.findByRole('heading', { name: 'Opened synthetic note' })).toBeTruthy();
    const browseCall = calls.find((call) => call.url.includes('/api/knowledge/browse?'))!;
    expect(browseCall.init?.cache).toBe('no-store');
    expect(browseCall.init?.credentials).toBe('same-origin');
    expect(calls.some((call) => call.url === '/api/knowledge/items/browse-id')).toBe(true);
  });

  it('surfaces browse authorization errors and does not invent empty results', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 403 }));
    render(<KnowledgePage locale="en" />);
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByText(/not authorized/)).toBeTruthy();
    expect(screen.queryByText('No documents match this folder and tag selection.')).toBeNull();
  });

  it('retries the exact failed browse page without resetting its offset', async () => {
    const browseUrls: string[] = [];
    let browseCount = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      const parsed = new URL(url, 'http://localhost');
      if (parsed.pathname.endsWith('/folders')) return foldersResponse(parsed.searchParams.get('path') ?? '');
      if (parsed.pathname.endsWith('/browse')) {
        browseUrls.push(url);
        browseCount += 1;
        if (browseCount === 2) return new Response('{}', { status: 503 });
        const offset = Number(parsed.searchParams.get('offset'));
        return new Response(JSON.stringify({ status: 'ok', path: '', tag_facets: [], items: [], total: 40,
          total_complete: true, offset, limit: 20, next_offset: offset === 0 ? 20 : null,
          scan: { entries: 40, complete: true } }), { status: 200 });
      }
      return new Response('{}', { status: 404 });
    });
    render(<KnowledgePage locale="en" />);
    await screen.findByRole('button', { name: 'Next' });
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(browseCount).toBe(3));
    expect(new URL(browseUrls[1], 'http://localhost').searchParams.get('offset')).toBe('20');
    expect(new URL(browseUrls[2], 'http://localhost').searchParams.get('offset')).toBe('20');
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
    expect((await screen.findAllByRole('alert')).some((alert) => /request was not authorized/.test(alert.textContent ?? ''))).toBe(true);
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
