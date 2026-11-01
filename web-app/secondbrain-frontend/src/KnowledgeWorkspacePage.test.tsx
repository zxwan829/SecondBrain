import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { KnowledgeWorkspacePage } from './KnowledgeWorkspacePage';

const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const folders = (collection = 'notes', path = '', values: Array<{ name: string; path: string }> = []) => ({
  source_kind: collection === 'drafts' ? 'drafts' : 'notes', collection, path, status: 'ok', folders: values,
  scan: { entries: values.length, complete: true },
});
const browse = (collection = 'notes', path = '', items: Array<{ path: string; title: string }> = []) => ({
  source_kind: collection === 'drafts' ? 'drafts' : 'notes', collection, path, status: 'ok', items,
  total: items.length, total_complete: true, offset: 0, limit: 20, next_offset: null,
  scan: { entries: items.length, bytes: 20, complete: true },
});

describe('Knowledge unified read-only workspace', () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('keeps Knowledge, authorized Notes and Drafts as separate sources and reads Chinese Markdown without writes', async () => {
    const calls: Array<{ url: string; method: string; cache?: RequestCache }> = [];
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input); calls.push({ url, method: init?.method ?? 'GET', cache: init?.cache });
      if (url === '/api/notes') return response({ collections: [{ id: 'notes', kind: 'authorized' }, { id: 'drafts', kind: 'drafts' }] });
      if (url.startsWith('/api/notes/notes/folders')) return response(folders());
      if (url.startsWith('/api/notes/notes/browse')) return response(browse('notes', '', [{ path: '研究/中文笔记.md', title: '合成中文笔记' }]));
      if (url.startsWith('/api/notes/notes/') && !url.includes('/folders') && !url.includes('/browse')) return response({ collection: 'notes', path: '研究/中文笔记.md', content: '---\ntags: [保留]\n---\n# 合成中文笔记', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] });
      if (url.startsWith('/api/notes/drafts/folders')) return response(folders('drafts'));
      if (url.startsWith('/api/notes/drafts/browse')) return response(browse('drafts', '', [{ path: '123e4567-e89b-12d3-a456-426614174000', title: '合成草稿' }]));
      return response({}, 404);
    });
    render(<KnowledgeWorkspacePage locale="zh-CN" onGlobalAuthFailure={vi.fn()} />);
    expect(screen.getByRole('button', { name: '知识库' }).getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: '普通笔记' }));
    fireEvent.click(await screen.findByRole('button', { name: /合成中文笔记/ }));
    await screen.findByRole('article');
    expect(screen.getByRole('article').textContent).toContain('tags: [保留]');
    fireEvent.click(screen.getByRole('button', { name: '草稿' }));
    expect(await screen.findByRole('button', { name: /合成草稿/ })).toBeTruthy();
    expect(calls.every((call) => call.method === 'GET')).toBe(true);
    expect(calls.filter((call) => call.url.startsWith('/api/notes/')).every((call) => call.cache === 'no-store')).toBe(true);
    expect(calls.filter((call) => call.url.includes('/api/knowledge/')).every((call) => call.url.includes('/folders') || call.url.includes('/browse'))).toBe(true);
    expect(calls.some((call) => call.url.includes('/api/notes/notes/') && decodeURIComponent(call.url).includes('研究/中文笔记.md'))).toBe(true);
    expect(setItem).not.toHaveBeenCalled();
  });

  it.each([403, 503])('clears the selected source after HTTP %i and never retains stale content', async (deniedStatus) => {
    let failRead = false;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url === '/api/notes') return response({ collections: [{ id: 'notes', kind: 'authorized' }] });
      if (url.includes('/folders')) return response(folders());
      if (url.includes('/browse')) return response(browse('notes', '', [{ path: 'private-test.md', title: 'Old content' }]));
      if (url.endsWith('/private-test.md')) return failRead ? response({ detail: 'denied' }, deniedStatus)
        : response({ collection: 'notes', path: 'private-test.md', content: 'old-body-marker', etag: 'b'.repeat(64), read_only: true, safety_reasons: [] });
      return response({}, 404);
    });
    render(<KnowledgeWorkspacePage locale="en" onGlobalAuthFailure={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Notes' }));
    fireEvent.click(await screen.findByRole('button', { name: /Old content/ }));
    expect(await screen.findByText('old-body-marker')).toBeTruthy();
    failRead = true;
    fireEvent.click(screen.getByRole('button', { name: /Old content/ }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.queryByText('old-body-marker')).toBeNull();
    expect(screen.queryByRole('button', { name: /Old content/ })).toBeNull();
    expect(screen.getByText(deniedStatus === 403 ? /not authorized/i : /temporarily unavailable/i)).toBeTruthy();
  });

  it('expires the full App session on 401 and ignores a late response from a superseded folder', async () => {
    const onGlobalAuthFailure = vi.fn();
    let releaseOld!: (value: Response) => void;
    let holdChild = false;
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input);
      if (url === '/api/notes') return Promise.resolve(response({ collections: [{ id: 'notes', kind: 'authorized' }] }));
      if (url.includes('/folders')) {
        const path = new URL(url, 'http://localhost').searchParams.get('path') ?? '';
        return Promise.resolve(response(folders('notes', path, path ? [] : [{ name: 'Child', path: 'Child' }])));
      }
      if (url.includes('/browse?path=Child')) return holdChild ? new Promise<Response>((resolve) => { releaseOld = resolve; })
        : Promise.resolve(response(browse('notes', 'Child', [{ path: 'Child/stale.md', title: 'Stale child' }])));
      if (url.includes('/browse')) return Promise.resolve(response(browse('notes')));
      return Promise.resolve(response({ detail: 'expired' }, 401));
    });
    render(<KnowledgeWorkspacePage locale="en" onGlobalAuthFailure={onGlobalAuthFailure} />);
    fireEvent.click(screen.getByRole('button', { name: 'Notes' }));
    await screen.findByRole('button', { name: 'Child' });
    holdChild = true;
    fireEvent.click(screen.getByRole('button', { name: 'Child' }));
    await waitFor(() => expect(releaseOld).toBeTruthy());
    fireEvent.click(screen.getByRole('navigation', { name: 'Current folder' }).querySelector('button')!);
    await waitFor(() => expect(screen.queryByText('Stale child')).toBeNull());
    await act(async () => { releaseOld(response(browse('notes', 'Child', [{ path: 'Child/stale.md', title: 'Stale child' }]))); });
    expect(screen.queryByText('Stale child')).toBeNull();
    holdChild = false;
    fireEvent.click(screen.getByRole('button', { name: 'Child' }));
    fireEvent.click(await screen.findByRole('button', { name: /Stale child/ }));
    // A 401 from a selected document invalidates the whole App session.
    await waitFor(() => expect(onGlobalAuthFailure).toHaveBeenCalled());
  });
});
