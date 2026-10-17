import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { UnifiedInboxPage } from './UnifiedInboxPage';

const noteId = 'synthetic-note-1';
let created = false;

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function ok(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  created = false;
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === '/api/inbox?limit=100') return ok({ items: [{
      capture_id: 'capture-synthetic-1', raw_path: 'raw/meeting.md', review_path: null,
      status: 'completed', source_type: 'synthetic', input_type: 'markdown',
      captured_at: '2026-10-17T10:00:00Z', display_filename: 'Sprint meeting.md',
      content_preview: '# 会议纪要\n\n项目：SecondBrain\n讨论 Inbox 审批流程。 #roadmap',
    }] });
    if (url === '/api/notes') {
      if (init?.method === 'POST') {
        created = true;
        return ok({ collection: 'drafts', path: noteId, content: JSON.parse(String(init.body)).content,
          etag: 'synthetic-etag', read_only: false, safety_reasons: [] });
      }
      return ok({ collections: [{ id: 'drafts', kind: 'drafts' }, { id: 'personal', kind: 'authorized' }] });
    }
    if (url === '/api/notes/drafts') return ok({ items: created ? [{ path: noteId, title: '新建合成会议' }] : [] });
    if (url === `/api/notes/drafts/${noteId}`) return ok({ collection: 'drafts', path: noteId,
      content: '# 新建合成会议\n\n讨论 Inbox 审批。 #roadmap\n', etag: 'synthetic-etag', read_only: false, safety_reasons: [] });
    return ok({ detail: `Unexpected request ${url}` }, 404);
  }));
});

describe('UnifiedInboxPage', () => {
  it('collects Notes drafts and Capture sources in one view and approves mock suggestions item by item without changing originals', async () => {
    const request = vi.mocked(fetch);
    render(<UnifiedInboxPage locale="zh-CN" onReview={vi.fn()} showSyntheticCaptureDemo />);

    expect(await screen.findByRole('heading', { name: 'Sprint meeting.md' })).toBeTruthy();
    const captureCard = screen.getByRole('heading', { name: 'Sprint meeting.md' }).closest('article') as HTMLElement;
    expect(captureCard.textContent).toContain('raw/meeting.md');
    fireEvent.click(screen.getByRole('button', { name: '添加合成 Capture 示例' }));
    expect(await screen.findByRole('heading', { name: '合成会议输入.md' })).toBeTruthy();
    const demoCard = screen.getByRole('heading', { name: '合成会议输入.md' }).closest('article') as HTMLElement;
    expect(demoCard.textContent).toContain('synthetic://capture-demo/meeting.md');

    fireEvent.change(screen.getByLabelText('标题'), { target: { value: '新建合成会议' } });
    fireEvent.change(screen.getByLabelText('正文'), { target: { value: '讨论 Inbox 审批。 #roadmap' } });
    const createButton = screen.getByRole('button', { name: '新建并收录' });
    fireEvent.click(createButton);
    fireEvent.click(createButton);
    const note = await screen.findByText('新建合成会议');
    expect(note).toBeTruthy();
    const noteCard = note.closest('article') as HTMLElement;
    expect(noteCard.dataset.source).toBe('notes');
    expect(noteCard.textContent).toContain(`drafts/${noteId}`);

    fireEvent.click(within(noteCard).getByRole('button', { name: '生成确定性 Mock 建议' }));
    const proposals = within(noteCard).getAllByLabelText('可编辑建议');
    expect(proposals).toHaveLength(4);
    expect((proposals[0] as HTMLTextAreaElement).value).toMatch(/会议纪要/);
    expect(within(noteCard).getByText(/仅审批此项建议/)).toBeTruthy();

    fireEvent.change(proposals[0], { target: { value: '头脑风暴\nSecondBrain, roadmap' } });
    fireEvent.click(within(noteCard).getAllByRole('button', { name: '批准此建议' })[0]);
    expect(await within(noteCard).findByText(/已批准待后续执行/)).toBeTruthy();
    fireEvent.click(within(noteCard).getAllByRole('button', { name: '拒绝' })[1]);
    expect(await within(noteCard).findByText('已拒绝；原始内容保留。')).toBeTruthy();
    fireEvent.click(within(noteCard).getAllByRole('button', { name: '批准此建议' })[0]);
    await waitFor(() => expect(within(noteCard).getAllByRole('status').length).toBeGreaterThanOrEqual(2));

    expect(request.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(false);
    expect(request.mock.calls.some(([url]) => /\/api\/(journal|promote|capture\/text|tasks)/.test(String(url)))).toBe(false);
    expect(request.mock.calls.filter(([url, init]) => url === '/api/notes' && init?.method === 'POST')).toHaveLength(1);
  });

  it('keeps Capture available when Notes permission is denied and reports a denied draft write', async () => {
    const request = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/inbox?limit=100') return ok({ items: [{ capture_id: 'capture-1', raw_path: 'raw/source.txt', status: 'completed', content_preview: 'synthetic capture' }] });
      if (url === '/api/notes') return init?.method === 'POST'
        ? ok({ detail: 'notes.write denied' }, 403)
        : ok({ detail: 'notes.read denied' }, 403);
      return ok({}, 404);
    });
    vi.stubGlobal('fetch', request);
    render(<UnifiedInboxPage locale="zh-CN" onReview={vi.fn()} showSyntheticCaptureDemo={false} />);
    expect(await screen.findByRole('heading', { name: 'source.txt' })).toBeTruthy();
    expect(await screen.findByText(/当前 Core 会话或配置未开放 Notes/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText('标题'), { target: { value: '未授权笔记' } });
    fireEvent.change(screen.getByLabelText('正文'), { target: { value: '不可写入' } });
    fireEvent.click(screen.getByRole('button', { name: '新建并收录' }));
    expect((await screen.findByRole('alert')).textContent).toContain('notes.write denied');
    expect(request.mock.calls.some(([url]) => /\/api\/(journal|promote|capture\/text|tasks)/.test(String(url)))).toBe(false);
  });
});
