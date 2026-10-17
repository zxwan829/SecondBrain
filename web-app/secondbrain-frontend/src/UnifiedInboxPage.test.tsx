import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { UnifiedInboxPage } from './UnifiedInboxPage';
import { suggestInboxClassification } from './unified-inbox';

const noteId = 'synthetic-note-1';
let created = false;
let retryCalls = 0;

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function ok(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  created = false;
  retryCalls = 0;
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === '/api/inbox') return ok({ items: [
      { capture_id: 'capture-synthetic-1', raw_path: 'raw/meeting.md', review_path: null,
        status: 'completed', source_type: 'synthetic', input_type: 'markdown',
        captured_at: '2026-10-17T10:00:00Z', display_filename: 'Sprint meeting.md',
        content_preview: '# 会议纪要\n\n项目：SecondBrain\n讨论 Inbox 审批流程。 #roadmap #SecondBrain', source_url: 'https://example.test/source', derived_source_url: 'https://cdn.example.test/source.md' },
      { capture_id: 'capture-partial-1', raw_path: 'raw/partial.txt', status: 'partial_success', source_type: 'synthetic', input_type: 'text',
        captured_at: '2026-10-17T09:00:00Z', display_filename: 'Partial source.txt', content_preview: 'Partial processing source',
        error: { code: 'processing_failed', message: 'Synthetic processor timed out' } },
      { capture_id: 'capture-pdf-1', raw_path: 'raw/doc.pdf', status: 'completed', source_type: 'synthetic', input_type: 'pdf', display_filename: 'document.pdf' },
      { capture_id: 'capture-image-1', raw_path: 'raw/picture.png', status: 'completed', source_type: 'synthetic', input_type: 'png', display_filename: 'picture.png' },
      { capture_id: 'capture-audio-1', raw_path: 'raw/clip.mp3', status: 'completed', source_type: 'synthetic', input_type: 'mp3', display_filename: 'clip.mp3' },
    ] });
    if (url === '/api/automation/organize/status') return ok({ execution_available: true, blocked_reason: '' });
    if (url === '/api/automation/organize/run') return ok({ status: 'completed', draft_count: 1 });
    if (url === '/api/inbox/capture-synthetic-1/preview') return new Response('Complete synthetic original preview', { status: 200 });
    if (url === '/api/capture/capture-partial-1/retry') { retryCalls += 1; return ok({ status: 'processing' }); }
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
      content: '# 新建合成会议\n\n讨论 Inbox 审批。 #roadmap #SecondBrain\n', etag: 'synthetic-etag', read_only: false, safety_reasons: [] });
    return ok({ detail: `Unexpected request ${url}` }, 404);
  }));
});

describe('UnifiedInboxPage', () => {
  it('uses a fixed synthetic vocabulary, withholds new tags and preserves manual corrections', () => {
    const first = suggestInboxClassification('会议纪要 #SecondBrain #roadmap', 'Sprint meeting.md');
    expect(first.type).toBe('会议纪要');
    expect(first.typeIsStandard).toBe(true);
    expect(first.tags).toEqual(['SecondBrain']);
    expect(first.newTagCandidates).toEqual(['roadmap']);
    expect(first.tags).not.toContain('待整理');

    const corrected = suggestInboxClassification('头脑风暴 #SecondBrain #roadmap', 'Notes', ['SecondBrain'], '日记');
    expect(corrected.type).toBe('日记');
    expect(corrected.reason).toContain('手动修正');
    expect(corrected.tags).toEqual([]);
    expect(corrected.newTagCandidates).toEqual(['roadmap']);
  });

  it('collects Notes drafts and Capture sources in one view and approves mock suggestions item by item without changing originals', async () => {
    const request = vi.mocked(fetch);
    render(<UnifiedInboxPage locale="zh-CN" onReview={vi.fn()} showSyntheticCaptureDemo />);

    expect(await screen.findByRole('heading', { name: 'Sprint meeting.md' })).toBeTruthy();
    const captureCard = screen.getByRole('heading', { name: 'Sprint meeting.md' }).closest('article') as HTMLElement;
    expect(captureCard.textContent).toContain('raw/meeting.md');
    fireEvent.click(within(captureCard).getByRole('button', { name: '预览与详情' }));
    expect(await screen.findByText('Complete synthetic original preview')).toBeTruthy();
    expect(screen.getByText('https://example.test/source')).toBeTruthy();
    expect(screen.getByText('https://cdn.example.test/source.md')).toBeTruthy();
    fireEvent.click(screen.getByRole('dialog').querySelector('.capture-close')!);
    const partialCard = screen.getByRole('heading', { name: 'Partial source.txt' }).closest('article') as HTMLElement;
    expect(partialCard.textContent).toContain('处理超时；原始文件已保留，可以重试。');
    fireEvent.click(within(partialCard).getByRole('button', { name: '重试处理' }));
    await waitFor(() => expect(retryCalls).toBe(1));
    fireEvent.click(screen.getByRole('button', { name: '立即整理' }));
    expect(await screen.findByText(/整理完成，新增 1 条 Review 草稿/)).toBeTruthy();
    const pdfCard = screen.getByRole('heading', { name: 'document.pdf' }).closest('article') as HTMLElement;
    fireEvent.click(within(pdfCard).getByRole('button', { name: '预览与详情' }));
    expect(screen.getByRole('link', { name: '在新标签页预览 PDF' })).toBeTruthy();
    fireEvent.click(screen.getByRole('dialog').querySelector('.capture-close')!);
    const imageCard = screen.getByRole('heading', { name: 'picture.png' }).closest('article') as HTMLElement;
    fireEvent.click(within(imageCard).getByRole('button', { name: '预览与详情' }));
    expect(screen.getByRole('img', { name: 'picture.png' })).toBeTruthy();
    fireEvent.click(screen.getByRole('dialog').querySelector('.capture-close')!);
    const audioCard = screen.getByRole('heading', { name: 'clip.mp3' }).closest('article') as HTMLElement;
    fireEvent.click(within(audioCard).getByRole('button', { name: '预览与详情' }));
    expect(document.querySelector('audio')?.getAttribute('src')).toContain('/preview');
    fireEvent.click(screen.getByRole('dialog').querySelector('.capture-close')!);
    fireEvent.click(screen.getByRole('button', { name: '添加合成 Capture 示例' }));
    expect(await screen.findByRole('heading', { name: '合成会议输入.md' })).toBeTruthy();
    const demoCard = screen.getByRole('heading', { name: '合成会议输入.md' }).closest('article') as HTMLElement;
    expect(demoCard.textContent).toContain('synthetic://capture-demo/meeting.md');

    fireEvent.change(screen.getByLabelText('标题'), { target: { value: '新建合成会议' } });
    fireEvent.change(screen.getByLabelText('正文'), { target: { value: '讨论 Inbox 审批。 #roadmap #SecondBrain' } });
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
    expect(proposals).toHaveLength(5);
    expect((proposals[0] as HTMLInputElement).value).toMatch(/会议纪要/);
    expect(within(noteCard).getByText(/需经 Issue #55 词库审批的新词候选：roadmap/)).toBeTruthy();
    expect(within(noteCard).queryByText('待整理')).toBeNull();

    fireEvent.change(proposals[0], { target: { value: '头脑风暴' } });
    fireEvent.click(within(noteCard).getByRole('button', { name: '重新生成 Mock 建议（保留手动修正）' }));
    expect((within(noteCard).getAllByLabelText('可编辑建议')[0] as HTMLInputElement).value).toBe('头脑风暴');
    const tagsInput = within(noteCard).getAllByLabelText('可编辑建议')[1] as HTMLTextAreaElement;
    expect(tagsInput.value).toContain('SecondBrain');
    fireEvent.change(tagsInput, { target: { value: '' } });
    fireEvent.click(within(noteCard).getByRole('button', { name: '重新生成 Mock 建议（保留手动修正）' }));
    expect((within(noteCard).getAllByLabelText('可编辑建议')[1] as HTMLTextAreaElement).value).toBe('');
    fireEvent.click(within(noteCard).getAllByRole('button', { name: '本页模拟同意（未执行）' })[0]);
    expect(await within(noteCard).findByText(/未提交、未排队、未执行/)).toBeTruthy();
    fireEvent.click(within(noteCard).getAllByRole('button', { name: '拒绝' })[1]);
    expect(await within(noteCard).findByText('已拒绝；原始内容保留。')).toBeTruthy();
    fireEvent.click(within(noteCard).getAllByRole('button', { name: '本页模拟同意（未执行）' })[0]);
    await waitFor(() => expect(within(noteCard).getAllByRole('status').length).toBeGreaterThanOrEqual(2));

    expect(request.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(false);
    expect(request.mock.calls.some(([url]) => /\/api\/(journal|promote|capture\/text|tasks)/.test(String(url)))).toBe(false);
    expect(request.mock.calls.filter(([url, init]) => url === '/api/notes' && init?.method === 'POST')).toHaveLength(1);
    expect(request.mock.calls.some(([url, init]) => String(url).includes('/api/automation/organize/run') && init?.method === 'POST')).toBe(true);
  });

  it('keeps Capture available when Notes permission is denied and reports a denied draft write', async () => {
    const request = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/inbox') return ok({ items: [{ capture_id: 'capture-1', raw_path: 'raw/source.txt', status: 'completed', content_preview: 'synthetic capture' }] });
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
