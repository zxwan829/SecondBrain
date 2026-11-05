import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { App, ChatPage, InboxPage, ReviewPage, scrollReviewItemIntoView, sortByCapturedAt } from './App';
import { UnifiedCaptureComposer } from './UnifiedCaptureComposer';

afterEach(() => { cleanup(); window.history.replaceState({}, '', '/'); vi.unstubAllGlobals(); vi.useRealTimers(); });

const callbacks = () => ({ onComplete: vi.fn(), onGoInbox: vi.fn() });
const TestCaptureComposer = ({ locale, onGoInbox = () => undefined }: { locale: 'zh-CN' | 'en'; onGoInbox?: () => void }) => <UnifiedCaptureComposer locale={locale} onComplete={() => undefined} onGoInbox={onGoInbox} />;
const ok = (body: unknown, contentType = 'application/json') => ({
  ok: true, status: 200, headers: { get: () => contentType },
  json: async () => body, text: async () => typeof body === 'string' ? body : JSON.stringify(body),
});
const sse = (events: Record<string, unknown>[]) => new Response(new ReadableStream<Uint8Array>({
  start(controller) {
    const encoder = new TextEncoder();
    for (const event of events) controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
    controller.close();
  },
}), { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
const proposalId = 'b'.repeat(32);
const inboxId = 'c'.repeat(32);
const proposalVersion = 4;
const sourceVersion = 'sha256:synthetic-source-version';
const suggestion = (overrides: Record<string, unknown> = {}) => ({ event: 'capture.suggestion', approved_proposal_id: proposalId,
  approved_proposal_version: proposalVersion, source_event_id: 'synthetic:event-9', occurred_at: '2026-10-20T01:02:03Z',
  original_text: 'A synthetic insight to capture.', ...overrides });
const approvalBody = (overrides: Record<string, unknown> = {}) => ({ proposal: {
  proposal_id: proposalId, status: 'approved_recorded', version: proposalVersion, kind: 'journal',
  source_version: sourceVersion, vocabulary_version: 12, suggestion: {
    original: { value: 'A synthetic insight to capture.', reason: 'Synthetic Core approval rationale.' },
    current: { value: 'A synthetic insight to capture.' },
  },
  ...overrides,
} });
const inboxBody = (overrides: Record<string, unknown> = {}) => ({ inbox_id: inboxId, status: 'processing',
  captured_at: '2026-10-20T01:03:00Z', occurred_at: '2026-10-20T01:02:03Z', source: { channel: 'web', event_id: 'synthetic:event-9' },
  intent: 'approved_suggestion', replayed: false,
  consent_evidence: { kind: 'authenticated_app_approved_proposal', subject: 'synthetic-owner', recorded_at: '2026-10-20T01:03:00Z',
    proposal_id: proposalId, proposal_version: proposalVersion, source_version: sourceVersion },
  approved_proposal: { proposal_id: proposalId, version: proposalVersion, kind: 'journal', source_version: sourceVersion },
  source_ref: { capture_id: inboxId, review_path: null, review_sha256: null }, ...overrides });
const chatSessions = [{ session_id: 'synthetic-chat-session', title: 'Synthetic' }];
const historyPayload = { sessions: chatSessions };

describe('D075.1 capture interactions', () => {
  it('requires an explicit Core approval check, posts the exact 202 contract, and confirms the single Inbox entry by GET', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    const event = suggestion();
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input); calls.push({ url, init });
      if (url === '/api/chat/sessions?limit=50&offset=0') return ok(historyPayload);
      if (url === '/api/chat/sessions') return ok({ session_id: 'synthetic-chat-session' });
      if (url.endsWith('/runs')) return ok({ run_id: 'synthetic-run' });
      if (url.endsWith('/events')) return sse([event, { event: 'run.completed', output: 'Done.' }]);
      if (url.endsWith('/messages')) return ok({ messages: [] });
      if (url.endsWith('/activities')) return ok({ activities: [] });
      if (url === `/api/inbox/proposals/${proposalId}/history`) return ok(approvalBody());
      if (url === '/api/inbox/entries') return new Response(JSON.stringify(inboxBody()), { status: 202, headers: { 'Content-Type': 'application/json' } });
      if (url === `/api/inbox/entries/${inboxId}`) return ok(inboxBody());
      return ok({});
    }));
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    const input = await screen.findByPlaceholderText('发送消息给 Hermes…');
    fireEvent.change(input, { target: { value: '普通聊天，不自动收录' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    const card = await screen.findByRole('region', { name: 'Hermes 收录建议' });
    expect(within(card).getByText(event.original_text)).toBeTruthy();
    expect(calls.some((call) => call.url === '/api/inbox/entries')).toBe(false);
    fireEvent.click(within(card).getByRole('button', { name: '核验当前 Core 批准' }));
    await within(card).findByText(/已核验 Core 批准/);
    expect(calls.some((call) => call.url === `/api/inbox/proposals/${proposalId}/history`)).toBe(true);
    const confirmation = within(card).getByLabelText('输入“确认收录”以继续');
    fireEvent.change(confirmation, { target: { value: '确认' } });
    expect(within(card).getByRole('button', { name: '确认并提交给 Core' }).hasAttribute('disabled')).toBe(true);
    fireEvent.change(confirmation, { target: { value: '确认收录' } });
    fireEvent.click(within(card).getByRole('button', { name: '确认并提交给 Core' }));
    expect(await within(card).findByRole('link', { name: '打开 Inbox 来源' })).toBeTruthy();
    expect(within(card).getByRole('link', { name: '打开 Inbox 来源' }).getAttribute('href')).toBe(`/inbox#capture-${inboxId}`);
    expect(within(card).getByRole('status').textContent).toContain('processing');
    const post = calls.find((call) => call.url === '/api/inbox/entries');
    expect(JSON.parse(String(post?.init?.body))).toEqual({
      original_text: event.original_text, source_channel: 'web', source_event_id: event.source_event_id,
      occurred_at: event.occurred_at, intent: 'approved_suggestion', approved_proposal_id: proposalId,
      approved_proposal_version: proposalVersion,
    });
    expect(new Headers(post?.init?.headers).get('Idempotency-Key')).toBeNull();
    expect(calls.some((call) => call.url === `/api/inbox/entries/${inboxId}`)).toBe(true);
    expect(sessionStorage.getItem(`secondbrain.chat.captureReceipt:synthetic-chat-session`)).not.toContain(event.original_text);
  });

  it('keeps a valid 202 receipt unverified and hides its source link when the exact GET mismatches', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    const calls: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input); calls.push(url);
      if (url === '/api/chat/sessions?limit=50&offset=0') return ok(historyPayload);
      if (url.endsWith('/messages')) return ok({ messages: [] });
      if (url.endsWith('/activities')) return ok({ activities: [] });
      if (url.endsWith('/runs')) return ok({ run_id: 'synthetic-run' });
      if (url.endsWith('/events')) return sse([suggestion(), { event: 'run.completed', output: 'Done.' }]);
      if (url === `/api/inbox/proposals/${proposalId}/history`) return ok(approvalBody());
      if (url === '/api/inbox/entries') return new Response(JSON.stringify(inboxBody()), { status: 202, headers: { 'Content-Type': 'application/json' } });
      if (url === `/api/inbox/entries/${inboxId}`) return ok(inboxBody({ source_ref: { capture_id: 'd'.repeat(32), review_path: null, review_sha256: null } }));
      return ok({});
    }));
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    fireEvent.change(await screen.findByPlaceholderText('发送消息给 Hermes…'), { target: { value: 'synthetic only' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    const card = await screen.findByRole('region', { name: 'Hermes 收录建议' });
    fireEvent.click(within(card).getByRole('button', { name: '核验当前 Core 批准' }));
    await within(card).findByText(/已核验 Core 批准/);
    fireEvent.change(within(card).getByLabelText('输入“确认收录”以继续'), { target: { value: '确认收录' } });
    fireEvent.click(within(card).getByRole('button', { name: '确认并提交给 Core' }));

    expect((await within(card).findByRole('alert')).textContent).toMatch(/状态尚未核验/);
    expect(within(card).queryByRole('link', { name: '打开 Inbox 来源' })).toBeNull();
    expect(within(card).queryByLabelText('输入“确认收录”以继续')).toBeNull();
    expect(within(card).getByRole('button', { name: '刷新 Core 状态' })).toBeTruthy();
    expect(calls.filter((url) => url === '/api/inbox/entries')).toHaveLength(1);
    expect(sessionStorage.getItem('secondbrain.chat.captureReceipt:synthetic-chat-session')).toContain(inboxId);
  });

  it('restores an opaque session receipt without a trusted link while exact GET is pending or fails', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    window.localStorage.setItem('secondbrain.chat.session', 'synthetic-chat-session');
    const receipt = { sessionId: 'synthetic-chat-session', inboxId, sourceEventId: 'synthetic:event-9', proposalId,
      proposalVersion, sourceVersion, kind: 'journal' };
    const storageKey = 'secondbrain.chat.captureReceipt:synthetic-chat-session';
    window.sessionStorage.setItem(storageKey, JSON.stringify(receipt));
    let rejectGet!: (response: Response) => void;
    const exactGet = new Promise<Response>((resolve) => { rejectGet = resolve; });
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/chat/sessions?limit=50&offset=0') return Promise.resolve(ok(historyPayload));
      if (url.endsWith('/messages')) return Promise.resolve(ok({ messages: [] }));
      if (url.endsWith('/activities')) return Promise.resolve(ok({ activities: [] }));
      if (url === `/api/inbox/entries/${inboxId}`) return exactGet;
      return Promise.resolve(ok({}));
    }));
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    expect(await screen.findByRole('region', { name: 'Inbox 收录状态' })).toBeTruthy();
    expect((await screen.findByRole('alert')).textContent).toContain('正在向 Core 核验已保存回执');
    expect(screen.queryByRole('link', { name: '打开 Inbox 来源' })).toBeNull();
    expect(sessionStorage.getItem(storageKey)).toBe(JSON.stringify(receipt));

    await act(async () => { rejectGet(new Response(JSON.stringify({ detail: 'synthetic unavailable' }), { status: 503 })); });
    expect((await screen.findByRole('alert')).textContent).toMatch(/状态尚未核验/);
    expect(screen.queryByRole('link', { name: '打开 Inbox 来源' })).toBeNull();
    expect(sessionStorage.getItem(storageKey)).toBe(JSON.stringify(receipt));
  });

  it('fails closed when SSE has only the untrusted legacy proposal_id', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    const event = suggestion({ approved_proposal_id: undefined, approved_proposal_version: undefined, proposal_id: proposalId });
    const calls: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      calls.push(url);
      if (url === '/api/chat/sessions?limit=50&offset=0') return ok(historyPayload);
      if (url === '/api/chat/sessions') return ok({ session_id: 'synthetic-chat-session' });
      if (url.endsWith('/runs')) return ok({ run_id: 'synthetic-run' });
      if (url.endsWith('/events')) return sse([event, { event: 'run.completed', output: 'Done.' }]);
      if (url.endsWith('/messages')) return ok({ messages: [] });
      if (url.endsWith('/activities')) return ok({ activities: [] });
      return ok({});
    }));
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    fireEvent.change(await screen.findByPlaceholderText('发送消息给 Hermes…'), { target: { value: 'ordinary chat' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    const card = await screen.findByRole('region', { name: 'Hermes 收录建议' });
    expect(within(card).getByText(/缺少 Core 已批准 Proposal ID/)).toBeTruthy();
    expect(within(card).queryByLabelText('输入“确认收录”以继续')).toBeNull();
    expect(within(card).queryByRole('button', { name: '核验当前 Core 批准' })).toBeNull();
    expect(calls.some((url) => url === '/api/inbox/entries' || url.includes('/api/inbox/proposals/'))).toBe(false);
    expect(within(card).queryByRole('link', { name: '打开 Inbox 来源' })).toBeNull();
  });

  it.each([
    ['unapproved status', { status: 'suggested' }],
    ['stale version', { version: proposalVersion + 1 }],
    ['changed source text', { suggestion: { original: { value: 'Changed source text.', reason: 'Synthetic rationale.' }, current: { value: 'Changed source text.' } } }],
    ['source text differs by whitespace', { suggestion: { original: { value: 'A synthetic insight to capture. ', reason: 'Synthetic rationale.' }, current: { value: 'A synthetic insight to capture.' } } }],
    ['legacy text shape', { suggestion: { original: 'A synthetic insight to capture.', current: { value: 'A synthetic insight to capture.' } } }],
    ['missing original value', { suggestion: { original: { reason: 'Synthetic rationale.' }, current: { value: 'A synthetic insight to capture.' } } }],
    ['non-text original value', { suggestion: { original: { value: 42, reason: 'Synthetic rationale.' }, current: { value: 'A synthetic insight to capture.' } } }],
    ['extra original field', { suggestion: { original: { value: 'A synthetic insight to capture.', reason: 'Synthetic rationale.', extra: 'rejected' }, current: { value: 'A synthetic insight to capture.' } } }],
  ])('does not allow a Core approval with %s to reach POST', async (_label, invalidApproval) => {
    window.localStorage.clear(); window.sessionStorage.clear();
    const calls: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      calls.push(url);
      if (url === '/api/chat/sessions?limit=50&offset=0') return ok(historyPayload);
      if (url === '/api/chat/sessions') return ok({ session_id: 'synthetic-chat-session' });
      if (url.endsWith('/runs')) return ok({ run_id: 'synthetic-run' });
      if (url.endsWith('/events')) return sse([suggestion(), { event: 'run.completed', output: 'Done.' }]);
      if (url.endsWith('/messages')) return ok({ messages: [] });
      if (url.endsWith('/activities')) return ok({ activities: [] });
      if (url === `/api/inbox/proposals/${proposalId}/history`) return ok(approvalBody(invalidApproval));
      return ok({});
    }));
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    fireEvent.change(await screen.findByPlaceholderText('发送消息给 Hermes…'), { target: { value: 'ordinary text' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    const card = await screen.findByRole('region', { name: 'Hermes 收录建议' });
    fireEvent.click(within(card).getByRole('button', { name: '核验当前 Core 批准' }));
    expect(await within(card).findByRole('alert')).toBeTruthy();
    expect(calls.some((url) => url === '/api/inbox/entries')).toBe(false);
    expect(within(card).queryByLabelText('输入“确认收录”以继续')).toBeNull();
  });

  it.each([200, 201, 202])('rejects malformed HTTP %i response without an exact Core receipt', async (status) => {
    window.localStorage.clear(); window.sessionStorage.clear();
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/chat/sessions?limit=50&offset=0') return ok(historyPayload);
      if (url === '/api/chat/sessions') return ok({ session_id: 'synthetic-chat-session' });
      if (url.endsWith('/runs')) return ok({ run_id: 'synthetic-run' });
      if (url.endsWith('/events')) return sse([suggestion(), { event: 'run.completed', output: 'Done.' }]);
      if (url.endsWith('/messages')) return ok({ messages: [] });
      if (url.endsWith('/activities')) return ok({ activities: [] });
      if (url === `/api/inbox/proposals/${proposalId}/history`) return ok(approvalBody());
      if (url === '/api/inbox/entries') return new Response(JSON.stringify({ inbox_id: 'not-an-id', status: 'processing' }), { status });
      return ok({});
    }));
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    fireEvent.change(await screen.findByPlaceholderText('发送消息给 Hermes…'), { target: { value: 'ordinary text' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    const card = await screen.findByRole('region', { name: 'Hermes 收录建议' });
    fireEvent.click(within(card).getByRole('button', { name: '核验当前 Core 批准' }));
    await within(card).findByText(/已核验 Core 批准/);
    fireEvent.change(within(card).getByLabelText('输入“确认收录”以继续'), { target: { value: '确认收录' } });
    fireEvent.click(within(card).getByRole('button', { name: '确认并提交给 Core' }));
    expect(await within(card).findByRole('alert')).toBeTruthy();
    expect(within(card).queryByRole('link', { name: '打开 Inbox 来源' })).toBeNull();
  });

  it.each([401, 403, 409, 503])('keeps capture unconfirmed when Core POST returns HTTP %i', async (status) => {
    window.localStorage.clear(); window.sessionStorage.clear();
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/chat/sessions?limit=50&offset=0') return ok(historyPayload);
      if (url === '/api/chat/sessions') return ok({ session_id: 'synthetic-chat-session' });
      if (url.endsWith('/runs')) return ok({ run_id: 'synthetic-run' });
      if (url.endsWith('/events')) return sse([suggestion(), { event: 'run.completed', output: 'Done.' }]);
      if (url.endsWith('/messages')) return ok({ messages: [] });
      if (url.endsWith('/activities')) return ok({ activities: [] });
      if (url === `/api/inbox/proposals/${proposalId}/history`) return ok(approvalBody());
      if (url === '/api/inbox/entries') return new Response(JSON.stringify({ detail: 'synthetic_failure' }), { status });
      return ok({});
    }));
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    fireEvent.change(await screen.findByPlaceholderText('发送消息给 Hermes…'), { target: { value: 'ordinary text' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    const card = await screen.findByRole('region', { name: 'Hermes 收录建议' });
    fireEvent.click(within(card).getByRole('button', { name: '核验当前 Core 批准' }));
    await within(card).findByText(/已核验 Core 批准/);
    fireEvent.change(within(card).getByLabelText('输入“确认收录”以继续'), { target: { value: '确认收录' } });
    fireEvent.click(within(card).getByRole('button', { name: '确认并提交给 Core' }));
    expect(await within(card).findByRole('alert')).toBeTruthy();
    expect(within(card).queryByRole('link', { name: '打开 Inbox 来源' })).toBeNull();
    expect(sessionStorage.getItem('secondbrain.chat.captureReceipt:synthetic-chat-session')).toBeNull();
  });

  it('retries an uncertain POST with the same event identity and restores only the session-bound receipt', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    let postAttempts = 0;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input); calls.push({ url, init });
      if (url === '/api/chat/sessions?limit=50&offset=0') return ok({ sessions: [
        { session_id: 'synthetic-session-a', title: 'Synthetic A' }, { session_id: 'synthetic-session-b', title: 'Synthetic B' },
      ] });
      if (url.endsWith('/messages')) return ok({ messages: [] });
      if (url.endsWith('/activities')) return ok({ activities: [] });
      if (url.endsWith('/runs')) return ok({ run_id: 'synthetic-run' });
      if (url.endsWith('/events')) return sse([suggestion(), { event: 'run.completed', output: 'Done.' }]);
      if (url === `/api/inbox/proposals/${proposalId}/history`) return ok(approvalBody());
      if (url === '/api/inbox/entries') {
        postAttempts += 1;
        if (postAttempts === 1) throw new TypeError('synthetic connection lost after request');
        return new Response(JSON.stringify(inboxBody({ replayed: true })), { status: 202, headers: { 'Content-Type': 'application/json' } });
      }
      if (url === `/api/inbox/entries/${inboxId}`) return ok(inboxBody());
      return ok({});
    }));
    window.localStorage.setItem('secondbrain.chat.session', 'synthetic-session-a');
    const mounted = render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    const input = await screen.findByPlaceholderText('发送消息给 Hermes…');
    fireEvent.change(input, { target: { value: 'ordinary text' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    const card = await screen.findByRole('region', { name: 'Hermes 收录建议' });
    fireEvent.click(within(card).getByRole('button', { name: '核验当前 Core 批准' }));
    await within(card).findByText(/已核验 Core 批准/);
    const confirmation = within(card).getByLabelText('输入“确认收录”以继续');
    fireEvent.change(confirmation, { target: { value: '确认收录' } });
    fireEvent.click(within(card).getByRole('button', { name: '确认并提交给 Core' }));
    expect(await within(card).findByRole('alert')).toBeTruthy();
    fireEvent.click(within(card).getByRole('button', { name: '确认并提交给 Core' }));
    expect(await within(card).findByRole('link', { name: '打开 Inbox 来源' })).toBeTruthy();
    const posts = calls.filter((call) => call.url === '/api/inbox/entries');
    expect(posts).toHaveLength(2);
    expect(JSON.parse(String(posts[0].init?.body))).toEqual(JSON.parse(String(posts[1].init?.body)));
    expect(JSON.parse(String(posts[1].init?.body)).source_event_id).toBe('synthetic:event-9');
    mounted.unmount();
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    await waitFor(() => expect(calls.filter((call) => call.url === `/api/inbox/entries/${inboxId}`)).toHaveLength(2));
    expect(await screen.findByRole('link', { name: '打开 Inbox 来源' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Synthetic B/ }));
    await waitFor(() => expect(calls.some((call) => call.url.endsWith('/synthetic-session-b/messages'))).toBe(true));
    expect(calls.filter((call) => call.url === `/api/inbox/entries/${inboxId}`)).toHaveLength(2);
  });

  it('ignores a capture suggestion delivered by an old Run after switching sessions', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    const proposal = { event: 'capture.suggestion', proposal_id: 'synthetic-late-proposal', source_event_id: 'synthetic-late-event', occurred_at: '2026-10-20T01:02:03Z', original_text: 'Late old-session suggestion.' };
    let streamController!: ReadableStreamDefaultController<Uint8Array>;
    const delayedStream = new Response(new ReadableStream<Uint8Array>({ start(controller) { streamController = controller; } }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
    const calls: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input); calls.push(url);
      if (url === '/api/chat/sessions?limit=50&offset=0') return ok({ sessions: [
        { session_id: 'synthetic-session-a', title: 'Synthetic A' }, { session_id: 'synthetic-session-b', title: 'Synthetic B' },
      ] });
      if (url.endsWith('/runs') && url.includes('synthetic-session-a')) return ok({ run_id: 'synthetic-run-a' });
      if (url.endsWith('/events')) return delayedStream;
      if (url === '/api/chat/runs/synthetic-run-a') return ok({ status: 'completed' });
      if (url.endsWith('/messages')) return ok({ messages: [] });
      if (url.endsWith('/activities')) return ok({ activities: [] });
      return ok({});
    }));
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    fireEvent.change(await screen.findByPlaceholderText('发送消息给 Hermes…'), { target: { value: 'ordinary text' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    await waitFor(() => expect(calls).toContain('/api/chat/sessions/synthetic-session-a/runs'));
    fireEvent.click(screen.getByRole('button', { name: /Synthetic B/ }));
    await waitFor(() => expect(calls).toContain('/api/chat/sessions/synthetic-session-b/messages'));
    const encoder = new TextEncoder();
    await act(async () => {
      streamController.enqueue(encoder.encode(`data: ${JSON.stringify(proposal)}\n\n`));
      streamController.enqueue(encoder.encode(`data: ${JSON.stringify({ event: 'run.completed' })}\n\n`));
      streamController.close();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(screen.queryByRole('region', { name: 'Hermes 收录建议' })).toBeNull();
    expect(screen.queryByText(proposal.original_text)).toBeNull();
    expect(calls.some((url) => url === '/api/inbox/entries')).toBe(false);
  });

  it('sorts capture timestamps newest first, keeps ties deterministic, and places unknown dates last', () => {
    const items = [
      { capture_id: 'z', captured_at: '2026-10-14T00:00:00Z' },
      { capture_id: 'unknown', captured_at: 'not-a-date' },
      { capture_id: 'b', captured_at: '2026-10-15T00:00:00Z' },
      { capture_id: 'a', captured_at: '2026-10-15T00:00:00Z' },
    ];
    expect(sortByCapturedAt(items, (item) => item.capture_id).map((item) => item.capture_id))
      .toEqual(['a', 'b', 'z', 'unknown']);
  });

  it('accepts one dropped file and allows removing it', async () => {
    render(<TestCaptureComposer locale="zh-CN" />);
    const file = new File(['hello'], 'notes.txt', { type: 'text/plain' });
    fireEvent.drop(screen.getByRole('region', { name: '快速收录' }), { dataTransfer: { files: [file], types: ['Files'] } });
    expect(await screen.findByText('notes.txt')).toBeTruthy();
    expect(screen.getByText(/KiB/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '移除附件' }));
    expect(screen.queryByText('notes.txt')).toBeNull();
  });

  it('uses the file chooser and rejects unsupported or oversized files', async () => {
    render(<TestCaptureComposer locale="zh-CN" />);
    const input = screen.getByLabelText('选择附件') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['x'], 'bad.exe')] } });
    expect((await screen.findByRole('alert')).textContent).toContain('此文件类型不受支持');
    const tooLarge = new File([new Uint8Array(20 * 1024 * 1024 + 1)], 'large.pdf', { type: 'application/pdf' });
    fireEvent.change(input, { target: { files: [tooLarge] } });
    expect((await screen.findByRole('alert')).textContent).toContain('不能超过 20 MiB');
    const selected = new File(['sample'], 'notes.md', { type: 'text/markdown' });
    fireEvent.change(input, { target: { files: [selected] } });
    expect(await screen.findByText('notes.md')).toBeTruthy();
    expect(input.value).toBe('');
    fireEvent.click(screen.getByRole('button', { name: '更换' }));
    fireEvent.change(input, { target: { files: [new File(['new'], 'replacement.pdf', { type: 'application/pdf' })] } });
    expect(await screen.findByText('replacement.pdf')).toBeTruthy();
    expect(screen.queryByText('notes.md')).toBeNull();
  });

  it('turns an explicitly pasted clipboard image into an attachment and keeps ordinary text paste', async () => {
    const createObjectURL = vi.fn().mockReturnValue('blob:preview');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL });
    render(<TestCaptureComposer locale="zh-CN" />);
    const input = screen.getByLabelText('收录内容');
    const image = new File(['image-bytes'], 'clipboard.png', { type: 'image/png' });
    const clipboardItem = { type: 'image/png', getAsFile: () => image };
    const pasteEvent = new Event('paste', { bubbles: true, cancelable: true });
    Object.defineProperty(pasteEvent, 'clipboardData', { value: { items: [clipboardItem] } });
    input.dispatchEvent(pasteEvent);
    expect(await screen.findByText('pasted-image.png')).toBeTruthy();
    expect(createObjectURL).toHaveBeenCalledWith(image);
    fireEvent.click(screen.getByRole('button', { name: '移除附件' }));
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:preview'));

    const textPaste = new Event('paste', { bubbles: true, cancelable: true });
    Object.defineProperty(textPaste, 'clipboardData', { value: { items: [] } });
    input.dispatchEvent(textPaste);
    expect(textPaste.defaultPrevented).toBe(false);
  });

  it('sends a sole valid URL to URL capture and preserves Markdown text through Text Capture', async () => {
    const request = vi.fn()
      .mockResolvedValueOnce(ok({ capture_id: '1'.repeat(32), raw_path: 'url.md', status: 'completed' }))
      .mockResolvedValueOnce(ok({ capture_id: '2'.repeat(32), raw_path: 'markdown.md', status: 'completed' }));
    vi.stubGlobal('fetch', request);
    render(<TestCaptureComposer locale="zh-CN" />);
    const input = screen.getByLabelText('收录内容');
    fireEvent.change(input, { target: { value: '  https://example.com/path  ' } });
    fireEvent.click(screen.getByRole('button', { name: '发送收录' }));
    await screen.findByText('url.md');
    expect(request.mock.calls[0][0]).toBe('/api/capture/url');
    expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({ url: 'https://example.com/path', capture_context: '' });

    fireEvent.click(screen.getByRole('button', { name: '继续收录' }));
    const markdown = '# 标题\n\n- 原样保留 **格式**';
    fireEvent.change(input, { target: { value: markdown } });
    fireEvent.click(screen.getByRole('button', { name: '发送收录' }));
    await screen.findByText('markdown.md');
    expect(request.mock.calls[1][0]).toBe('/api/capture/text');
    expect(JSON.parse(request.mock.calls[1][1].body).text).toBe(markdown);
  });

  it('uses composer text as attachment context and keeps both fields on failure', async () => {
    const request = vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({ detail: 'write failed' }) });
    vi.stubGlobal('fetch', request);
    render(<TestCaptureComposer locale="zh-CN" />);
    const input = screen.getByLabelText('收录内容') as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: '关于这张图的说明' } });
    fireEvent.change(screen.getByLabelText('选择附件'), { target: { files: [new File(['x'], 'note.txt', { type: 'text/plain' })] } });
    fireEvent.click(screen.getByRole('button', { name: '发送收录' }));
    expect((await screen.findByRole('alert')).textContent).toContain('SecondBrain 服务暂时不可用');
    expect(input.value).toBe('关于这张图的说明');
    const form = request.mock.calls[0][1].body as FormData;
    expect(form.get('capture_context')).toBe('关于这张图的说明');
    expect((form.get('file') as File).name).toBe('note.txt');
  });

  it('clears a selected attachment only after the server confirms its Raw path', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ capture_id: '4'.repeat(32), raw_path: 'photo.png', status: 'processing' })));
    render(<TestCaptureComposer locale="zh-CN" />);
    fireEvent.change(screen.getByLabelText('选择附件'), { target: { files: [new File(['image'], 'photo.png', { type: 'image/png' })] } });
    expect(await screen.findByText('photo.png')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '发送收录' }));
    await screen.findByText('photo.png', { selector: '.capture-result span' });
    expect(screen.queryByRole('img', { name: 'photo.png' })).toBeNull();
    expect(screen.getByRole('button', { name: '继续收录' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '前往收件箱' })).toBeTruthy();
  });

  it('localizes the polled image OCR partial result without changing its status or error code', async () => {
    vi.useFakeTimers();
    const processing = { capture_id: '5'.repeat(32), raw_path: 'photo.png', status: 'processing', source_type: 'image' };
    const partial = { ...processing, status: 'partial_success', review_path: 'photo.md', processor: { kind: 'image_ocr' }, error: { code: 'processor_unavailable', message: 'OCR succeeded; AI scene description is not configured.' } };
    const request = vi.fn().mockImplementation(async (input: RequestInfo | URL) => String(input).includes('/api/capture/555') ? ok(partial) : ok(processing));
    vi.stubGlobal('fetch', request);
    render(<TestCaptureComposer locale="zh-CN" />);
    fireEvent.change(screen.getByLabelText('选择附件'), { target: { files: [new File(['image'], 'photo.png', { type: 'image/png' })] } });
    fireEvent.click(screen.getByRole('button', { name: '发送收录' }));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(screen.getByText('处理中')).toBeTruthy();
    await act(async () => { await vi.advanceTimersByTimeAsync(900); });
    expect(screen.getByText('部分完成')).toBeTruthy();
    expect(screen.getByText(/文字识别完成，画面理解暂未接入/)).toBeTruthy();
    expect(screen.queryByText(/AI scene description/)).toBeNull();
    expect(request).toHaveBeenCalledWith('/api/capture/55555555555555555555555555555555', expect.any(Object));
  });

  it('shows a localized real OCR failure instead of the backend English message', async () => {
    const failed = { capture_id: '6'.repeat(32), raw_path: 'broken.png', status: 'partial_success', source_type: 'image', processor: { kind: 'image_ocr' }, error: { code: 'processing_failed', message: 'Image OCR exceeded its time limit' } };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(failed)));
    render(<TestCaptureComposer locale="zh-CN" />);
    fireEvent.change(screen.getByLabelText('选择附件'), { target: { files: [new File(['image'], 'broken.png', { type: 'image/png' })] } });
    fireEvent.click(screen.getByRole('button', { name: '发送收录' }));
    expect(await screen.findByText(/处理超时；原始文件已保留，可以重试。/)).toBeTruthy();
    expect(screen.queryByText(/exceeded its time limit/)).toBeNull();
  });

  it('keeps Inbox as a history manager and exposes an honest unavailable organize action', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ items: [] })));
    render(<InboxPage locale="zh-CN" onReview={vi.fn()} />);
    expect(await screen.findByRole('heading', { name: '收件箱' })).toBeTruthy();
    expect(screen.queryByLabelText('收录内容')).toBeNull();
    expect(screen.getByRole('button', { name: '立即整理' }).hasAttribute('disabled')).toBe(true);
  });

  it('waits for Inbox items to load before focusing and scrolling to an exact capture hash', async () => {
    const captureId = 'e'.repeat(32);
    const item = { capture_id: captureId, source_type: 'text', input_type: 'md', captured_at: '2026-10-20T00:00:00Z', raw_path: 'synthetic.md', status: 'completed', display_filename: 'synthetic.md' };
    let finishInbox!: (response: ReturnType<typeof ok>) => void;
    const pendingInbox = new Promise<ReturnType<typeof ok>>((resolve) => { finishInbox = resolve; });
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => String(input) === '/api/inbox' ? pendingInbox : Promise.resolve(ok({}))));
    window.history.replaceState({}, '', `/inbox#capture-${captureId}`);
    const previous = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollIntoView');
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: scrollIntoView });
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback: FrameRequestCallback) => { callback(0); return 1; });
    try {
      const { container } = render(<InboxPage locale="zh-CN" onReview={vi.fn()} />);
      await screen.findByText('加载中…');
      await act(async () => { finishInbox(ok({ items: [item] })); await pendingInbox; });
      await screen.findByRole('heading', { name: 'synthetic.md' });
      const target = container.querySelector(`#capture-${captureId}`) as HTMLElement;
      await waitFor(() => expect(scrollIntoView).toHaveBeenCalledWith({ block: 'center' }));
      expect(document.activeElement).toBe(target);
    } finally {
      if (previous) Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', previous);
      else delete (HTMLElement.prototype as Partial<HTMLElement>).scrollIntoView;
    }
  });

  it('reports an exact Inbox source hash that is absent after loading', async () => {
    const captureId = 'f'.repeat(32);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ items: [] })));
    window.history.replaceState({}, '', `/inbox#capture-${captureId}`);
    render(<InboxPage locale="zh-CN" onReview={vi.fn()} />);
    expect((await screen.findByRole('status')).textContent).toContain('未在当前收件箱列表中找到指定来源。');
  });

  it('defaults to Hermes chat and explicitly switches unsupported attachments into capture', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ sessions: [] })));
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    const chatInput = await screen.findByPlaceholderText('发送消息给 Hermes…');
    fireEvent.change(chatInput, { target: { value: '这段文字作为附件说明' } });
    const chooser = document.querySelector('.chat-composer input[type="file"]') as HTMLInputElement;
    fireEvent.change(chooser, { target: { files: [new File(['sample'], 'image.png', { type: 'image/png' })] } });
    expect(await screen.findByText(/对话附件解析尚未验证/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '切换到收录' }));
    expect(await screen.findByText('image.png')).toBeTruthy();
    expect((screen.getByLabelText('收录内容') as HTMLTextAreaElement).value).toBe('这段文字作为附件说明');
    expect(screen.getByRole('button', { name: '对话' })).toBeTruthy();
  });

  it('routes explicit Journal intent to Inbox without creating a Journal entry or Hermes run', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    let inboxRequest: Record<string, unknown> | null = null;
    const request = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/chat/sessions?limit=50&offset=0') return ok({ sessions: [] });
      if (url === '/api/chat/sessions') return ok({ session_id: 'session-synthetic' });
      if (url === '/api/inbox/entries' && init?.method === 'POST') {
        inboxRequest = JSON.parse(String(init.body));
        return new Response(JSON.stringify({ inbox_id: 'd'.repeat(32), status: 'processing', captured_at: '2026-10-17T10:00:00Z',
          occurred_at: inboxRequest!.occurred_at, source: { channel: 'web', event_id: inboxRequest!.source_event_id }, intent: 'journal_intent', replayed: false,
          consent_evidence: { kind: 'authenticated_app_explicit_action', subject: 'synthetic-owner', recorded_at: '2026-10-17T10:00:00Z' } }), { status: 202 });
      }
      if (url === `/api/inbox/entries/${'d'.repeat(32)}`) {
        return ok({ inbox_id: 'd'.repeat(32), status: 'processing', captured_at: '2026-10-17T10:00:00Z', occurred_at: inboxRequest?.occurred_at,
          source: { channel: 'web', event_id: inboxRequest?.source_event_id }, intent: 'journal_intent',
          consent_evidence: { kind: 'authenticated_app_explicit_action', subject: 'synthetic-owner', recorded_at: '2026-10-17T10:00:00Z' },
          source_ref: { capture_id: 'd'.repeat(32), review_path: null, review_sha256: null } });
      }
      if (url.endsWith('/messages')) return ok({ messages: [] });
      if (url.endsWith('/activities')) return ok({ activities: [] });
      return ok({ sessions: [] });
    });
    vi.stubGlobal('fetch', request);
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    const input = await screen.findByPlaceholderText('发送消息给 Hermes…');
    const original = '  记一下：测试时完整保留空格  ';
    fireEvent.change(input, { target: { value: original } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    expect(await screen.findByRole('link', { name: '打开 Inbox 条目' })).toBeTruthy();
    expect(inboxRequest).toEqual({ original_text: original, source_channel: 'web', source_event_id: expect.any(String),
      occurred_at: expect.any(String), intent: 'journal_intent' });
    expect(request.mock.calls.filter(([url]) => url === '/api/journal/entries')).toHaveLength(0);
    expect(request.mock.calls.filter(([url]) => url === `/api/inbox/entries/${'d'.repeat(32)}`)).toHaveLength(1);
    expect(request.mock.calls.some(([url]) => String(url).includes('/runs'))).toBe(false);
    expect((input as HTMLTextAreaElement).value).toBe('');
  });

  it('restores persisted activity after reload and filters it when switching sessions', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    window.localStorage.setItem('secondbrain.chat.session', 'session-a');
    const request = vi.fn(async (url: string) => {
      if (url === '/api/chat/sessions?limit=50&offset=0') return ok({ sessions: [
        { session_id: 'session-a', title: 'A' }, { session_id: 'session-b', title: 'B' },
      ] });
      if (url.endsWith('/activities')) return ok({ activities: url.includes('session-a')
        ? [{ event_id: 'journal:a', operation_id: 'op-a', session_id: 'session-a', kind: 'journal', status: 'succeeded', original_text: '记一下：仅属于 A', occurred_at: '2026-10-17T10:00:00Z', journal_date: '2026-10-17' }]
        : [{ event_id: 'task:b', operation_id: 'op-b', session_id: 'session-b', kind: 'task', status: 'succeeded', original_text: '添加待办：仅属于 B', occurred_at: '2026-10-17T10:01:00Z', task_title: 'B 项', task_status: 'open' }] });
      if (url.endsWith('/messages')) return ok({ messages: [] });
      return ok({ sessions: [] });
    });
    vi.stubGlobal('fetch', request);
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    expect(await screen.findByText('记一下：仅属于 A')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /^B/ }));
    expect(await screen.findByText('添加待办：仅属于 B')).toBeTruthy();
    expect(screen.queryByText('记一下：仅属于 A')).toBeNull();
  });

  it('recovers to a listed Hermes session when the persisted selected ID is stale', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    window.localStorage.setItem('secondbrain.chat.session', 'hermes-stale-id');
    const request = vi.fn(async (url: string) => {
      if (url === '/api/chat/sessions?limit=50&offset=0') return ok({ sessions: [
        { session_id: 'hermes-live-B', title: 'A misleading display title' },
      ] });
      if (url.endsWith('/activities')) return ok({ activities: [{
        event_id: 'journal:live-B', operation_id: 'op-live-B', session_id: 'hermes-live-B',
        kind: 'journal', status: 'succeeded', original_text: '记一下：恢复到实际 Hermes ID',
        occurred_at: '2026-10-18T00:00:00Z', journal_date: '2026-10-18',
      }] });
      if (url.endsWith('/messages')) return ok({ messages: [] });
      return ok({ sessions: [] });
    });
    vi.stubGlobal('fetch', request);
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);

    expect(await screen.findByText('记一下：恢复到实际 Hermes ID')).toBeTruthy();
    expect(request).toHaveBeenCalledWith('/api/chat/sessions/hermes-live-B/activities', expect.anything());
    expect(window.localStorage.getItem('secondbrain.chat.session')).toBe('hermes-live-B');
  });

  it.each(['private-valid-id', 'private-expired-id'])('blank acceptance entry ignores stored Session ID %s and active Run state', async (storedSessionId) => {
    window.localStorage.clear(); window.sessionStorage.clear();
    window.localStorage.setItem('secondbrain.chat.session', storedSessionId);
    window.sessionStorage.setItem('secondbrain.chat.activeRun', 'private-run-id');
    window.sessionStorage.setItem('secondbrain.chat.activeSession', storedSessionId);
    const localGet = vi.spyOn(window.localStorage, 'getItem');
    const localSet = vi.spyOn(window.localStorage, 'setItem');
    const request = vi.fn();
    vi.stubGlobal('fetch', request);
    render(<ChatPage locale="zh-CN" blankMode onGoInbox={vi.fn()} />);

    await act(async () => {});
    expect(request).not.toHaveBeenCalled();
    expect(localGet).not.toHaveBeenCalledWith('secondbrain.chat.session');
    expect(localSet.mock.calls.some(([key]) => key === 'secondbrain.chat.session')).toBe(false);
    expect(window.localStorage.getItem('secondbrain.chat.session')).toBe(storedSessionId);
    expect(window.sessionStorage.getItem('secondbrain.chat.activeRun')).toBe('private-run-id');
    expect(screen.getByRole('status').textContent).toContain('不提供已认证后端账户的服务端隔离');
    fireEvent.change(screen.getByPlaceholderText('发送消息给 Hermes…'), { target: { value: 'must wait for explicit create' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    expect((await screen.findByRole('alert')).textContent).toContain('请先明确创建空白合成会话');
    expect(request).not.toHaveBeenCalled();
    localGet.mockRestore(); localSet.mockRestore();
  });

  it('creates only on explicit action and restores only a previously created blank Session', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    window.localStorage.setItem('secondbrain.chat.session', 'private-existing-id');
    window.sessionStorage.setItem('secondbrain.chat.activeRun', 'private-existing-run');
    const request = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/chat/sessions' && init?.method === 'POST') return ok({ session_id: 'synthetic-session-A' });
      if (url.endsWith('/synthetic-session-A/messages')) return ok({ messages: [{ id: 'm1', role: 'assistant', text: 'synthetic-only' }] });
      if (url.endsWith('/synthetic-session-A/activities')) return ok({ activities: [] });
      throw new Error(`Unexpected blank-mode request: ${url}`);
    });
    vi.stubGlobal('fetch', request);
    const first = render(<ChatPage locale="zh-CN" blankMode onGoInbox={vi.fn()} />);
    await act(async () => {});
    expect(request).not.toHaveBeenCalled();
    expect(window.localStorage.getItem('secondbrain.chat.session')).toBe('private-existing-id');

    fireEvent.click(screen.getByRole('button', { name: '创建合成会话' }));
    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request.mock.calls[0]?.[0]).toBe('/api/chat/sessions');
    expect(request.mock.calls[0]?.[1]?.method).toBe('POST');
    expect(request.mock.calls.some(([url]) => String(url).includes('?limit=') || String(url).includes('/messages') || String(url).includes('/activities') || String(url).includes('/runs'))).toBe(false);
    expect(window.localStorage.getItem('secondbrain.chat.session')).toBe('private-existing-id');

    fireEvent.click(await screen.findByRole('button', { name: /合成会话 1/ }));
    expect(await screen.findByText('synthetic-only')).toBeTruthy();
    expect(request.mock.calls.map(([url]) => url)).toEqual([
      '/api/chat/sessions',
      '/api/chat/sessions/synthetic-session-A/messages',
      '/api/chat/sessions/synthetic-session-A/activities',
    ]);
    first.unmount();

    request.mockClear();
    render(<ChatPage locale="zh-CN" blankMode onGoInbox={vi.fn()} />);
    expect(await screen.findByText('synthetic-only')).toBeTruthy();
    expect(request.mock.calls.map(([url]) => url)).toEqual([
      '/api/chat/sessions/synthetic-session-A/messages',
      '/api/chat/sessions/synthetic-session-A/activities',
    ]);
  });

  it('keeps only explicitly created blank IDs during delayed creation and out-of-order session loads', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    let resolveA: ((value: ReturnType<typeof ok>) => void) | undefined;
    const request = vi.fn((url: string, init?: RequestInit) => {
      if (url === '/api/chat/sessions' && init?.method === 'POST') {
        const callIndex = request.mock.calls.filter(([calledUrl, calledInit]) => calledUrl === url && calledInit?.method === 'POST').length;
        if (callIndex === 1) return new Promise<ReturnType<typeof ok>>((resolve) => { resolveA = resolve; });
        return Promise.resolve(ok({ session_id: 'synthetic-session-B' }));
      }
      const id = url.includes('synthetic-session-A') ? 'A' : 'B';
      if (url.endsWith('/messages')) return id === 'A'
        ? new Promise<ReturnType<typeof ok>>((resolve) => { window.setTimeout(() => resolve(ok({ messages: [{ id: 'a', role: 'assistant', text: 'A only' }] })), 20); })
        : Promise.resolve(ok({ messages: [{ id: 'b', role: 'assistant', text: 'B only' }] }));
      if (url.endsWith('/activities')) return Promise.resolve(ok({ activities: [] }));
      return Promise.reject(new Error(`Unexpected blank-mode request: ${url}`));
    });
    vi.stubGlobal('fetch', request);
    render(<ChatPage locale="zh-CN" blankMode onGoInbox={vi.fn()} />);

    const create = screen.getByRole('button', { name: '创建合成会话' });
    fireEvent.click(create);
    fireEvent.click(create);
    await waitFor(() => expect(resolveA).toBeTruthy());
    await act(async () => { resolveA?.(ok({ session_id: 'synthetic-session-A' })); });
    expect(await screen.findByText('合成会话 2')).toBeTruthy();
    expect(screen.getByRole('button', { name: /合成会话 1/ }).className).toContain('is-selected');

    fireEvent.click(screen.getByRole('button', { name: /合成会话 2/ }));
    fireEvent.click(screen.getByRole('button', { name: /合成会话 1/ }));
    expect(await screen.findByText('B only')).toBeTruthy();
    await act(async () => { await new Promise((resolve) => window.setTimeout(resolve, 35)); });
    expect(screen.getByText('B only')).toBeTruthy();
    expect(screen.queryByText('A only')).toBeNull();
    const paths = request.mock.calls.map(([url]) => String(url));
    expect(paths.every((path) => !path.includes('?limit=') && !path.includes('private') && !path.includes('/runs'))).toBe(true);
    expect(paths.filter((path) => path.endsWith('/messages') || path.endsWith('/activities'))
      .every((path) => path.includes('synthetic-session-A') || path.includes('synthetic-session-B'))).toBe(true);
  });

  it('preserves ordinary Chat first-session recovery outside blank mode', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    const request = vi.fn(async (url: string) => {
      if (url === '/api/chat/sessions?limit=50&offset=0') return ok({ sessions: [{ session_id: 'ordinary-first-session', title: 'First' }] });
      if (url.endsWith('/messages')) return ok({ messages: [{ id: 'm1', role: 'assistant', text: 'ordinary restore' }] });
      if (url.endsWith('/activities')) return ok({ activities: [] });
      return ok({});
    });
    vi.stubGlobal('fetch', request);
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    expect(await screen.findByText('ordinary restore')).toBeTruthy();
    expect(request).toHaveBeenCalledWith('/api/chat/sessions?limit=50&offset=0', expect.anything());
    expect(window.localStorage.getItem('secondbrain.chat.session')).toBe('ordinary-first-session');
  });

  it('routes /chat/blank into the no-session-list entry after App authentication', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    window.localStorage.setItem('secondbrain.chat.session', 'private-trap-id');
    window.history.replaceState({}, '', '/chat/blank');
    const request = vi.fn(async (url: string) => {
      if (url === '/api/auth/session') return ok({});
      throw new Error(`Unexpected blank entry request: ${url}`);
    });
    vi.stubGlobal('fetch', request);
    render(<App />);
    expect(await screen.findByRole('heading', { name: '空白验收' })).toBeTruthy();
    expect(request.mock.calls.map(([url]) => url)).toEqual(['/api/auth/session']);
    expect(window.localStorage.getItem('secondbrain.chat.session')).toBe('private-trap-id');
  });

  it('ignores an activity payload whose Hermes ID differs from the requested session', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    window.localStorage.setItem('secondbrain.chat.session', 'hermes-requested-B');
    const request = vi.fn(async (url: string) => {
      if (url === '/api/chat/sessions?limit=50&offset=0') return ok({ sessions: [
        { session_id: 'hermes-requested-B', title: 'Session C' },
      ] });
      if (url.endsWith('/activities')) return ok({ activities: [{
        event_id: 'task:wrong-A', operation_id: 'op-wrong-A', session_id: 'hermes-response-A',
        kind: 'task', status: 'succeeded', original_text: '添加待办：不可串会话',
        occurred_at: '2026-10-18T00:01:00Z', task_title: '不可串会话', task_status: 'open',
      }] });
      if (url.endsWith('/messages')) return ok({ messages: [] });
      return ok({ sessions: [] });
    });
    vi.stubGlobal('fetch', request);
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);

    await waitFor(() => expect(request).toHaveBeenCalledWith('/api/chat/sessions/hermes-requested-B/activities', expect.anything()));
    expect(screen.queryByText('添加待办：不可串会话')).toBeNull();
  });

  it('keeps the latest selected session when an earlier activity response arrives late', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    window.localStorage.setItem('secondbrain.chat.session', 'hermes-fast-A');
    let resolveA!: (response: ReturnType<typeof ok>) => void;
    const delayedA = new Promise<ReturnType<typeof ok>>((resolve) => { resolveA = resolve; });
    const request = vi.fn(async (url: string) => {
      if (url === '/api/chat/sessions?limit=50&offset=0') return ok({ sessions: [
        { session_id: 'hermes-fast-A', title: 'Session A' }, { session_id: 'hermes-fast-B', title: 'Session B' },
      ] });
      if (url === '/api/chat/sessions/hermes-fast-A/activities') return delayedA;
      if (url === '/api/chat/sessions/hermes-fast-B/activities') return ok({ activities: [{
        event_id: 'task:fast-B', operation_id: 'op-fast-B', session_id: 'hermes-fast-B', kind: 'task',
        status: 'succeeded', original_text: '添加待办：快速切换后属于 B', occurred_at: '2026-10-18T00:02:00Z',
        task_title: '快速切换后属于 B', task_status: 'open',
      }] });
      if (url.endsWith('/messages')) return ok({ messages: [] });
      return ok({ sessions: [] });
    });
    vi.stubGlobal('fetch', request);
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    await waitFor(() => expect(request).toHaveBeenCalledWith('/api/chat/sessions/hermes-fast-A/activities', expect.anything()));

    fireEvent.click(screen.getByRole('button', { name: /^Session B/ }));
    expect(await screen.findByText('添加待办：快速切换后属于 B')).toBeTruthy();
    await act(async () => {
      resolveA(ok({ activities: [{
        event_id: 'journal:late-A', operation_id: 'op-late-A', session_id: 'hermes-fast-A', kind: 'journal',
        status: 'succeeded', original_text: '记一下：延迟返回的 A', occurred_at: '2026-10-18T00:01:00Z', journal_date: '2026-10-18',
      }] }));
      await delayedA;
    });
    expect(screen.getByText('添加待办：快速切换后属于 B')).toBeTruthy();
    expect(screen.queryByText('记一下：延迟返回的 A')).toBeNull();
    expect(window.localStorage.getItem('secondbrain.chat.session')).toBe('hermes-fast-B');
  });

  it('does not let a delayed session creation override a later user selection', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    window.localStorage.setItem('secondbrain.chat.session', 'hermes-create-A');
    let resolveCreate!: (response: ReturnType<typeof ok>) => void;
    let listCalls = 0;
    const delayedCreate = new Promise<ReturnType<typeof ok>>((resolve) => { resolveCreate = resolve; });
    const request = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/chat/sessions?limit=50&offset=0') {
        listCalls += 1;
        return ok({ sessions: [
        { session_id: 'hermes-create-A', title: 'Session A' }, { session_id: 'hermes-create-B', title: 'Session B' },
        ...(listCalls > 1 ? [{ session_id: 'hermes-created-C', title: 'Session C' }] : []),
        ] });
      }
      if (url === '/api/chat/sessions' && init?.method === 'POST') return delayedCreate;
      if (url === '/api/chat/sessions/hermes-create-B/activities') return ok({ activities: [{
        event_id: 'task:selected-B', operation_id: 'op-selected-B', session_id: 'hermes-create-B', kind: 'task',
        status: 'succeeded', original_text: '添加待办：用户最后选择 B', occurred_at: '2026-10-18T00:03:00Z',
        task_title: '用户最后选择 B', task_status: 'open',
      }] });
      if (url.endsWith('/activities')) return ok({ activities: [] });
      if (url.endsWith('/messages')) return ok({ messages: [] });
      return ok({ sessions: [] });
    });
    vi.stubGlobal('fetch', request);
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    await waitFor(() => expect(request).toHaveBeenCalledWith('/api/chat/sessions/hermes-create-A/activities', expect.anything()));

    fireEvent.click(screen.getByRole('button', { name: '新对话' }));
    await waitFor(() => expect(request).toHaveBeenCalledWith('/api/chat/sessions', expect.objectContaining({ method: 'POST' })));
    fireEvent.click(screen.getByRole('button', { name: /^Session B/ }));
    expect(await screen.findByText('添加待办：用户最后选择 B')).toBeTruthy();
    await act(async () => {
      resolveCreate(ok({ session_id: 'hermes-created-C' }));
      await delayedCreate;
    });
    await waitFor(() => expect(request).toHaveBeenCalledWith('/api/chat/sessions?limit=50&offset=0', expect.anything()));
    expect(window.localStorage.getItem('secondbrain.chat.session')).toBe('hermes-create-B');
    expect(screen.getByText('添加待办：用户最后选择 B')).toBeTruthy();
  });

  it('keeps ordinary chat input on the Hermes run route', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    const request = vi.fn(async (url: string) => {
      if (url === '/api/chat/sessions?limit=50&offset=0') return ok({ sessions: [] });
      if (url === '/api/chat/sessions') return ok({ session_id: 'session-synthetic' });
      if (url === '/api/chat/sessions/session-synthetic/runs') return ok({ run_id: 'run-synthetic' });
      if (url === '/api/chat/runs/run-synthetic/events') return { ok: false, status: 503, body: null };
      return ok({ messages: [], sessions: [] });
    });
    vi.stubGlobal('fetch', request);
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    fireEvent.change(await screen.findByPlaceholderText('发送消息给 Hermes…'), { target: { value: '今天天气不错' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    await waitFor(() => expect(request).toHaveBeenCalledWith('/api/chat/sessions/session-synthetic/runs', expect.objectContaining({ method: 'POST' })));
    expect(request).not.toHaveBeenCalledWith('/api/journal/entries', expect.anything());
    expect(request.mock.calls.some(([url]) => url === '/api/inbox/entries')).toBe(false);
  });

  it('keeps explicit Journal text in Inbox after a temporary failure and retries the exact request', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    let posts = 0;
    const requestBodies: string[] = [];
    const request = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/chat/sessions?limit=50&offset=0') return ok({ sessions: [] });
      if (url === '/api/chat/sessions') return ok({ session_id: 'session-synthetic' });
      if (url === '/api/inbox/entries' && init?.method === 'POST') {
        posts += 1;
        requestBodies.push(String(init.body));
        if (posts === 1) return new Response(JSON.stringify({ detail: 'synthetic temporary error' }), { status: 503 });
        const body = JSON.parse(String(init.body));
        return new Response(JSON.stringify({ inbox_id: 'c'.repeat(32), status: 'processing', captured_at: '2026-10-17T10:00:00Z',
          occurred_at: body.occurred_at, source: { channel: 'web', event_id: body.source_event_id }, intent: 'journal_intent', replayed: true,
          consent_evidence: { kind: 'authenticated_app_explicit_action', subject: 'synthetic-owner', recorded_at: '2026-10-17T10:00:00Z' } }), { status: 202 });
      }
      if (url === `/api/inbox/entries/${'c'.repeat(32)}`) {
        const body = JSON.parse(requestBodies.at(-1)!);
        return ok({ inbox_id: 'c'.repeat(32), status: 'processing', captured_at: '2026-10-17T10:00:00Z', occurred_at: body.occurred_at,
          source: { channel: 'web', event_id: body.source_event_id }, intent: 'journal_intent',
          consent_evidence: { kind: 'authenticated_app_explicit_action', subject: 'synthetic-owner', recorded_at: '2026-10-17T10:00:00Z' },
          source_ref: { capture_id: 'c'.repeat(32), review_path: null, review_sha256: null } });
      }
      if (url.endsWith('/messages')) return ok({ messages: [] });
      if (url.endsWith('/activities')) return ok({ activities: [] });
      return ok({ sessions: [] });
    });
    vi.stubGlobal('fetch', request);
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    const input = await screen.findByPlaceholderText('发送消息给 Hermes…');
    fireEvent.change(input, { target: { value: '记一下：失败后保留' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    expect((await screen.findByRole('alert')).textContent).toMatch(/结果未知/);
    expect(await screen.findByRole('button', { name: '使用同一请求重试' })).toBeTruthy();
    expect((input as HTMLTextAreaElement).value).toBe('记一下：失败后保留');
    const firstBody = requestBodies[0];
    fireEvent.click(screen.getByRole('button', { name: '使用同一请求重试' }));
    await screen.findByRole('link', { name: '打开 Inbox 条目' });
    expect(requestBodies).toHaveLength(2);
    expect(requestBodies[1]).toBe(firstBody);
    expect(JSON.parse(firstBody)).toMatchObject({ original_text: '记一下：失败后保留', source_channel: 'web', intent: 'journal_intent' });
    expect(request.mock.calls.filter(([url]) => url === '/api/journal/entries')).toHaveLength(0);
    expect(request.mock.calls.some(([url]) => String(url).includes('/runs'))).toBe(false);
  });

  it('reports unavailable Inbox without clearing the input or pretending Journal was saved', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    const request = vi.fn(async (url: string) => url === '/api/chat/sessions?limit=50&offset=0' ? ok({ sessions: [] })
      : url === '/api/chat/sessions' ? ok({ session_id: 'session-synthetic' })
        : url === '/api/inbox/entries' ? new Response(JSON.stringify({ detail: 'Inbox is not enabled' }), { status: 503 })
          : ok({ activities: [], messages: [] }));
    vi.stubGlobal('fetch', request);
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    const input = await screen.findByPlaceholderText('发送消息给 Hermes…');
    fireEvent.change(input, { target: { value: '请帮我记录到日记里：Journal 未启用' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    expect((await screen.findByRole('alert')).textContent).toMatch(/结果未知/);
    expect((input as HTMLTextAreaElement).value).toBe('请帮我记录到日记里：Journal 未启用');
    expect(request.mock.calls.filter(([url]) => url === '/api/journal/entries')).toHaveLength(0);
    expect(screen.queryByText(/Journal 已创建/)).toBeNull();
  });

  it('creates an explicit Task directly and preserves its command on failure for same-key retry', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    let posts = 0;
    let activity: Record<string, unknown> | null = null;
    const request = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/chat/sessions?limit=50&offset=0') return ok({ sessions: [] });
      if (url === '/api/chat/sessions') return ok({ session_id: 'session-synthetic' });
      if (url === '/api/tasks') {
        posts += 1;
        const body = JSON.parse(String(init?.body));
        activity = { event_id: 'task:one', operation_id: new Headers(init?.headers).get('Idempotency-Key'), session_id: body.session_id, kind: 'task', status: 'succeeded', original_text: body.original_command, occurred_at: '2026-10-17T10:00:00Z', task_id: 'task-1', task_title: '测试任务', task_status: 'open' };
        if (posts === 1) return new Response(JSON.stringify({ detail: 'Task response was lost after commit' }), { status: 500 });
        return ok({ status: 'duplicate', task: { id: 'task-1', title: '测试任务', due_date: body.due_date, status: 'open', created_at: '2026-10-17T10:00:00Z' }, activity });
      }
      if (url.endsWith('/messages')) return ok({ messages: [] });
      if (url.endsWith('/activities')) return ok({ activities: activity ? [activity] : [] });
      return ok({ sessions: [] });
    });
    vi.stubGlobal('fetch', request);
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    const input = await screen.findByPlaceholderText('发送消息给 Hermes…');
    fireEvent.change(input, { target: { value: '请帮我创建一个待办：测试任务 截止：2026-10-20' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    expect((await screen.findByRole('alert')).textContent).toMatch(/服务暂时不可用/);
    expect(await screen.findByText(/结果待确认/)).toBeTruthy();
    expect((input as HTMLTextAreaElement).value).toBe('请帮我创建一个待办：测试任务 截止：2026-10-20');
    const firstTaskCall = request.mock.calls.find(([url]) => url === '/api/tasks');
    const firstKey = new Headers(firstTaskCall?.[1]?.headers).get('Idempotency-Key');
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    await waitFor(() => expect(screen.getByText('成功')).toBeTruthy());
    const taskCalls = request.mock.calls.filter(([url]) => url === '/api/tasks');
    expect(JSON.parse(String(taskCalls[0][1]?.body))).toEqual({ title: '测试任务', due_date: '2026-10-20', original_command: '请帮我创建一个待办：测试任务 截止：2026-10-20', session_id: 'session-synthetic' });
    expect(new Headers(taskCalls[1]?.[1]?.headers).get('Idempotency-Key')).toBe(firstKey);
    expect(request.mock.calls.some(([url]) => String(url).includes('/runs'))).toBe(false);
  });

  it('does not treat an embedded Task phrase as an explicit Chat command', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    const request = vi.fn(async (url: string) => {
      if (url === '/api/chat/sessions?limit=50&offset=0') return ok({ sessions: [] });
      if (url === '/api/chat/sessions') return ok({ session_id: 'session-task-synthetic' });
      if (url === '/api/chat/sessions/session-task-synthetic/runs') return ok({ run_id: 'run-task-synthetic' });
      if (url === '/api/chat/runs/run-task-synthetic/events') return { ok: false, status: 503, body: null };
      return ok({ messages: [], sessions: [] });
    });
    vi.stubGlobal('fetch', request);
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    fireEvent.change(await screen.findByPlaceholderText('发送消息给 Hermes…'), { target: { value: '我们后面可以添加待办：写总结' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    await waitFor(() => expect(request).toHaveBeenCalledWith('/api/chat/sessions/session-task-synthetic/runs', expect.objectContaining({ method: 'POST' })));
    expect(request).not.toHaveBeenCalledWith('/api/tasks', expect.anything());
  });

  it('preserves edited text and a replaced attachment when switching modes repeatedly', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ sessions: [] })));
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    const chatInput = await screen.findByPlaceholderText('发送消息给 Hermes…');
    fireEvent.change(chatInput, { target: { value: '带着附件一起收录' } });
    const chooseInChat = document.querySelector('.chat-composer input[type="file"]') as HTMLInputElement;
    fireEvent.change(chooseInChat, { target: { files: [new File(['old'], 'old.txt', { type: 'text/plain' })] } });
    fireEvent.click(screen.getByRole('button', { name: '切换到收录' }));
    const captureInput = screen.getByLabelText('收录内容') as HTMLTextAreaElement;
    fireEvent.change(captureInput, { target: { value: '编辑后的说明' } });
    fireEvent.change(screen.getByLabelText('选择附件'), { target: { files: [new File(['new'], 'replacement.pdf', { type: 'application/pdf' })] } });
    expect(screen.getByText('replacement.pdf')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '对话' }));
    expect((screen.getByPlaceholderText('发送消息给 Hermes…') as HTMLTextAreaElement).value).toBe('编辑后的说明');
    expect(document.querySelector('.chat-attachment-warning')?.textContent).toContain('replacement.pdf');
    fireEvent.click(screen.getByRole('button', { name: '切换到收录' }));
    expect((screen.getByLabelText('收录内容') as HTMLTextAreaElement).value).toBe('编辑后的说明');
    expect(screen.getByText('replacement.pdf')).toBeTruthy();
  });

  it('accepts Finder drag and drop without sending an unverified file to Hermes', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ sessions: [] })));
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    await screen.findByPlaceholderText('发送消息给 Hermes…');
    const file = new File(['scan'], 'scan.pdf', { type: 'application/pdf' });
    const composer = document.querySelector('.chat-composer')!;
    fireEvent.drop(composer, { dataTransfer: { files: [file], types: ['Files'] } });
    expect(await screen.findByText(/当前 Hermes 对话附件解析能力未验证/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '切换到收录' }));
    expect(await screen.findByText('scan.pdf')).toBeTruthy();
  });

  it('does not submit Enter during IME composition, while Shift+Enter remains a newline', async () => {
    const request = vi.fn().mockResolvedValue(ok({ capture_id: '3'.repeat(32), raw_path: 'ime.md', status: 'completed' }));
    vi.stubGlobal('fetch', request);
    render(<TestCaptureComposer locale="zh-CN" />);
    const input = screen.getByLabelText('收录内容');
    fireEvent.change(input, { target: { value: '中文输入' } });
    fireEvent.compositionStart(input);
    fireEvent.keyDown(input, { key: 'Enter', keyCode: 229, isComposing: true });
    expect(request).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
    expect(request).not.toHaveBeenCalled();
    fireEvent.compositionEnd(input);
    fireEvent.keyDown(input, { key: 'Enter', keyCode: 13, isComposing: false });
    await screen.findByText('ime.md');
    expect(request).toHaveBeenCalledOnce();
  });

  it('clears input only after server confirms Raw and keeps the result actions', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ capture_id: 'a'.repeat(32), raw_path: 'note.md', status: 'processing' })));
    const props = callbacks();
    render(<TestCaptureComposer locale="zh-CN" onGoInbox={props.onGoInbox} />);
    const input = screen.getByLabelText('收录内容') as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: 'keep this capture' } });
    fireEvent.click(screen.getByRole('button', { name: '发送收录' }));
    await screen.findByText('note.md');
    expect(input.value).toBe('');
    expect(screen.getByRole('button', { name: '继续收录' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '前往收件箱' }));
    expect(props.onGoInbox).toHaveBeenCalledOnce();
  });

  it('preserves text when the server rejects capture before Raw is saved', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 400, json: async () => ({ detail: 'invalid input' }) }));
    render(<TestCaptureComposer locale="zh-CN" />);
    const input = screen.getByLabelText('收录内容') as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: 'retry this' } });
    fireEvent.click(screen.getByRole('button', { name: '发送收录' }));
    await screen.findByRole('alert');
    expect(input.value).toBe('retry this');
  });

  it('does not issue duplicate requests while a capture is in flight', async () => {
    let resolveResponse!: (value: unknown) => void;
    const pending = new Promise((resolve) => { resolveResponse = resolve; });
    const request = vi.fn().mockReturnValue(pending);
    vi.stubGlobal('fetch', request);
    render(<TestCaptureComposer locale="zh-CN" />);
    fireEvent.change(screen.getByLabelText('收录内容'), { target: { value: 'single request' } });
    const form = screen.getByLabelText('收录内容').closest('form')!;
    fireEvent.submit(form); fireEvent.submit(form);
    expect(request).toHaveBeenCalledTimes(1);
    resolveResponse(ok({ capture_id: 'e'.repeat(32), raw_path: 'single.md', status: 'completed' }));
    await screen.findByText('single.md');
  });

  it('routes to the exact associated Review and renders that selected detail', async () => {
    const item = { capture_id: 'b'.repeat(32), source_type: 'text', input_type: 'md', captured_at: '2026-10-14T00:00:00Z', original_asset: '/raw/x.md', raw_path: 'x.md', review_path: 'nested/exact.md', status: 'completed', title: 'Inbox source' };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ items: [item] })));
    const onReview = vi.fn();
    render(<InboxPage locale="zh-CN" onReview={onReview} />);
    fireEvent.click(await screen.findByRole('button', { name: '查看 Review' }));
    expect(onReview).toHaveBeenCalledWith('nested/exact.md');

    const review = { review_path: 'nested/exact.md', review_sha256: 'hash', target_filename: 'exact.md', title: 'Exact entry', status: 'pending', content: 'Exact content' };
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/review/items')) return ok({ items: [review, { ...review, review_path: 'other.md', title: 'Other entry' }] });
      if (url.endsWith('/status')) return ok({ promote_enabled: false });
      return ok(review);
    }));
    const { container } = render(<ReviewPage locale="zh-CN" initialReviewPath="nested/exact.md" onBack={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Exact content')).toBeTruthy());
    const selected = container.querySelector('.review-page-item.is-selected');
    expect(selected?.textContent).toContain('Exact entry');
  });

  it('orders Reviews by metadata-only capture time and leaves missing dates unknown without reading Inbox', async () => {
    const review = (review_path: string, captured_at?: string | null) => ({
      review_path, review_sha256: review_path, target_filename: review_path,
      title: review_path, status: 'pending', captured_at, content: `# ${review_path}`,
    });
    const reviews = [review('old.md', '2026-10-10T00:00:00Z'), review('date-only.md', '2026-10-13'), review('legacy.md'), review('unknown.md')];
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/review/items')) return ok({ items: reviews });
      if (url.includes('/api/inbox')) throw new Error('Review list must not load Inbox');
      if (url.endsWith('/status')) return ok({ promote_enabled: false });
      return ok(reviews.find((item) => url.endsWith(item.review_path)));
    }));
    const { container } = render(<ReviewPage locale="zh-CN" onBack={vi.fn()} />);
    await screen.findByText('legacy.md', { selector: '.review-page-item strong' });
    const titles = [...container.querySelectorAll('.review-page-item strong')].map((node) => node.textContent);
    expect(titles).toEqual(['date-only.md', 'old.md', 'legacy.md', 'unknown.md']);
    expect(container.querySelector('.review-page-item:last-child')?.textContent).toContain('时间未知');
  });

  it('resets the independently scrolling Review detail pane to the top when switching rows', async () => {
    const reviews = [
      { review_path: 'a.md', review_sha256: 'a', target_filename: 'a.md', title: 'A', status: 'pending', captured_at: '2026-10-15T00:00:00Z', content: '# A' },
      { review_path: 'b.md', review_sha256: 'b', target_filename: 'b.md', title: 'B', status: 'pending', captured_at: '2026-10-14T00:00:00Z', content: '# B' },
    ];
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/review/items')) return ok({ items: reviews });
      if (url.includes('/api/inbox')) return ok({ items: [] });
      if (url.endsWith('/status')) return ok({ promote_enabled: false });
      return ok(reviews.find((item) => url.endsWith(item.review_path)));
    }));
    const { container } = render(<ReviewPage locale="zh-CN" onBack={vi.fn()} />);
    await screen.findByRole('button', { name: /A/ });
    fireEvent.click(screen.getByRole('button', { name: /A/ }));
    await screen.findByRole('heading', { level: 2, name: 'A' });
    const detail = container.querySelector('.review-page-detail') as HTMLElement;
    detail.scrollTop = 240;
    const secondReview = [...container.querySelectorAll<HTMLButtonElement>('.review-page-item')]
      .find((button) => button.textContent?.includes('b.md'));
    expect(secondReview).toBeTruthy();
    fireEvent.click(secondReview!);
    await screen.findByRole('heading', { level: 2, name: 'B' });
    expect(detail.scrollTop).toBe(0);
    fireEvent.click(screen.getByRole('button', { name: '刷新' }));
    await screen.findByRole('heading', { level: 2, name: 'B' });
    expect(container.querySelector('.review-page-item.is-selected')?.textContent).toContain('Bb.md');
  });

  it('shows one Core status message and hides OCR engine parameters until original text is expanded', async () => {
    const review = {
      review_path: 'ocr.md', review_sha256: 'hash', target_filename: 'ocr.md', title: 'OCR', status: 'pending',
      captured_at: null,
      content: '---\ntype: review\nsource_type: pdf\n---\n# OCR\n\nOCR: tesseract; languages: chi_sim+eng; pages: 1\n\n识别正文',
    };
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/review/items')) return ok({ items: [review] });
      if (url.includes('/api/inbox')) return ok({ items: [] });
      if (url.endsWith('/status')) return ok({ promote_enabled: false });
      return ok(review);
    }));
    const { container } = render(<ReviewPage locale="zh-CN" onBack={vi.fn()} />);
    await screen.findByRole('button', { name: /OCR/ });
    fireEvent.click(screen.getByRole('button', { name: /OCR/ }));
    await waitFor(() => expect(container.querySelector('.review-markdown-raw')?.textContent).toContain('识别正文'));
    expect(container.querySelectorAll('.review-connection-status')).toHaveLength(1);
    expect(container.querySelector('.review-page-toolbar')?.textContent).not.toContain('已连接 Core');
    expect(container.querySelector('.review-markdown-raw')?.textContent).not.toContain('tesseract');
    expect(container.querySelector('.review-source-original')?.textContent).toContain('tesseract');
    expect(container.querySelector('.review-detail-heading')?.textContent).toContain('时间未知');
  });

  it('renders Review body without frontmatter and keeps full metadata collapsible', async () => {
    const review = {
      review_path: 'scan.md', review_sha256: 'hash', target_filename: 'scan.md',
      title: '扫描资料', status: 'pending',
      content: '---\ntype: "review"\nsource_type: "pdf"\ncaptured_at: "2026-10-15T08:00:00Z"\noriginal_asset: "/inbox/scan.pdf"\n---\n# 扫描资料\n\n正文第一行\n正文第二行',
    };
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => String(input).endsWith('/review/items') ? ok({ items: [review] }) : String(input).endsWith('/status') ? ok({ promote_enabled: false }) : ok(review)));
    const { container } = render(<ReviewPage locale="zh-CN" onBack={vi.fn()} />);
    await screen.findByRole('button', { name: /扫描资料/ });
    fireEvent.click(screen.getByRole('button', { name: /扫描资料/ }));
    await waitFor(() => expect(container.querySelector('.review-markdown')?.textContent).toContain('正文第一行'));
    expect(container.querySelector('.review-page-detail')?.textContent).not.toContain('type: "review"');
    expect(screen.getByRole('heading', { level: 2, name: '扫描资料' })).toBeTruthy();
    expect(screen.getByText('完整元数据')).toBeTruthy();
    expect(screen.getByText('2026-10-15T08:00:00Z')).toBeTruthy();
    expect(container.querySelector('.review-detail-heading')?.textContent).toContain('2026/10/15');
    expect(container.querySelector('.review-markdown h1')?.textContent).toBe('扫描资料');
  });

  it('preserves OCR text verbatim and shows a verification note for OCR Reviews', async () => {
    const review = {
      review_path: 'ocr.md', review_sha256: 'hash', target_filename: 'ocr.md',
      title: '扫描识别', status: 'pending',
      content: '---\ntype: "review"\nsource_type: "pdf"\ncaptured_at: "2026-10-15T08:00:00Z"\n---\n# 扫描识别\n\nOCR: tesseract; languages: chi_sim+eng; pages: 1\n\n[Page 1]\n第一行：编号 A-01\n第二行  key: value',
    };
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => String(input).endsWith('/review/items') ? ok({ items: [review] }) : String(input).endsWith('/status') ? ok({ promote_enabled: false }) : ok(review)));
    const { container } = render(<ReviewPage locale="zh-CN" onBack={vi.fn()} />);
    await screen.findByRole('button', { name: /扫描识别/ });
    fireEvent.click(screen.getByRole('button', { name: /扫描识别/ }));
    expect((await screen.findAllByText('第一行：编号 A-01', { exact: false })).length).toBeGreaterThan(0);
    expect(container.querySelector('.review-markdown-raw')?.textContent).toContain('第二行  key: value');
    expect(container.querySelector('.review-markdown-raw')?.textContent).not.toContain('tesseract');
    expect(container.querySelector('.review-source-original')?.textContent).toContain('tesseract');
    expect(screen.getByText('OCR 识别可能存在误差，请对照原件核对。')).toBeTruthy();
  });

  it('shows a safe text preview and download separately', async () => {
    const item = { capture_id: 'd'.repeat(32), source_type: 'markdown', input_type: 'md', captured_at: '2026-10-14T00:00:00Z', original_asset: '/raw/readme.md', raw_path: 'readme.md', status: 'completed', title: 'Read me', content_preview: '# safe' };
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => String(input).endsWith('/preview') ? ok('# Safe text\n<script>text only</script>', 'text/plain') : ok({ items: [item] })));
    render(<InboxPage locale="zh-CN" onReview={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: '预览与详情' }));
    expect(await screen.findByText(/<script>text only<\/script>/)).toBeTruthy();
    expect(screen.getAllByRole('link', { name: '下载原件' })).toHaveLength(2);
  });

  it('does not silently select the first item when the requested Review is missing', async () => {
    const other = { review_path: 'other.md', review_sha256: 'hash', target_filename: 'other.md', title: 'Other entry', status: 'pending', content: 'Other content' };
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => String(input).endsWith('/review/items') ? ok({ items: [other] }) : ok({ promote_enabled: false })));
    const { container } = render(<ReviewPage locale="zh-CN" initialReviewPath="missing.md" onBack={vi.fn()} />);
    expect((await screen.findAllByText('找不到指定的 Review 条目。')).length).toBeGreaterThan(0);
    expect(container.querySelector('.review-page-item.is-selected')).toBeNull();
    expect(screen.queryByText('Other content')).toBeNull();
  });

  it('does not expose an English Core Review error in the Chinese status area', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({ detail: 'Review item not found' }) }));
    render(<ReviewPage locale="zh-CN" onBack={vi.fn()} />);
    expect((await screen.findAllByText('找不到对应的 Review 条目。')).length).toBeGreaterThan(0);
    expect(screen.queryByText('Review item not found')).toBeNull();
  });

  it('scrolls an overflowing mobile Review list itself and centers the selected row', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }));
    const list = document.createElement('div');
    list.style.overflowY = 'auto';
    Object.defineProperties(list, { clientHeight: { value: 200 }, scrollHeight: { value: 800 }, scrollTop: { value: 10, writable: true } });
    list.getBoundingClientRect = vi.fn().mockReturnValue({ top: 20, bottom: 220, left: 0, right: 200, width: 200, height: 200, x: 0, y: 20, toJSON: () => ({}) });
    const scrollTo = vi.fn();
    list.scrollTo = scrollTo;
    const target = document.createElement('button');
    target.getBoundingClientRect = vi.fn().mockReturnValue({ top: 180, bottom: 220, left: 0, right: 100, width: 100, height: 40, x: 0, y: 180, toJSON: () => ({}) });

    scrollReviewItemIntoView(list, target);

    expect(scrollTo).toHaveBeenCalledWith({ top: 90, behavior: 'smooth' });
  });

  it('never falls back to scrolling the full page when the list has no scroll range', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
    const list = document.createElement('div');
    list.style.overflowY = 'visible';
    Object.defineProperties(list, { clientHeight: { value: 500 }, scrollHeight: { value: 500 } });
    const target = document.createElement('button');
    const scrollIntoView = vi.fn();
    target.scrollIntoView = scrollIntoView;

    scrollReviewItemIntoView(list, target);

    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it('shows image OCR partial success neutrally and hides a useless vision retry', async () => {
    const item = { capture_id: 'a'.repeat(32), source_type: 'image', input_type: 'png', captured_at: '2026-10-14T00:00:00Z', original_asset: '/raw/p.png', raw_path: 'p.png', review_path: 'p.md', status: 'partial_success', title: 'p', processor: { kind: 'image_ocr' }, error: { code: 'processor_unavailable', message: 'AI scene description is not configured.' } };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ items: [item] })));
    const { container } = render(<InboxPage locale="zh-CN" onReview={vi.fn()} />);
    await screen.findByRole('heading', { name: 'p.png' });
    expect(screen.getByText('文字识别完成，画面理解暂未接入。')).toBeTruthy();
    expect(container.querySelector('.capture-alert')).toBeNull();
    expect(screen.queryByRole('button', { name: '重试处理' })).toBeNull();
  });

  it('keeps retry and a clear error for actual OCR failures without a Review', async () => {
    const item = { capture_id: 'c'.repeat(32), source_type: 'image', input_type: 'png', captured_at: '2026-10-14T00:00:00Z', original_asset: '/raw/p.png', raw_path: 'p.png', status: 'partial_success', title: 'p', error: { code: 'processing_failed', message: 'Image OCR exceeded its time limit' } };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ items: [item] })));
    render(<InboxPage locale="zh-CN" onReview={vi.fn()} />);
    await screen.findByRole('heading', { name: 'p.png' });
    expect(screen.getByText(/处理超时；原始文件已保留/)).toBeTruthy();
    expect(screen.queryByText(/Image OCR exceeded its time limit/)).toBeNull();
    expect(screen.getByRole('button', { name: '重试处理' })).toBeTruthy();
  });

  it('preserves Capture preview details and retries a synthetic partial-success item', async () => {
    const capture = { capture_id: 'd'.repeat(32), source_type: 'text', input_type: 'md', captured_at: '2026-10-14T00:00:00Z', raw_path: 'raw/retry.md', review_path: null, status: 'partial_success', display_filename: 'retry.md', source_url: 'https://example.test/source', error: { code: 'processing_failed', message: 'Retry the synthetic item.' } };
    let retryCount = 0;
    const request = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/inbox') return ok({ items: [retryCount ? { ...capture, status: 'completed' } : capture] });
      if (url === '/api/automation/organize/status') return ok({ execution_available: false, blocked_reason: 'Synthetic test: disabled' });
      if (url.endsWith('/preview')) return new Response('# Synthetic preview body', { status: 200 });
      if (url.endsWith('/retry') && init?.method === 'POST') { retryCount += 1; return ok({ status: 'accepted' }); }
      return ok({});
    });
    vi.stubGlobal('fetch', request);
    render(<InboxPage locale="zh-CN" onReview={vi.fn()} />);
    expect(await screen.findByRole('heading', { name: 'retry.md' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '预览与详情' }));
    expect(await screen.findByRole('dialog')).toBeTruthy();
    expect(await screen.findByText('# Synthetic preview body')).toBeTruthy();
    expect(screen.getByText('https://example.test/source')).toBeTruthy();
    fireEvent.click(within(screen.getByRole('dialog')).getAllByRole('button', { name: '关闭' })[0]);
    fireEvent.click(screen.getByRole('button', { name: '重试处理' }));
    await waitFor(() => expect(request.mock.calls.some(([url, init]) => String(url).endsWith('/retry') && init?.method === 'POST')).toBe(true));
    expect(await screen.findByText('已完成')).toBeTruthy();
  });

  it('does not let an older Inbox poll overwrite the newer retry result', async () => {
    const capture = { capture_id: '9'.repeat(32), source_type: 'pdf', input_type: 'pdf', captured_at: '2026-10-14T00:00:00Z', raw_path: 'raw/race.pdf', review_path: null, status: 'partial_success', display_filename: 'race.pdf', error: { code: 'processing_failed', message: 'Retry this synthetic PDF.' } };
    let inboxRead = 0;
    let resolveStaleRead!: (response: ReturnType<typeof ok>) => void;
    const request = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/inbox') {
        inboxRead += 1;
        if (inboxRead === 1) return Promise.resolve(ok({ items: [capture] }));
        if (inboxRead === 2) return new Promise<ReturnType<typeof ok>>((resolve) => { resolveStaleRead = resolve; });
        return Promise.resolve(ok({ items: [{ ...capture, status: 'completed', error: null }] }));
      }
      if (url === '/api/automation/organize/status') return Promise.resolve(ok({ execution_available: false, blocked_reason: 'Synthetic test: disabled' }));
      if (url.endsWith('/retry') && init?.method === 'POST') return Promise.resolve(ok({ status: 'accepted' }));
      return Promise.resolve(ok({}));
    });
    vi.stubGlobal('fetch', request);
    render(<InboxPage locale="zh-CN" onReview={vi.fn()} />);
    const heading = await screen.findByRole('heading', { name: 'race.pdf' });
    const item = heading.closest('article')!;

    window.dispatchEvent(new Event('sb-inbox-refresh'));
    await waitFor(() => expect(resolveStaleRead).toBeTypeOf('function'));
    fireEvent.click(within(item).getByRole('button', { name: '重试处理' }));
    await waitFor(() => expect(item.querySelector('.capture-status')?.textContent).toBe('已完成'));

    await act(async () => {
      resolveStaleRead(ok({ items: [capture] }));
    });
    await waitFor(() => expect(item.querySelector('.capture-status')?.textContent).toBe('已完成'));
  });

  it('loads Organizer status and exposes its controlled action only when available', async () => {
    const request = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === '/api/automation/organize/status') return ok({ execution_available: true, blocked_reason: '' });
      if (String(input) === '/api/automation/organize/run' && init?.method === 'POST') return ok({ status: 'no_new_messages' });
      return ok({ items: [] });
    });
    vi.stubGlobal('fetch', request);
    render(<InboxPage locale="zh-CN" onReview={vi.fn()} />);
    const run = await screen.findByRole('button', { name: '立即整理' });
    await waitFor(() => expect((run as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(run);
    expect(await screen.findByText('没有新增对话，无需整理。')).toBeTruthy();
    expect(request.mock.calls.some(([url, init]) => String(url) === '/api/automation/organize/run' && init?.method === 'POST')).toBe(true);
  });

  it('keeps Organizer disabled and reports authorization status when its status API returns 403', async () => {
    const request = vi.fn((input: RequestInfo | URL) => {
      if (String(input) === '/api/automation/organize/status') return Promise.resolve({ ok: false, status: 403, json: async () => ({ detail: 'synthetic private detail' }) });
      return Promise.resolve(ok({ items: [] }));
    });
    vi.stubGlobal('fetch', request);
    render(<InboxPage locale="zh-CN" onReview={vi.fn()} />);
    const run = await screen.findByRole('button', { name: '立即整理' }) as HTMLButtonElement;
    expect(run.disabled).toBe(true);
    expect(await screen.findByText('自动整理状态无法验证（HTTP 403），操作保持禁用。')).toBeTruthy();
    expect(screen.queryByText('synthetic private detail')).toBeNull();
  });

  it('shows the validated upload filename instead of PDF metadata and falls back to the legacy Raw filename', async () => {
    const newer = { capture_id: 'f'.repeat(32), source_type: 'pdf', input_type: 'pdf', captured_at: '2026-10-14T00:00:00Z', original_asset: '/raw/safe.pdf', raw_path: 'safe.pdf', status: 'completed', title: 'safe', display_filename: '会议纪要.pdf', document_title: '(anonymous)' };
    const legacy = { ...newer, capture_id: 'e'.repeat(32), display_filename: undefined, raw_path: '旧版计划.pdf', title: '(anonymous)' };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ items: [newer, legacy] })));
    render(<InboxPage locale="zh-CN" onReview={vi.fn()} />);

    expect(await screen.findByRole('heading', { name: '会议纪要.pdf' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: '旧版计划.pdf' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: '(anonymous)' })).toBeNull();
  });

  it('does not offer a Review action when no Review path exists', async () => {
    const item = { capture_id: 'c'.repeat(32), source_type: 'image', input_type: 'png', captured_at: '2026-10-14T00:00:00Z', original_asset: '/raw/p.png', raw_path: 'p.png', status: 'partial_success', title: 'Image', error: { code: 'processor_unavailable', message: 'No processor' } };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ items: [item] })));
    render(<InboxPage locale="zh-CN" onReview={vi.fn()} />);
    await screen.findByRole('heading', { name: 'p.png' });
    expect(screen.queryByRole('button', { name: '查看 Review' })).toBeNull();
    expect(screen.getByText(/处理功能暂不可用/)).toBeTruthy();
  });
});
