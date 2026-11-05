import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { UnifiedInboxPage } from './UnifiedInboxPage';
import { suggestInboxClassification } from './unified-inbox';

const noteId = 'synthetic-note-1';
const singleDraftId = 'ec5467a3-3087-45a2-befd-74038d08830c';
let created = false;
let savedProposals: Array<Record<string, any>> = [];
let savedManualType = '';
let savedRemovedTags: string[] = [];

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function ok(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  created = false;
  savedProposals = [];
  savedManualType = '';
  savedRemovedTags = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.startsWith('/api/inbox/proposals?')) return ok({ proposals: savedProposals });
    if (url === '/api/inbox/proposals' && init?.method === 'POST') {
      const source = JSON.parse(String(init.body));
      const kinds = ['type', 'tags', 'journal', 'review', 'project'];
      savedProposals = kinds.map((kind) => {
        const original = kind === 'type' ? { value: '会议纪要', vocabulary_values: ['日记', '笔记', '头脑风暴', '摘要', '会议纪要'] } : kind === 'tags' ? { values: ['SecondBrain'], unknown_candidates: ['roadmap'], vocabulary_values: ['SecondBrain', 'CRM'] } : { value: '合成建议' };
        const current = kind === 'type' && savedManualType ? { ...original, value: savedManualType }
          : kind === 'tags' ? { ...original, values: (Array.isArray(original.values) ? original.values : []).filter((tag: string) => !savedRemovedTags.includes(tag)), removed_by_user: savedRemovedTags }
            : original;
        return { proposal_id: `proposal-${kind}`, ...source, kind, status: 'suggested', version: 1, source_version: 'synthetic-etag', target_execution_status: 'not_executed', suggestion: { original, current }, history: [{ event: 'suggested', actor: 'synthetic-user', at: '2026-10-18T00:00:00Z', version: 1 }] };
      });
      return ok({ proposals: savedProposals, status: 'created' });
    }
    if (/^\/api\/inbox\/proposals\/proposal-[^/]+\/history$/.test(url)) {
      const proposal = savedProposals.find((item) => url.includes(item.proposal_id));
      return proposal ? ok({ proposal, history: proposal.history }) : ok({ detail: 'proposal not found' }, 404);
    }
    if (url.startsWith('/api/inbox/proposals/proposal-') && url.endsWith('/execution-preview')) {
      const body = JSON.parse(String(init?.body || '{}'));
      const proposal = savedProposals.find((item) => url.includes(item.proposal_id));
      return ok({ status: 'ready', proposal_id: 'proposal-journal', kind: 'journal', proposal_version: 2,
        vocabulary_version: 4, source_summary: { source_kind: proposal?.source_kind || 'capture', source_ref: proposal?.path || 'capture-synthetic-1', source_version: 'synthetic-etag', source_content_sha256: 'a'.repeat(64) },
        target_action: 'journal.append', target: { date: body.target_date || '2026-10-18', text: body.target_text || '合成来源正文' }, preview_sha256: 'b'.repeat(64) });
    }
    if (url.startsWith('/api/inbox/proposals/proposal-') && url.endsWith('/execute')) {
      const proposal = savedProposals.find((item) => url.includes(item.proposal_id));
      if (!proposal) return ok({ detail: 'proposal not found' }, 404);
      proposal.execution = { status: 'executed', target_uri: 'journal:2026-10-18' };
      proposal.target_execution_status = 'executed';
      return ok({ proposal, duplicate: false });
    }
    if (url.startsWith('/api/inbox/proposals/proposal-') && url.endsWith('/decision')) {
      const proposal = savedProposals.find((item) => url.includes(item.proposal_id));
      if (proposal) { proposal.status = JSON.parse(String(init?.body)).decision; proposal.version += 1; }
      return ok({ proposal });
    }
    if (url.startsWith('/api/inbox/proposals/proposal-') && init?.method === 'PUT') {
      const proposal = savedProposals.find((item) => url.includes(item.proposal_id));
      if (proposal) {
        proposal.suggestion.current = JSON.parse(String(init.body)).suggestion;
        if (proposal.kind === 'type') savedManualType = proposal.suggestion.current.value;
        if (proposal.kind === 'tags') savedRemovedTags = proposal.suggestion.original.values.filter((tag: string) => !proposal.suggestion.current.values.includes(tag));
        proposal.version += 1;
      }
      return ok({ proposal });
    }
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
    if (url === `/api/notes/drafts/${noteId}` || url === `/api/notes/drafts/${singleDraftId}`) return ok({ collection: 'drafts', path: url.split('/').pop(),
      content: '# 新建合成会议\n\n讨论 Inbox 审批。 #roadmap #SecondBrain\n', etag: 'synthetic-etag', read_only: false, safety_reasons: [] });
    return ok({ detail: `Unexpected request ${url}` }, 404);
  }));
});

describe('UnifiedInboxPage', () => {
  it('cancels a superseded Inbox source load and ignores its late Capture response', async () => {
    const request = vi.mocked(fetch);
    const original = request.getMockImplementation()!;
    let finishInitial!: (response: Response) => void;
    let firstSignal: AbortSignal | undefined;
    let captureReads = 0;
    request.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === '/api/inbox?limit=100') {
        captureReads += 1;
        if (captureReads === 1) {
          firstSignal = init?.signal as AbortSignal | undefined;
          return new Promise<Response>((resolve) => { finishInitial = resolve; });
        }
        return ok({ items: [{ capture_id: 'capture-current', raw_path: 'raw/current.md', status: 'completed', display_filename: 'Current source.md' }] });
      }
      return original(input, init);
    });

    render(<UnifiedInboxPage locale="zh-CN" onReview={vi.fn()} showSyntheticCaptureDemo={false} />);
    await waitFor(() => expect(firstSignal).toBeTruthy());
    window.dispatchEvent(new Event('sb-inbox-refresh'));
    expect(await screen.findByRole('heading', { name: 'Current source.md' })).toBeTruthy();
    expect(firstSignal?.aborted).toBe(true);

    await act(async () => { finishInitial(ok({ items: [{ capture_id: 'capture-stale', raw_path: 'raw/stale.md', status: 'completed', display_filename: 'Stale source.md' }] })); });
    expect(screen.getByRole('heading', { name: 'Current source.md' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Stale source.md' })).toBeNull();
  });

  it('aborts an older proposal read and ignores its late response after a newer approval state loads', async () => {
    const request = vi.mocked(fetch);
    const original = request.getMockImplementation()!;
    let finishInitial!: (response: Response) => void;
    let firstSignal: AbortSignal | undefined;
    let proposalReadCount = 0;
    request.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.startsWith('/api/inbox/proposals?')) {
        proposalReadCount += 1;
        if (proposalReadCount === 1) {
          firstSignal = init?.signal as AbortSignal | undefined;
          return new Promise<Response>((resolve) => { finishInitial = resolve; });
        }
        return ok({ proposals: savedProposals });
      }
      if (url === '/api/inbox/proposals' && init?.method === 'POST') {
        const response = await original(input, init);
        savedProposals = savedProposals.map((record) => record.kind === 'journal' ? { ...record, status: 'approved_recorded' } : record);
        return response;
      }
      return original(input, init);
    });

    render(<UnifiedInboxPage locale="zh-CN" onReview={vi.fn()} showSyntheticCaptureDemo={false} singleSourceMode singleSource={{ kind: 'notes', collection: 'drafts', path: singleDraftId }} />);
    const card = (await screen.findByRole('heading', { name: '新建合成会议' })).closest('article') as HTMLElement;
    await waitFor(() => expect(firstSignal).toBeTruthy());
    fireEvent.click(within(card).getByRole('button', { name: '生成确定性 Mock 建议' }));

    expect(await within(card).findByRole('button', { name: '准备目标预览' })).toBeTruthy();
    expect(firstSignal?.aborted).toBe(true);
    await act(async () => { finishInitial(ok({ proposals: [] })); });

    expect(within(card).getByRole('button', { name: '准备目标预览' })).toBeTruthy();
    expect(within(card).getByText(/决定已记录到 Core/)).toBeTruthy();
  });

  it('keeps every request bound to one Draft through creation, approval, preview, execution, history, and refresh', async () => {
    const request = vi.mocked(fetch);
    render(<UnifiedInboxPage locale="zh-CN" onReview={vi.fn()} showSyntheticCaptureDemo={false} singleSourceMode singleSource={{ kind: 'notes', collection: 'drafts', path: singleDraftId }} />);

    const sourceHeading = await screen.findByRole('heading', { name: '新建合成会议' });
    expect(sourceHeading.closest('article')?.textContent).toContain(`drafts/${singleDraftId}`);
    const card = sourceHeading.closest('article') as HTMLElement;
    expect(request.mock.calls.some(([url]) => String(url) === '/api/notes')).toBe(false);
    expect(request.mock.calls.some(([url]) => String(url) === '/api/notes/drafts')).toBe(false);
    expect(request.mock.calls.some(([url]) => String(url) === '/api/inbox?limit=100')).toBe(false);

    fireEvent.click(within(card).getByRole('button', { name: '生成确定性 Mock 建议' }));
    await within(card).findAllByRole('button', { name: '记录审批（不执行）' });
    const createRequest = request.mock.calls.find(([url, init]) => String(url) === '/api/inbox/proposals' && init?.method === 'POST');
    expect(JSON.parse(String(createRequest?.[1]?.body))).toEqual({ source_kind: 'notes', source_id: `drafts:${singleDraftId}`, collection: 'drafts', path: singleDraftId });
    expect(new Headers(createRequest?.[1]?.headers).get('Idempotency-Key')).toBeTruthy();

    const journal = card.querySelector('[data-proposal="journal"]') as HTMLElement;
    fireEvent.click(within(journal).getByRole('button', { name: '记录审批（不执行）' }));
    fireEvent.click(await within(journal).findByRole('button', { name: '准备目标预览' }));
    await within(journal).findByLabelText('目标正文（将按此内容写入）');
    fireEvent.click(within(journal).getByRole('button', { name: '确认并执行' }));
    expect(await within(journal).findByText(/已执行 · journal:2026-10-18/)).toBeTruthy();
    fireEvent.click(within(card).getByRole('button', { name: '查看 journal 审计历史' }));
    expect(await within(card).findByText(/suggested · 2026-10-18T00:00:00Z · v1/)).toBeTruthy();

    cleanup();
    request.mockClear();
    render(<UnifiedInboxPage locale="zh-CN" onReview={vi.fn()} showSyntheticCaptureDemo={false} singleSourceMode singleSource={{ kind: 'notes', collection: 'drafts', path: singleDraftId }} />);
    expect(await screen.findByRole('heading', { name: '新建合成会议' })).toBeTruthy();
    expect(await screen.findByText(/已执行 · journal:2026-10-18/)).toBeTruthy();
    expect(request.mock.calls.some(([url]) => String(url) === '/api/inbox?limit=100' || String(url) === '/api/notes' || String(url) === '/api/notes/drafts')).toBe(false);
    expect(request.mock.calls.every(([url]) => {
      const value = String(url);
      return value === `/api/notes/drafts/${singleDraftId}` || value.startsWith('/api/inbox/proposals?source_kind=notes&')
        || value === '/api/inbox/proposals' || /^\/api\/inbox\/proposals\/proposal-(type|tags|journal|review|project)(?:\/(decision|execution-preview|execute|history))?$/.test(value);
    })).toBe(true);
  });

  it('fails closed on a missing or malformed single Draft without requesting any source endpoint', async () => {
    const request = vi.mocked(fetch);
    render(<UnifiedInboxPage locale="zh-CN" onReview={vi.fn()} showSyntheticCaptureDemo={false} singleSourceMode singleSource={null} />);
    expect(await screen.findByText('必须提供有效的 Draft 来源；未加载任何收件箱来源。')).toBeTruthy();
    expect(request.mock.calls).toHaveLength(0);
  });

  it('does not query proposals when the exact Notes read returns a different Draft identity', async () => {
    const request = vi.mocked(fetch);
    const original = request.getMockImplementation()!;
    request.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === `/api/notes/drafts/${singleDraftId}`) return ok({ collection: 'drafts', path: '00000000-0000-4000-8000-000000000999', content: 'wrong source', etag: 'synthetic-etag', read_only: false, safety_reasons: [] });
      return original(input, init);
    });
    render(<UnifiedInboxPage locale="zh-CN" onReview={vi.fn()} showSyntheticCaptureDemo={false} singleSourceMode singleSource={{ kind: 'notes', collection: 'drafts', path: singleDraftId }} />);
    expect(await screen.findByText('Core 返回了其他 Draft；未展示任何收件箱来源。')).toBeTruthy();
    expect(request.mock.calls.some(([url]) => String(url).startsWith('/api/inbox/proposals'))).toBe(false);
    expect(screen.queryByRole('heading', { name: '新建合成会议' })).toBeNull();
  });

  it('reuses the same idempotency key and source payload after a transient proposal-create failure', async () => {
    const request = vi.mocked(fetch);
    const original = request.getMockImplementation()!;
    let failOnce = true;
    request.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === '/api/inbox/proposals' && init?.method === 'POST' && failOnce) {
        failOnce = false;
        return ok({ detail: 'synthetic transient failure' }, 503);
      }
      return original(input, init);
    });
    render(<UnifiedInboxPage locale="zh-CN" onReview={vi.fn()} showSyntheticCaptureDemo={false} singleSourceMode singleSource={{ kind: 'notes', collection: 'drafts', path: singleDraftId }} />);
    const card = (await screen.findByRole('heading', { name: '新建合成会议' })).closest('article') as HTMLElement;
    const suggest = within(card).getByRole('button', { name: '生成确定性 Mock 建议' });
    fireEvent.click(suggest);
    expect(await within(card).findByText('建议保存失败（HTTP 503）。')).toBeTruthy();
    fireEvent.click(suggest);
    await within(card).findAllByRole('button', { name: '记录审批（不执行）' });
    const posts = request.mock.calls.filter(([url, init]) => String(url) === '/api/inbox/proposals' && init?.method === 'POST');
    expect(posts).toHaveLength(2);
    expect(new Headers(posts[0][1]?.headers).get('Idempotency-Key')).toBe(new Headers(posts[1][1]?.headers).get('Idempotency-Key'));
    expect(posts.map(([, init]) => init?.body)).toEqual([JSON.stringify({ source_kind: 'notes', source_id: `drafts:${singleDraftId}`, collection: 'drafts', path: singleDraftId }), JSON.stringify({ source_kind: 'notes', source_id: `drafts:${singleDraftId}`, collection: 'drafts', path: singleDraftId })]);
  });

  it('hides all proposals if the exact-source GET returns a different source binding', async () => {
    const request = vi.mocked(fetch);
    const original = request.getMockImplementation()!;
    request.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).startsWith('/api/inbox/proposals?')) return ok({ proposals: [{ proposal_id: 'proposal-other', source_kind: 'notes', source_id: 'drafts:other', collection: 'drafts', path: 'other', kind: 'journal', status: 'suggested', version: 1, source_version: 'synthetic-etag', target_execution_status: 'not_executed', suggestion: { original: { value: 'wrong' }, current: { value: 'wrong' } } }] });
      return original(input, init);
    });
    render(<UnifiedInboxPage locale="zh-CN" onReview={vi.fn()} showSyntheticCaptureDemo={false} singleSourceMode singleSource={{ kind: 'notes', collection: 'drafts', path: singleDraftId }} />);
    const card = (await screen.findByRole('heading', { name: '新建合成会议' })).closest('article') as HTMLElement;
    expect(await within(card).findByText(/Core 返回了绑定到其他来源的提案/)).toBeTruthy();
    expect(within(card).queryByLabelText('待人工逐项审批的建议')).toBeNull();
    expect((within(card).getByRole('button', { name: '生成确定性 Mock 建议' }) as HTMLButtonElement).disabled).toBe(true);
    expect(within(card).queryByRole('button', { name: '记录审批（不执行）' })).toBeNull();
  });

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
    const proposals = await within(noteCard).findAllByLabelText('可编辑建议');
    expect(proposals).toHaveLength(3);
    expect((within(noteCard).getByLabelText('建议类型（Core 集中词库）') as HTMLSelectElement).value).toBe('会议纪要');
    expect(within(noteCard).getByText('Core 词库中的有效标签')).toBeTruthy();
    expect(within(noteCard).getByText(/既有类型与 Core 词库中的有效标签无需逐条审批/)).toBeTruthy();
    expect(within(noteCard).getByText(/单独审批词库/)).toBeTruthy();

    fireEvent.change(within(noteCard).getByLabelText('建议类型（Core 集中词库）'), { target: { value: '头脑风暴' } });
    await waitFor(() => expect((within(noteCard).getByLabelText('建议类型（Core 集中词库）') as HTMLSelectElement).value).toBe('头脑风暴'));
    fireEvent.click(within(noteCard).getByRole('button', { name: '重新生成 Mock 建议（保留手动修正）' }));
    expect((within(noteCard).getByLabelText('建议类型（Core 集中词库）') as HTMLSelectElement).value).toBe('头脑风暴');
    const standardTag = within(noteCard).getByLabelText('SecondBrain') as HTMLInputElement;
    expect(standardTag.checked).toBe(true);
    fireEvent.click(standardTag);
    await waitFor(() => expect(standardTag.checked).toBe(false));
    fireEvent.click(within(noteCard).getByRole('button', { name: '重新生成 Mock 建议（保留手动修正）' }));
    expect((within(noteCard).getByLabelText('SecondBrain') as HTMLInputElement).checked).toBe(false);
    expect(within(noteCard).queryByRole('button', { name: '本页模拟同意（未执行）' })).toBeNull();
    fireEvent.click(within(noteCard).getAllByRole('button', { name: '记录审批（不执行）' })[0]);
    expect(await within(noteCard).findByText(/决定已记录到 Core/)).toBeTruthy();
    fireEvent.click(within(noteCard).getAllByRole('button', { name: '拒绝' })[1]);
    expect(await within(noteCard).findByText('已拒绝；原始内容保留。')).toBeTruthy();
    fireEvent.click(within(noteCard).getAllByRole('button', { name: '记录审批（不执行）' })[0]);
    await waitFor(() => expect(within(noteCard).getAllByRole('status').length).toBeGreaterThanOrEqual(2));

    expect(request.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(true);
    expect(request.mock.calls.some(([url]) => /\/api\/(journal|promote|capture\/text|tasks)/.test(String(url)))).toBe(false);
    expect(request.mock.calls.filter(([url, init]) => url === '/api/notes' && init?.method === 'POST')).toHaveLength(1);

    cleanup();
    render(<UnifiedInboxPage locale="zh-CN" onReview={vi.fn()} showSyntheticCaptureDemo />);
    const restoredTitle = await screen.findByText('新建合成会议');
    const restoredCard = restoredTitle.closest('article') as HTMLElement;
    expect((await within(restoredCard).findAllByText(/决定已记录到 Core/)).length).toBeGreaterThan(0);
    expect(within(restoredCard).getByText('已拒绝；原始内容保留。')).toBeTruthy();
  });

  it('uses only known demo vocabulary, surfaces unknown hashtags separately, and never emits status as a tag', () => {
    const result = suggestInboxClassification('项目：SecondBrain\n状态：待整理\n这是 #CRM #roadmap #待整理。');
    expect(result.type).toBe('笔记');
    expect(result.tags).toEqual(['CRM']);
    expect(result.unknownTagCandidates).toEqual(['roadmap']);
    expect(result.tags).not.toContain('待整理');
    expect(result.projectAssociation).toBe('SecondBrain');
    const corrected = suggestInboxClassification('项目：SecondBrain\n状态：待整理\n这是 #CRM #SecondBrain #roadmap。', '', ['SecondBrain'], '头脑风暴');
    expect(corrected.type).toBe('头脑风暴');
    expect(corrected.tags).toEqual(['CRM']);
    expect(corrected.unknownTagCandidates).toEqual(['roadmap']);
  });

  it('requires a separate exact target preview and explicit confirmation after recording approval', async () => {
    const request = vi.mocked(fetch);
    render(<UnifiedInboxPage locale="zh-CN" onReview={vi.fn()} showSyntheticCaptureDemo={false} />);
    const card = (await screen.findByRole('heading', { name: 'Sprint meeting.md' })).closest('article') as HTMLElement;
    fireEvent.click(within(card).getByRole('button', { name: '生成确定性 Mock 建议' }));
    const approve = await within(card).findAllByRole('button', { name: '记录审批（不执行）' });
    fireEvent.click(approve[0]);
    expect(await within(card).findByText(/审批记录本身不会执行/)).toBeTruthy();
    expect(request.mock.calls.some(([url]) => String(url).endsWith('/execute'))).toBe(false);
    fireEvent.click(within(card).getByRole('button', { name: '准备目标预览' }));
    const target = await within(card).findByLabelText('目标正文（将按此内容写入）') as HTMLTextAreaElement;
    expect(target.value).toBe('合成来源正文');
    expect(within(card).getByRole('button', { name: '确认并执行' })).toBeTruthy();
    expect(request.mock.calls.some(([url]) => String(url).endsWith('/execute'))).toBe(false);
    fireEvent.click(within(card).getByRole('button', { name: '确认并执行' }));
    expect(await within(card).findByText(/已执行 · journal:2026-10-18/)).toBeTruthy();
    expect(request.mock.calls.filter(([url]) => String(url).endsWith('/execute'))).toHaveLength(1);
    expect(request.mock.calls.some(([url]) => String(url).includes('/promote/'))).toBe(false);
  });

  it('embedded Notes section skips real Capture fetch but allows a synthetic Capture example in the same view', async () => {
    const request = vi.mocked(fetch);
    render(<UnifiedInboxPage locale="zh-CN" onReview={vi.fn()} showSyntheticCaptureDemo={false} notesOnly />);
    expect(await screen.findByRole('heading', { name: '笔记草稿' })).toBeTruthy();
    expect(request.mock.calls.some(([url]) => String(url).startsWith('/api/inbox'))).toBe(false);
    cleanup();
    request.mockClear();
    render(<UnifiedInboxPage locale="zh-CN" onReview={vi.fn()} showSyntheticCaptureDemo notesOnly />);
    fireEvent.click(await screen.findByRole('button', { name: '添加合成 Capture 示例' }));
    expect(await screen.findByRole('heading', { name: '合成会议输入.md' })).toBeTruthy();
    expect(request.mock.calls.some(([url]) => String(url).startsWith('/api/inbox'))).toBe(false);
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
    expect(await screen.findByText(/notes.write denied/)).toBeTruthy();
    expect(request.mock.calls.some(([url]) => /\/api\/(journal|promote|capture\/text|tasks)/.test(String(url)))).toBe(false);
  });

  it('restores the Core value and reports an unsaved edit after an asynchronous save failure', async () => {
    const request = vi.mocked(fetch);
    const original = request.getMockImplementation()!;
    request.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).startsWith('/api/inbox/proposals/proposal-journal') && init?.method === 'PUT') return ok({ detail: 'synthetic failure' }, 500);
      return original(input, init);
    });
    render(<UnifiedInboxPage locale="zh-CN" onReview={vi.fn()} showSyntheticCaptureDemo={false} />);
    const card = (await screen.findByRole('heading', { name: 'Sprint meeting.md' })).closest('article') as HTMLElement;
    fireEvent.click(within(card).getByRole('button', { name: '生成确定性 Mock 建议' }));
    const textarea = (await within(card).findAllByLabelText('可编辑建议'))[0] as HTMLTextAreaElement;
    const persistedValue = textarea.value;
    fireEvent.change(textarea, { target: { value: '未保存的本地修改' } });
    fireEvent.click(within(card).getAllByRole('button', { name: '保存建议' })[0]);
    expect(await within(card).findByText('修改未保存（HTTP 500）。')).toBeTruthy();
    expect(textarea.value).toBe(persistedValue);
  });

  it('marks an edit conflict and disables approval until the source is reviewed again', async () => {
    const request = vi.mocked(fetch);
    const original = request.getMockImplementation()!;
    request.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).startsWith('/api/inbox/proposals/proposal-type') && init?.method === 'PUT') return ok({ detail: 'synthetic conflict' }, 412);
      return original(input, init);
    });
    render(<UnifiedInboxPage locale="zh-CN" onReview={vi.fn()} showSyntheticCaptureDemo={false} />);
    const card = (await screen.findByRole('heading', { name: 'Sprint meeting.md' })).closest('article') as HTMLElement;
    fireEvent.click(within(card).getByRole('button', { name: '生成确定性 Mock 建议' }));
    const type = await within(card).findByLabelText('建议类型（Core 集中词库）') as HTMLSelectElement;
    fireEvent.change(type, { target: { value: '头脑风暴' } });
    expect(await within(card).findByText(/发生冲突：来源或建议已变化/)).toBeTruthy();
    expect(type.disabled).toBe(true);
    expect(within(card).getByText('来源已变化；请重新生成并复核。')).toBeTruthy();
    fireEvent.click(within(card).getByRole('button', { name: '重新加载建议' }));
    await waitFor(() => expect(type.disabled).toBe(false));
    expect(within(card).queryByText('来源已变化；请重新生成并复核。')).toBeNull();
  });
});
