import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ChatPage } from './App';
import { journalInboxAttemptKey } from './chat-inbox';
import { isExplicitJournalIntent } from './journal-intent';

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const response = (status: number, body: unknown) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
});
const sessions = [{ session_id: 'session-a', title: 'Synthetic A' }, { session_id: 'session-b', title: 'Synthetic B' }];
const recordedAt = '2026-10-20T10:00:00.000Z';

function inboxAccepted(requestBody: Record<string, unknown>, overrides: Record<string, unknown> = {}) {
  return {
    inbox_id: 'a'.repeat(32), status: 'processing', captured_at: recordedAt,
    occurred_at: requestBody.occurred_at, source: { channel: 'web', event_id: requestBody.source_event_id },
    intent: 'journal_intent', replayed: false,
    consent_evidence: { kind: 'authenticated_app_explicit_action', subject: 'synthetic-owner', recorded_at: recordedAt },
    ...overrides,
  };
}

function inboxStatus(requestBody: Record<string, unknown>, overrides: Record<string, unknown> = {}) {
  return {
    inbox_id: 'a'.repeat(32), status: 'processing', captured_at: recordedAt,
    occurred_at: requestBody.occurred_at, source: { channel: 'web', event_id: requestBody.source_event_id },
    intent: 'journal_intent',
    consent_evidence: { kind: 'authenticated_app_explicit_action', subject: 'synthetic-owner', recorded_at: recordedAt },
    source_ref: { capture_id: 'a'.repeat(32), review_path: null, review_sha256: null },
    ...overrides,
  };
}

function setupFetch(handler: (url: string, init?: RequestInit) => Promise<Response>) {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    if (url === '/api/chat/sessions?limit=50&offset=0') return response(200, { sessions });
    if (url.endsWith('/messages')) return response(200, { messages: [] });
    if (url.endsWith('/activities')) return response(200, { activities: [] });
    return handler(url, init);
  });
  vi.stubGlobal('fetch', fetchMock);
  return { calls, fetchMock };
}

async function openChat() {
  render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
  return await screen.findByPlaceholderText('发送消息给 Hermes…') as HTMLTextAreaElement;
}

function submit(buttonLabel = '发送') {
  fireEvent.click(screen.getByRole('button', { name: buttonLabel }));
}

describe('D086 explicit Journal intent to Inbox', () => {
  it.each(['记一下：原文', '记下来 原文', '写日记：原文', '记录一下，原文', '保存这段话：原文', '写到日记里：原文', '请帮我记一下：原文', '麻烦帮我记录到日记里，原文'])
  ('recognizes frozen explicit Journal phrase %s', (text) => {
    expect(isExplicitJournalIntent(text)).toBe(true);
  });

  it('does not classify ordinary text that merely mentions a Journal phrase later', () => {
    expect(isExplicitJournalIntent('我想记一下这个问题')).toBe(false);
  });

  it('posts the exact original text with the frozen journal_intent schema, then verifies the inbox_id by GET', async () => {
    window.localStorage.setItem('secondbrain.chat.session', 'session-a');
    const generatedId = vi.fn(() => 'web-event-unique-001');
    vi.stubGlobal('crypto', { randomUUID: generatedId });
    const { calls } = setupFetch(async (url, init) => {
      if (url === '/api/inbox/entries' && init?.method === 'POST') {
        return response(202, inboxAccepted(JSON.parse(String(init.body)) as Record<string, unknown>));
      }
      if (url === `/api/inbox/entries/${'a'.repeat(32)}`) {
        const post = calls.find((call) => call.url === '/api/inbox/entries' && call.init?.method === 'POST');
        return response(200, inboxStatus(JSON.parse(String(post?.init?.body)) as Record<string, unknown>));
      }
      return response(404, { detail: 'not found' });
    });
    const input = await openChat();
    const original = '  记一下：保持用户原始空格与原话  ';
    fireEvent.change(input, { target: { value: original } });
    submit();

    const link = await screen.findByRole('link', { name: '打开 Inbox 条目' });
    expect(link.getAttribute('href')).toBe(`/inbox#capture-${'a'.repeat(32)}`);
    expect((input as HTMLTextAreaElement).value).toBe('');
    expect(screen.getByText(/尚未创建 Journal 日记/)).toBeTruthy();
    const post = calls.find((call) => call.url === '/api/inbox/entries' && call.init?.method === 'POST');
    const body = JSON.parse(String(post?.init?.body));
    expect(body).toEqual({ original_text: original, source_channel: 'web', source_event_id: 'web-event-unique-001',
      occurred_at: expect.any(String), intent: 'journal_intent' });
    expect(new Headers(post?.init?.headers).get('Idempotency-Key')).toBeNull();
    expect(generatedId).toHaveBeenCalledTimes(1);
    expect(calls.some((call) => call.url === '/api/journal/entries')).toBe(false);
    expect(calls.some((call) => call.url === '/api/tasks')).toBe(false);
    expect(calls.some((call) => call.url.includes('/runs'))).toBe(false);
    expect(calls.some((call) => call.url === `/api/inbox/entries/${'a'.repeat(32)}`)).toBe(true);
  });

  it('ordinary chat does not enter Inbox and keeps the Hermes Run route', async () => {
    window.localStorage.setItem('secondbrain.chat.session', 'session-a');
    const { calls } = setupFetch(async (url) => {
      if (url === '/api/chat/sessions/session-a/runs') return response(200, { run_id: 'synthetic-run' });
      if (url === '/api/chat/runs/synthetic-run/events') return response(503, { detail: 'synthetic offline' });
      return response(404, {});
    });
    const input = await openChat();
    fireEvent.change(input, { target: { value: '普通聊天，不自动收录' } });
    submit();
    await waitFor(() => expect(calls.some((call) => call.url === '/api/chat/sessions/session-a/runs')).toBe(true));
    expect(calls.some((call) => call.url === '/api/inbox/entries')).toBe(false);
    expect(calls.some((call) => call.url === '/api/journal/entries')).toBe(false);
  });

  it('a lost POST response retries the exact serialized body, event ID, and time', async () => {
    window.localStorage.setItem('secondbrain.chat.session', 'session-a');
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'retry-event-001') });
    const bodies: string[] = [];
    let posts = 0;
    const { calls } = setupFetch(async (url, init) => {
      if (url === '/api/inbox/entries' && init?.method === 'POST') {
        posts += 1; bodies.push(String(init.body));
        if (posts === 1) throw new TypeError('synthetic network result unknown');
        return response(202, inboxAccepted(JSON.parse(String(init.body)) as Record<string, unknown>, { replayed: true }));
      }
      if (url === `/api/inbox/entries/${'a'.repeat(32)}`) return response(200, inboxStatus(JSON.parse(bodies.at(-1)!) as Record<string, unknown>));
      return response(404, {});
    });
    const input = await openChat();
    const original = '写日记：network result unknown';
    fireEvent.change(input, { target: { value: original } });
    submit();
    expect((await screen.findByRole('alert')).textContent).toContain('结果未知');
    expect(input.value).toBe(original);
    const saved = JSON.parse(sessionStorage.getItem(journalInboxAttemptKey('session-a'))!);
    const firstBody = bodies[0];
    expect(saved.bodyJson).toBe(firstBody);
    expect(saved.body.source_event_id).toBe('retry-event-001');
    expect(saved.body.original_text).toBe(original);
    submit('使用同一请求重试');
    await screen.findByRole('link', { name: '打开 Inbox 条目' });
    expect(posts).toBe(2);
    expect(bodies[1]).toBe(firstBody);
    expect(calls.some((call) => call.url === '/api/journal/entries')).toBe(false);
  });

  it('restores an unknown attempt after page reload and retries the byte-identical body', async () => {
    window.localStorage.setItem('secondbrain.chat.session', 'session-a');
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'refresh-event-001') });
    const firstBodies: string[] = [];
    setupFetch(async (url, init) => {
      if (url === '/api/inbox/entries' && init?.method === 'POST') {
        firstBodies.push(String(init.body));
        throw new TypeError('synthetic response lost');
      }
      return response(404, {});
    });
    const firstPage = render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    const original = '写到日记里：刷新后继续原请求';
    const input = await screen.findByPlaceholderText('发送消息给 Hermes…') as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: original } });
    submit();
    await screen.findByRole('button', { name: '使用同一请求重试' });
    firstPage.unmount();

    const retryBodies: string[] = [];
    setupFetch(async (url, init) => {
      if (url === '/api/inbox/entries' && init?.method === 'POST') {
        const bodyJson = String(init.body); retryBodies.push(bodyJson);
        const body = JSON.parse(bodyJson) as Record<string, unknown>;
        return response(202, inboxAccepted(body, { inbox_id: 'c'.repeat(32), replayed: true }));
      }
      if (url === `/api/inbox/entries/${'c'.repeat(32)}`) {
        const body = JSON.parse(retryBodies.at(-1)!) as Record<string, unknown>;
        return response(200, inboxStatus(body, { inbox_id: 'c'.repeat(32), source_ref: { capture_id: 'c'.repeat(32) } }));
      }
      return response(404, {});
    });
    const restoredInput = await openChat();
    expect((restoredInput as HTMLTextAreaElement).value).toBe(original);
    fireEvent.click(await screen.findByRole('button', { name: '使用同一请求重试' }));
    await screen.findByRole('link', { name: '打开 Inbox 条目' });
    expect(retryBodies).toHaveLength(1);
    expect(retryBodies[0]).toBe(firstBodies[0]);
    expect(JSON.parse(retryBodies[0]).source_event_id).toBe('refresh-event-001');
  });

  it('does not POST until exact request storage succeeds', async () => {
    window.localStorage.setItem('secondbrain.chat.session', 'session-a');
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'storage-retry-event') });
    const posted: string[] = [];
    setupFetch(async (url, init) => {
      if (url === '/api/inbox/entries' && init?.method === 'POST') {
        posted.push(String(init.body));
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        return response(202, inboxAccepted(body));
      }
      if (url.startsWith('/api/inbox/entries/')) return response(200, inboxStatus(JSON.parse(posted.at(-1)!) as Record<string, unknown>));
      return response(404, {});
    });
    const originalSetItem = Storage.prototype.setItem;
    const storageFailure = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (this: Storage, key: string, value: string) {
      if (key === journalInboxAttemptKey('session-a')) throw new DOMException('synthetic storage full', 'QuotaExceededError');
      return originalSetItem.call(this, key, value);
    });
    const input = await openChat();
    fireEvent.change(input, { target: { value: '记一下：先持久化再发送' } });
    submit();
    expect((await screen.findByRole('alert')).textContent).toContain('没有发送任何写入');
    expect(posted).toHaveLength(0);
    storageFailure.mockRestore();
    await waitFor(() => expect(screen.getByRole('button', { name: '使用同一请求重试' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '使用同一请求重试' }));
    await screen.findByRole('link', { name: '打开 Inbox 条目' });
    expect(posted).toHaveLength(1);
    expect(JSON.parse(posted[0]).source_event_id).toBe('storage-retry-event');
  });

  it.each([401, 403, 409, 422, 503])('retains the exact request and shows sanitized HTTP %s feedback', async (status) => {
    window.localStorage.setItem('secondbrain.chat.session', 'session-a');
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => `failure-event-${status}`) });
    const { calls } = setupFetch(async (url, init) => url === '/api/inbox/entries' && init?.method === 'POST'
      ? response(status, { detail: 'SYNTHETIC_PRIVATE_ERROR_MUST_NOT_RENDER' }) : response(404, {}));
    const input = await openChat();
    const original = '记一下：失败时原文不清除';
    fireEvent.change(input, { target: { value: original } });
    submit();
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toBeTruthy();
    expect(alert.textContent).not.toContain('SYNTHETIC_PRIVATE_ERROR_MUST_NOT_RENDER');
    expect(input.value).toBe(original);
    expect(sessionStorage.getItem(journalInboxAttemptKey('session-a'))).toContain(`failure-event-${status}`);
    expect(calls.filter((call) => call.url === '/api/journal/entries')).toHaveLength(0);
  });

  it('rapid repeat clicks send one POST and each confirmed new send receives a distinct source event ID', async () => {
    window.localStorage.setItem('secondbrain.chat.session', 'session-a');
    const ids = ['distinct-event-a', 'distinct-event-b'];
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => ids.shift() ?? 'unexpected-event') });
    const posted: Record<string, unknown>[] = [];
    const { calls } = setupFetch(async (url, init) => {
      if (url === '/api/inbox/entries' && init?.method === 'POST') {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>; posted.push(body);
        return response(202, inboxAccepted(body));
      }
      if (url.startsWith('/api/inbox/entries/')) return response(200, inboxStatus(posted.at(-1)!));
      return response(404, {});
    });
    const input = await openChat();
    fireEvent.change(input, { target: { value: '记一下：第一次' } });
    submit();
    fireEvent.submit(input.closest('form')!);
    await screen.findByRole('link', { name: '打开 Inbox 条目' });
    expect(calls.filter((call) => call.url === '/api/inbox/entries' && call.init?.method === 'POST')).toHaveLength(1);
    await waitFor(() => expect(screen.getByRole('button', { name: '发送' })).toBeTruthy());
    fireEvent.change(input, { target: { value: '保存这段话：第二次独立收录' } });
    submit();
    await waitFor(() => expect(posted).toHaveLength(2));
    expect(posted.map((body) => body.source_event_id)).toEqual(['distinct-event-a', 'distinct-event-b']);
    expect(posted[0].source_event_id).not.toBe(posted[1].source_event_id);
    expect(calls.filter((call) => call.url === '/api/inbox/entries' && call.init?.method === 'POST')).toHaveLength(2);
  });

  it('keeps a late accepted result scoped to its source session', async () => {
    window.localStorage.setItem('secondbrain.chat.session', 'session-a');
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'session-a-event') });
    let releaseFirst!: (result: Response) => void;
    const firstPost = new Promise<Response>((resolve) => { releaseFirst = resolve; });
    let postedBody: Record<string, unknown> | null = null;
    const { calls } = setupFetch(async (url, init) => {
      if (url === '/api/inbox/entries' && init?.method === 'POST') {
        postedBody = JSON.parse(String(init.body)) as Record<string, unknown>;
        return firstPost;
      }
      if (url === `/api/inbox/entries/${'a'.repeat(32)}` && postedBody) {
        return response(200, inboxStatus(postedBody));
      }
      return response(404, {});
    });
    const input = await openChat();
    fireEvent.change(input, { target: { value: '记一下：A 会话待确认' } });
    submit();
    await waitFor(() => expect(postedBody?.source_event_id).toBe('session-a-event'));
    fireEvent.click(screen.getByRole('button', { name: /^Synthetic B/ }));
    await waitFor(() => expect(window.localStorage.getItem('secondbrain.chat.session')).toBe('session-b'));
    expect(screen.queryByRole('region', { name: '日记意图 Inbox 回执' })).toBeNull();
    await act(async () => {
      releaseFirst(response(202, inboxAccepted(postedBody!, { inbox_id: 'a'.repeat(32) })));
    });
    expect(screen.queryByRole('region', { name: '日记意图 Inbox 回执' })).toBeNull();
    expect(calls.some((call) => call.url === '/api/inbox/entries')).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: /^Synthetic A/ }));
    expect(await screen.findByRole('link', { name: '打开 Inbox 条目' })).toBeTruthy();
    expect(calls.some((call) => call.url === '/api/journal/entries')).toBe(false);
  });

  it('restores an unknown request only in its own session and reuses it after switching back', async () => {
    window.localStorage.setItem('secondbrain.chat.session', 'session-a');
    const generated = vi.fn().mockReturnValueOnce('session-a-event').mockReturnValueOnce('session-b-event');
    vi.stubGlobal('crypto', { randomUUID: generated });
    const bodies = new Map<string, string[]>();
    const { calls } = setupFetch(async (url, init) => {
      if (url === '/api/inbox/entries' && init?.method === 'POST') {
        const bodyJson = String(init.body);
        const body = JSON.parse(bodyJson) as Record<string, unknown>;
        const key = String(body.source_event_id);
        const attempts = bodies.get(key) ?? [];
        attempts.push(bodyJson); bodies.set(key, attempts);
        if (key === 'session-a-event' && attempts.length === 1) return response(503, { detail: 'synthetic unknown' });
        const inboxId = key === 'session-a-event' ? 'a'.repeat(32) : 'b'.repeat(32);
        return response(202, inboxAccepted(body, { inbox_id: inboxId, replayed: attempts.length > 1 }));
      }
      if (url.startsWith('/api/inbox/entries/')) {
        const inboxId = url.split('/').at(-1)!;
        const key = inboxId === 'a'.repeat(32) ? 'session-a-event' : 'session-b-event';
        const body = JSON.parse(bodies.get(key)?.at(-1) ?? '{}') as Record<string, unknown>;
        return response(200, inboxStatus(body, { inbox_id: inboxId, source_ref: { capture_id: inboxId } }));
      }
      return response(404, {});
    });
    const input = await openChat();
    fireEvent.change(input, { target: { value: '记一下：A 会话待确认' } });
    submit();
    expect((await screen.findByRole('alert')).textContent).toContain('结果未知');
    const firstA = bodies.get('session-a-event')?.[0];
    expect(firstA).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /^Synthetic B/ }));
    await waitFor(() => expect(window.localStorage.getItem('secondbrain.chat.session')).toBe('session-b'));
    expect(screen.queryByRole('region', { name: '日记意图重试状态' })).toBeNull();
    const inputB = await screen.findByPlaceholderText('发送消息给 Hermes…') as HTMLTextAreaElement;
    fireEvent.change(inputB, { target: { value: '记一下：B 会话内容' } });
    submit();
    await screen.findByRole('link', { name: '打开 Inbox 条目' });
    expect(bodies.has('session-b-event')).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: /^Synthetic A/ }));
    const retryButton = await screen.findByRole('button', { name: '使用同一请求重试' });
    expect((screen.getByPlaceholderText('发送消息给 Hermes…') as HTMLTextAreaElement).value).toBe('记一下：A 会话待确认');
    fireEvent.click(retryButton);
    await waitFor(() => expect(bodies.get('session-a-event')).toHaveLength(2));
    expect(bodies.get('session-a-event')![0]).toBe(bodies.get('session-a-event')![1]);
    expect(JSON.parse(bodies.get('session-a-event')![0]).occurred_at).toBeTruthy();
    expect(JSON.parse(bodies.get('session-a-event')![0]).source_event_id).not.toBe(JSON.parse(bodies.get('session-b-event')![0]).source_event_id);
    expect(calls.some((call) => call.url === '/api/journal/entries')).toBe(false);
  });

  it('does not trust a malformed 202 or expose its source link', async () => {
    window.localStorage.setItem('secondbrain.chat.session', 'session-a');
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'mismatched-event') });
    setupFetch(async (url, init) => {
      if (url === '/api/inbox/entries' && init?.method === 'POST') {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        return response(202, inboxAccepted(body, { source: { channel: 'web', event_id: 'different-event' } }));
      }
      return response(404, {});
    });
    const input = await openChat();
    const original = '记一下：回执要精确匹配';
    fireEvent.change(input, { target: { value: original } });
    submit();
    expect((await screen.findByRole('alert')).textContent).toContain('无法核验');
    expect(input.value).toBe(original);
    expect(screen.queryByRole('link', { name: '打开 Inbox 条目' })).toBeNull();
    expect(sessionStorage.getItem(journalInboxAttemptKey('session-a'))).toContain('mismatched-event');
  });

  it('does not reuse an unresolved event ID for edited content', async () => {
    window.localStorage.setItem('secondbrain.chat.session', 'session-a');
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'unresolved-event') });
    const posted: string[] = [];
    setupFetch(async (url, init) => {
      if (url === '/api/inbox/entries' && init?.method === 'POST') {
        posted.push(String(init.body));
        return response(503, { detail: 'synthetic unavailable' });
      }
      return response(404, {});
    });
    const input = await openChat();
    fireEvent.change(input, { target: { value: '记一下：原始请求' } });
    submit();
    await screen.findByRole('button', { name: '使用同一请求重试' });
    await waitFor(() => expect((screen.getByRole('button', { name: '发送' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.change(input, { target: { value: '记一下：编辑后的不同内容' } });
    submit();
    expect((await screen.findByRole('alert')).textContent).toContain('没有发送新请求');
    expect(posted).toHaveLength(1);
    expect(JSON.parse(posted[0]).original_text).toBe('记一下：原始请求');
    expect(JSON.parse(sessionStorage.getItem(journalInboxAttemptKey('session-a'))!).body.source_event_id).toBe('unresolved-event');
  });
});
