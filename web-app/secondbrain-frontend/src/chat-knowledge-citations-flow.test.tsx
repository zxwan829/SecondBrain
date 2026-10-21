import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ChatPage } from './App';

afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

const citation = { citation_id: 'opaqueCitationId_123456', title: '合成知识条目', sha256: 'a'.repeat(64),
  knowledge_status: 'version_verified', provenance_status: 'verified' };
const history = (sessionId: string, runId: string, status = 'available', citations: unknown[] = [citation]) => ({
  event: 'knowledge.citations', version: 1, session_id: sessionId, run_id: runId, status, citations,
});
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'private, no-store' },
});
const sse = (frames: unknown[]) => new Response(frames.map((frame) => `data: ${JSON.stringify(frame)}\n\n`).join(''), {
  status: 200, headers: { 'Content-Type': 'text/event-stream' },
});
const sessions = { sessions: [
  { session_id: 'session-a', title: 'Synthetic A' },
  { session_id: 'session-b', title: 'Synthetic B' },
] };

function mockChat(historyResponse: (sessionId: string, runId: string) => Response = (sessionId, runId) => json(history(sessionId, runId))) {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input); calls.push({ url, init });
    if (url === '/api/chat/sessions?limit=50&offset=0') return json(sessions);
    if (url.endsWith('/messages')) return json({ messages: [] });
    if (url.endsWith('/activities')) return json({ activities: [] });
    if (url === '/api/chat/sessions/session-a/runs' && init?.method === 'POST') return json({ run_id: 'run-a' });
    if (url === '/api/chat/runs/run-a/events') return sse([
      history('session-a', 'run-a'),
      { event: 'run.completed', run_id: 'run-a', output: 'synthetic answer' },
    ]);
    const match = url.match(/^\/api\/chat\/sessions\/([^/]+)\/runs\/([^/]+)\/knowledge-citations$/);
    if (match) return historyResponse(decodeURIComponent(match[1]), decodeURIComponent(match[2]));
    return json({});
  }));
  return calls;
}

async function openChat() {
  render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
  return await screen.findByPlaceholderText('发送消息给 Hermes…') as HTMLTextAreaElement;
}

describe('Chat Knowledge citation UI and recovery', () => {
  it('renders only the bound live SSE metadata and restores it through the explicit history endpoint', async () => {
    localStorage.setItem('secondbrain.chat.session', 'session-a');
    const calls = mockChat();
    const input = await openChat();
    fireEvent.change(input, { target: { value: '合成问题' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));

    expect(await screen.findByText('合成知识条目')).toBeTruthy();
    expect(screen.getByText(/不证明回答使用了这些参考/)).toBeTruthy();
    expect(screen.getByText('知识文档版本已核验')).toBeTruthy();
    expect(screen.getByText('原始来源记录已核验')).toBeTruthy();
    await waitFor(() => expect(calls.some((call) => call.url.endsWith('/knowledge-citations'))).toBe(true));
    expect(calls.some((call) => call.url.startsWith('/api/knowledge/search'))).toBe(false);
    expect(calls.some((call) => call.url.startsWith('/api/knowledge/items/'))).toBe(false);
    const historyCall = calls.find((call) => call.url.endsWith('/knowledge-citations'));
    expect(historyCall?.init?.cache).toBe('no-store');
    expect(historyCall?.init?.credentials).toBe('same-origin');
  });

  it('restores references after reload and isolates them when switching sessions', async () => {
    localStorage.setItem('secondbrain.chat.session', 'session-a');
    localStorage.setItem('secondbrain.chat.knowledgeCitationRuns', JSON.stringify([
      { session_id: 'session-a', run_id: 'run-a' },
    ]));
    const calls = mockChat((sessionId, runId) => sessionId === 'session-a' && runId === 'run-a'
      ? json(history(sessionId, runId)) : json({ ...history(sessionId, runId), session_id: 'session-a' }));
    await openChat();
    expect(await screen.findByText('合成知识条目')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /Synthetic B/ }));
    await waitFor(() => expect(screen.queryByText('合成知识条目')).toBeNull());
    fireEvent.click(screen.getByRole('button', { name: /Synthetic A/ }));
    expect(await screen.findByText('合成知识条目')).toBeTruthy();
    expect(calls.filter((call) => call.url.endsWith('/knowledge-citations')).every((call) => call.url.includes('/session-a/'))).toBe(true);
  });

  it.each([
    ['401', 401, '请重新登录后核验这些检索参考。'],
    ['403', 403, '当前账户无权重新核验这些检索参考。'],
    ['404', 404, '此运行或其检索参考已不可用。'],
    ['409', 409, '引用绑定发生冲突，已隐藏相关内容。'],
    ['410', 410, '这些检索参考已失效。'],
    ['503', 503, '暂时无法核验检索参考。'],
  ])('shows a fail-closed unavailable state for history HTTP %s', async (_name, status, expected) => {
    localStorage.setItem('secondbrain.chat.session', 'session-a');
    localStorage.setItem('secondbrain.chat.knowledgeCitationRuns', JSON.stringify([
      { session_id: 'session-a', run_id: 'run-a' },
    ]));
    mockChat((sessionId, runId) => json({}, status));
    await openChat();
    expect(await screen.findByText(expected)).toBeTruthy();
    expect(screen.queryByText('合成知识条目')).toBeNull();
  });

  it('labels stale references as invalid and never promotes them to verified', async () => {
    localStorage.setItem('secondbrain.chat.session', 'session-a');
    localStorage.setItem('secondbrain.chat.knowledgeCitationRuns', JSON.stringify([
      { session_id: 'session-a', run_id: 'run-a' },
    ]));
    mockChat((sessionId, runId) => json(history(sessionId, runId, 'partial', [
      { ...citation, knowledge_status: 'stale' },
    ])));
    await openChat();
    expect(await screen.findByText('知识文档版本已变化；此检索参考已失效。')).toBeTruthy();
    expect(screen.queryByText('知识文档版本已核验')).toBeNull();
    expect(screen.queryByText('原始来源记录已核验')).toBeNull();
  });

  it('does not display mismatched run/session payloads or duplicate citation IDs', async () => {
    localStorage.setItem('secondbrain.chat.session', 'session-a');
    localStorage.setItem('secondbrain.chat.knowledgeCitationRuns', JSON.stringify([
      { session_id: 'session-a', run_id: 'run-a' },
    ]));
    mockChat((sessionId, runId) => json({ ...history(sessionId, runId), session_id: 'session-b' }));
    await openChat();
    expect(await screen.findByText('暂时无法核验检索参考。')).toBeTruthy();
    expect(screen.queryByText('合成知识条目')).toBeNull();
  });
});
