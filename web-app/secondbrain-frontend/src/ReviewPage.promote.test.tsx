import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ReviewPage } from './App';

const review = {
  review_path: '10-Review/synthetic-review.md', review_sha256: 'a'.repeat(64),
  target_filename: 'Knowledge/synthetic-review.md', title: 'Synthetic Review', status: 'pending',
  captured_at: '2026-10-18T00:00:00Z', content: '---\nsource_type: text\n---\n# Synthetic Review body',
};
const preview = {
  preview_id: 'preview-1', request_id: 'request-1', expires_at: '2099-01-01T00:00:00Z',
  source_sha256: review.review_sha256, target_filename: review.target_filename,
  target_precondition: { exists: false }, source_markdown: review.content,
  projected_markdown: '# Exact projected Markdown', output_sha256: 'b'.repeat(64), change_summary: 'No existing target will be replaced.',
};
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState({}, '', '/');
});

function mockReviewApi() {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input); calls.push({ url, init });
    if (url === '/api/promote/review/items') return json({ items: [review] });
    if (url === '/api/promote/review/items/10-Review/synthetic-review.md') return json(review);
    if (url === '/api/promote/status') return json({ promote_enabled: true });
    if (url === '/api/promote/review/preview') return json(preview);
    if (url === '/api/promote/review/defer') return json({ status: 'deferred' });
    return json({ detail: 'synthetic unmatched route' }, 404);
  });
  return calls;
}

describe('Review page controlled Promote wiring', () => {
  it('loads only the Review list by default and reads a detail only after explicit selection', async () => {
    const calls = mockReviewApi();
    render(<ReviewPage locale="zh-CN" onBack={() => undefined} />);
    expect(await screen.findByRole('button', { name: /Synthetic Review/ })).toBeTruthy();
    await waitFor(() => expect(calls.some((call) => call.url === '/api/promote/status')).toBe(true));
    expect(calls.some((call) => call.url.startsWith('/api/promote/review/items/'))).toBe(false);
    expect(calls.some((call) => call.url.startsWith('/api/inbox'))).toBe(false);
    expect(screen.queryByText('Synthetic Review body')).toBeNull();
    expect(calls.some((call) => call.url.startsWith('/api/promote/review/preview'))).toBe(false);
    expect(calls.some((call) => call.url.startsWith('/api/promote/auth/'))).toBe(false);
    expect(calls.some((call) => call.url.includes('/api/promote/operations/'))).toBe(false);
    expect(calls.some((call) => call.url === '/api/promote/review/approve')).toBe(false);
    expect(screen.queryByRole('button', { name: '批准入库' })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /Synthetic Review/ }));
    expect(await screen.findByText('Synthetic Review body')).toBeTruthy();
    expect(await screen.findByRole('button', { name: '准备正式入库预览' })).toBeTruthy();
    expect(calls.some((call) => call.url.startsWith('/api/promote/review/preview'))).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: '准备正式入库预览' }));
    expect(await screen.findByLabelText('拟入库 Markdown 原文')).toBeTruthy();
    const previewCall = calls.find((call) => call.url === '/api/promote/review/preview');
    expect(previewCall).toBeTruthy();
    expect(JSON.parse(String(previewCall?.init?.body))).toEqual({
      review_path: review.review_path, review_sha256: review.review_sha256, target_filename: review.target_filename,
    });
    expect(calls.some((call) => call.url === '/api/promote/review/approve')).toBe(false);
  });

  it('keeps the independent defer action on its existing route', async () => {
    const calls = mockReviewApi();
    render(<ReviewPage locale="en" onBack={() => undefined} />);
    await screen.findByRole('button', { name: /Synthetic Review/ });
    fireEvent.click(screen.getByRole('button', { name: /Synthetic Review/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Defer' }));
    await waitFor(() => expect(calls.some((call) => call.url === '/api/promote/review/defer')).toBe(true));
    expect(calls.some((call) => call.url === '/api/promote/review/approve')).toBe(false);
  });

  it('aborts and ignores an older Review detail response after the user selects another source', async () => {
    const first = { ...review, review_path: '10-Review/synthetic-a.md', title: 'Synthetic Alpha', captured_at: '2026-10-18T00:01:00Z' };
    const second = { ...review, review_path: '10-Review/synthetic-b.md', title: 'Synthetic Beta', captured_at: '2026-10-18T00:00:00Z' };
    let finishFirst!: (response: Response) => void;
    const pendingFirst = new Promise<Response>((resolve) => { finishFirst = resolve; });
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input); calls.push(url);
      if (url === '/api/promote/review/items') return Promise.resolve(json({ items: [first, second] }));
      if (url === '/api/promote/review/items/10-Review/synthetic-a.md') return pendingFirst;
      if (url === '/api/promote/review/items/10-Review/synthetic-b.md') return Promise.resolve(json({ ...second, content: '# Synthetic Beta body' }));
      if (url === '/api/promote/status') return Promise.resolve(json({ promote_enabled: true }));
      return Promise.resolve(json({}, 404));
    });
    render(<ReviewPage locale="en" onBack={() => undefined} />);
    expect(calls).not.toContain('/api/promote/review/items/10-Review/synthetic-a.md');
    await screen.findByRole('button', { name: /Synthetic Alpha/ });
    fireEvent.click(screen.getByRole('button', { name: /Synthetic Alpha/ }));
    await waitFor(() => expect(calls).toContain('/api/promote/review/items/10-Review/synthetic-a.md'));
    fireEvent.click(screen.getByRole('button', { name: /Synthetic Beta/ }));
    expect(await screen.findByText('Synthetic Beta body')).toBeTruthy();
    expect(await screen.findByRole('button', { name: 'Prepare exact Promote preview' })).toBeTruthy();
    await act(async () => { finishFirst(json({ ...first, content: '# Synthetic Alpha stale body' })); await pendingFirst; });
    expect(screen.getByText('Synthetic Beta body')).toBeTruthy();
    expect(screen.queryByText('Synthetic Alpha stale body')).toBeNull();
    expect(calls.some((url) => url.startsWith('/api/promote/review/preview'))).toBe(false);
  });

  it('clears the previous detail immediately and keeps it unavailable when the newly selected Review fails', async () => {
    const first = { ...review, review_path: '10-Review/synthetic-a.md', title: 'Synthetic Alpha', content: '# Synthetic Alpha body' };
    const second = { ...review, review_path: '10-Review/synthetic-b.md', title: 'Synthetic Beta' };
    let failSecond!: (response: Response) => void;
    const pendingSecond = new Promise<Response>((resolve) => { failSecond = resolve; });
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input); calls.push(url);
      if (url === '/api/promote/review/items') return Promise.resolve(json({ items: [first, second] }));
      if (url === '/api/promote/review/items/10-Review/synthetic-a.md') return Promise.resolve(json(first));
      if (url === '/api/promote/review/items/10-Review/synthetic-b.md') return pendingSecond;
      if (url === '/api/promote/status') return Promise.resolve(json({ promote_enabled: true }));
      return Promise.resolve(json({}, 404));
    });
    render(<ReviewPage locale="en" onBack={() => undefined} />);
    await screen.findByRole('button', { name: /Synthetic Alpha/ });
    fireEvent.click(screen.getByRole('button', { name: /Synthetic Alpha/ }));
    expect(await screen.findByText('Synthetic Alpha body')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Defer' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Synthetic Beta/ }));

    expect(screen.queryByText('Synthetic Alpha body')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Defer' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Prepare exact Promote preview' })).toBeNull();
    expect(screen.getByText('Loading selected Review…')).toBeTruthy();

    await act(async () => { failSecond(json({ detail: 'synthetic failure' }, 500)); await pendingSecond; });
    expect(screen.queryByText('Synthetic Alpha body')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Defer' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Prepare exact Promote preview' })).toBeNull();
    expect(calls.some((url) => url === '/api/promote/review/defer')).toBe(false);
    expect(calls.some((url) => url === '/api/promote/review/preview')).toBe(false);
    expect(calls.some((url) => url === '/api/promote/review/confirm')).toBe(false);
  });

  it('aborts and ignores the Review list response when leaving the page', async () => {
    let finishList!: (response: Response) => void;
    const pendingList = new Promise<Response>((resolve) => { finishList = resolve; });
    let listSignal: AbortSignal | undefined;
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input); calls.push(url);
      if (url === '/api/promote/review/items') { listSignal = init?.signal as AbortSignal | undefined; return pendingList; }
      return Promise.resolve(json({ promote_enabled: false }));
    });
    const page = render(<ReviewPage locale="en" onBack={() => undefined} />);
    await waitFor(() => expect(calls).toContain('/api/promote/review/items'));
    page.unmount();
    expect(listSignal?.aborted).toBe(true);
    await act(async () => { finishList(json({ items: [review] })); await pendingList; });
    expect(calls).not.toContain('/api/promote/status');
    expect(calls.some((url) => url.startsWith('/api/promote/review/items/') && url !== '/api/promote/review/items')).toBe(false);
  });

  it('ignores a late detail response after a deep-link change reloads the list', async () => {
    const first = { ...review, review_path: '10-Review/deep-a.md', title: 'Deep A' };
    const second = { ...review, review_path: '10-Review/deep-b.md', title: 'Deep B' };
    let finishFirst!: (response: Response) => void;
    const pendingFirst = new Promise<Response>((resolve) => { finishFirst = resolve; });
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input); calls.push(url);
      if (url === '/api/promote/review/items') return Promise.resolve(json({ items: [first, second] }));
      if (url === '/api/promote/review/items/10-Review/deep-a.md') return pendingFirst;
      if (url === '/api/promote/review/items/10-Review/deep-b.md') return Promise.resolve(json({ ...second, content: '# Current Deep B' }));
      if (url === '/api/promote/status') return Promise.resolve(json({ promote_enabled: false }));
      return Promise.resolve(json({}, 404));
    });
    const page = render(<ReviewPage locale="en" initialReviewPath={first.review_path} onBack={() => undefined} />);
    await waitFor(() => expect(calls).toContain('/api/promote/review/items/10-Review/deep-a.md'));
    page.rerender(<ReviewPage locale="en" initialReviewPath={second.review_path} onBack={() => undefined} />);
    expect(await screen.findByText('Current Deep B')).toBeTruthy();
    await act(async () => { finishFirst(json({ ...first, content: '# Stale Deep A' })); await pendingFirst; });
    expect(screen.getByText('Current Deep B')).toBeTruthy();
    expect(screen.queryByText('Stale Deep A')).toBeNull();
  });
});
