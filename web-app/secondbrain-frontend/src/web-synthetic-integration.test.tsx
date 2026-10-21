import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { App } from './App';
import { PromotePreviewPanel } from './PromotePreviewPanel';

const captureId = 'c'.repeat(32);
const reviewPath = '10-Review/synthetic-approved-capture.md';
const reviewSha = 'a'.repeat(64);
const outputSha = 'b'.repeat(64);
const requestId = 'synthetic-request-01';
const reviewMarkdown = '---\nsource_type: text\n---\n# Synthetic approved capture\n\nOnly synthetic integration data.\n';
const preview = {
  preview_id: 'synthetic-preview-01', request_id: requestId, expires_at: '2099-01-01T00:00:00Z',
  source_sha256: reviewSha, target_filename: 'Knowledge/synthetic-approved-capture.md',
  target_precondition: { exists: false }, source_markdown: reviewMarkdown,
  projected_markdown: `${reviewMarkdown}\nApproved synthetic projection.\n`, output_sha256: outputSha,
  change_summary: ['Synthetic exact Review projection; no real file is written.'],
};
const knowledgeResults = [
  { id: 'opaque-verified', title: 'Synthetic promoted entry', snippet: 'Synthetic result', match: 'title', updated: '2026-10-20T00:00:00Z', sha256: outputSha, provenance_status: 'verified' },
  { id: 'opaque-unverified', title: 'Synthetic unverified', snippet: 'Synthetic result', match: 'content', updated: '2026-10-20T00:00:01Z', sha256: 'd'.repeat(64), provenance_status: 'unverified' },
  { id: 'opaque-missing', title: 'Synthetic missing provenance', snippet: 'Synthetic result', match: 'content', updated: '2026-10-20T00:00:02Z', sha256: 'e'.repeat(64), provenance_status: 'missing' },
];

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });

afterEach(() => {
  cleanup(); vi.restoreAllMocks(); vi.unstubAllEnvs();
  localStorage.clear(); sessionStorage.clear();
  history.replaceState({}, '', '/');
});

describe('A Web-only synthetic UI to HTTP integration', () => {
  it('requires explicit Inbox, Review, Promote, search and detail actions and preserves the exact mocked contract', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'false');
    localStorage.clear(); sessionStorage.clear();
    history.replaceState({}, '', '/inbox');
    const calls: Array<{ url: string; method: string; body?: unknown }> = [];
    const homeRequestPaths: string[] = [];
    let operationReads = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method || 'GET';
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ url, method, body });
      if (url === '/api/home') homeRequestPaths.push(location.pathname);
      if (url === '/api/auth/session') return json({ authenticated: true });
      if (url === '/api/inbox/summary?limit=100') return json({ status: 'synthetic', items: [{
        capture_id: captureId, source_type: 'text', input_type: 'text', captured_at: '2026-10-20T00:00:00Z',
        display_filename: 'synthetic-capture.txt', status: 'completed', error_code: null, has_review: true,
      }] });
      if (url === `/api/capture/${captureId}`) return json({
        capture_id: captureId, source_type: 'text', input_type: 'text', captured_at: '2026-10-20T00:00:00Z',
        raw_path: 'synthetic-capture.txt', display_filename: 'synthetic-capture.txt', title: 'Synthetic capture',
        status: 'completed', content_preview: 'synthetic body', review_path: reviewPath,
      });
      if (url === `/api/inbox/${captureId}/preview`) return new Response('Synthetic capture text only.', { status: 200 });
      if (url === '/api/promote/review/items') return json({ items: [{
        review_path: reviewPath, review_sha256: reviewSha, target_filename: preview.target_filename,
        title: 'Synthetic approved capture', status: 'pending', captured_at: '2026-10-20T00:00:00Z',
      }] });
      if (url === `/api/promote/review/items/${reviewPath}`) return json({
        review_path: reviewPath, review_sha256: reviewSha, target_filename: preview.target_filename,
        title: 'Synthetic approved capture', status: 'pending', content: reviewMarkdown,
      });
      if (url === '/api/promote/status') return json({ promote_enabled: true });
      if (url === '/api/promote/review/preview') return json(preview);
      if (url === '/api/promote/auth/unlock') return json({ status: 'unlocked' });
      if (url === '/api/promote/review/confirm') return json({ request_id: requestId, status: 'confirmed' });
      if (url === `/api/promote/operations/${requestId}`) {
        operationReads += 1;
        return json({ request_id: requestId, status: operationReads === 1 ? 'confirmed' : 'promoted', output_sha256: outputSha });
      }
      if (url.startsWith('/api/knowledge/search?')) return json({ items: knowledgeResults, status: 'ok' });
      if (url === '/api/knowledge/items/opaque-verified') return json({
        id: 'opaque-verified', content: '# Synthetic promoted entry\n\nOnly synthetic detail.', sha256: outputSha,
        updated: '2026-10-20T00:00:00Z', provenance_status: 'verified',
      });
      if (url === '/api/knowledge/items/opaque-unverified') return json({
        id: 'opaque-unverified', content: '# Synthetic unverified detail', sha256: 'd'.repeat(64),
        updated: '2026-10-20T00:00:01Z', provenance_status: 'unverified',
      });
      if (url === '/api/knowledge/items/opaque-missing') return json({
        id: 'opaque-missing', content: '# Synthetic missing detail', sha256: 'e'.repeat(64),
        updated: '2026-10-20T00:00:02Z', provenance_status: 'missing',
      });
      return json({ detail: 'unmatched synthetic route' }, 404);
    });

    render(<App />);
    expect(await screen.findByRole('heading', { name: '选择收件箱范围' })).toBeTruthy();
    expect(calls.map((call) => call.url)).toEqual(['/api/auth/session']);
    expect(calls.some((call) => call.url === '/api/home' || call.url.startsWith('/api/promote/') || call.url.startsWith('/api/knowledge/'))).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: /Capture 待处理/ }));
    expect(await screen.findByRole('button', { name: '打开此 Capture' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '打开此 Capture' }));
    expect(await screen.findByRole('button', { name: '查看对应 Review' })).toBeTruthy();
    expect(screen.getByText('Synthetic capture text only.')).toBeTruthy();
    expect(calls.filter((call) => call.url === `/api/capture/${captureId}`)).toHaveLength(1);
    expect(calls.filter((call) => call.url === `/api/inbox/${captureId}/preview`)).toHaveLength(1);
    expect(calls.some((call) => call.url === '/api/automation/organize/status' || call.url === '/api/automation/organize/run')).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: '查看对应 Review' }));
    expect(await screen.findByText('Only synthetic integration data.')).toBeTruthy();
    await waitFor(() => expect(calls.some((call) => call.url === '/api/promote/status')).toBe(true));
    expect(location.pathname).toBe('/review');
    expect(new URLSearchParams(location.search).get('review_path')).toBe(reviewPath);
    expect(screen.getAllByText('Synthetic approved capture').length).toBeGreaterThan(1);
    expect(homeRequestPaths).toEqual([]);

    fireEvent.click(screen.getByRole('button', { name: /Synthetic approved captureKnowledge/ }));
    expect(await screen.findByRole('button', { name: /Prepare exact Promote preview|准备正式入库预览/ })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Prepare exact Promote preview|准备正式入库预览/ }));
    expect(await screen.findByLabelText('拟入库 Markdown 原文')).toBeTruthy();
    expect(screen.getByLabelText('独立正式入库口令')).toBeTruthy();
    expect(screen.getByLabelText('来源 Markdown 原文').textContent).toBe(reviewMarkdown);
    fireEvent.change(screen.getByLabelText('独立正式入库口令'), { target: { value: 'synthetic-only-passphrase' } });
    fireEvent.click(screen.getByRole('button', { name: '独立解锁' }));
    fireEvent.click(await screen.findByRole('button', { name: '确认将此版本写入 Knowledge' }));
    expect(await screen.findByText('已确认；执行结果尚未核验。')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '查询操作状态' }));
    expect(await screen.findByText('已将精确预览版本写入 Knowledge。')).toBeTruthy();
    const promoteCalls = calls.filter((call) => call.url.startsWith('/api/promote/'));
    expect(promoteCalls.map((call) => call.url)).toEqual([
      '/api/promote/review/items', `/api/promote/review/items/${reviewPath}`, '/api/promote/status',
      `/api/promote/review/items/${reviewPath}`, '/api/promote/review/preview', '/api/promote/auth/unlock', '/api/promote/review/confirm',
      `/api/promote/operations/${requestId}`, `/api/promote/operations/${requestId}`,
    ]);
    expect(promoteCalls.find((call) => call.url === '/api/promote/review/preview')?.body).toEqual({
      review_path: reviewPath, review_sha256: reviewSha, target_filename: preview.target_filename,
    });
    expect(promoteCalls.find((call) => call.url === '/api/promote/auth/unlock')?.body).toEqual({ passphrase: 'synthetic-only-passphrase' });
    expect(promoteCalls.find((call) => call.url === '/api/promote/review/confirm')?.body).toEqual({
      preview_id: preview.preview_id, confirm_intent: 'promote_exact_preview',
    });
    expect(promoteCalls.filter((call) => call.url === '/api/promote/review/confirm')).toHaveLength(1);
    expect(promoteCalls.some((call) => call.url === '/api/promote/review/approve')).toBe(false);

    const knowledgeLink = screen.getByRole('link', { name: '打开 Knowledge 搜索' });
    expect(knowledgeLink.getAttribute('href')).toBe('/knowledge');
    knowledgeLink.addEventListener('click', (event) => event.preventDefault());
    fireEvent.click(knowledgeLink);
    history.pushState({}, '', '/knowledge');
    window.dispatchEvent(new PopStateEvent('popstate', { state: {} }));
    expect(await screen.findByRole('heading', { name: '知识库' })).toBeTruthy();
    expect(calls.some((call) => call.url.startsWith('/api/knowledge/'))).toBe(false);
    fireEvent.change(screen.getByLabelText('搜索关键词'), { target: { value: 'Synthetic promoted entry' } });
    fireEvent.click(screen.getByRole('button', { name: '搜索' }));
    expect(await screen.findByRole('button', { name: /Synthetic promoted entry/ })).toBeTruthy();
    expect(await screen.findByText('来源已验证')).toBeTruthy();
    expect(calls.filter((call) => call.url === '/api/home').map((call) => call.url)).toEqual([]);
    fireEvent.click(screen.getByRole('button', { name: /Synthetic promoted entry/ }));
    expect(await screen.findByRole('heading', { name: 'Synthetic promoted entry' })).toBeTruthy();
    const knowledgeDetail = within(document.querySelector('.knowledge-detail') as HTMLElement);
    expect(knowledgeDetail.getByText('来源已验证')).toBeTruthy();
    expect(calls.filter((call) => call.url.startsWith('/api/knowledge/')).map((call) => call.url)).toEqual([
      '/api/knowledge/search?q=Synthetic+promoted+entry&limit=50', '/api/knowledge/items/opaque-verified',
    ]);

    fireEvent.click(screen.getByRole('button', { name: /Synthetic unverified/ }));
    expect(await within(document.querySelector('.knowledge-detail') as HTMLElement).findByText(/来源声明不可验证/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Synthetic missing provenance/ }));
    expect(await within(document.querySelector('.knowledge-detail') as HTMLElement).findByText('没有已验证的来源记录')).toBeTruthy();

    expect(calls.some((call) => call.url === '/api/notes' || call.url.startsWith('/api/notes/'))).toBe(false);
    expect(calls.some((call) => call.url === '/api/inbox?limit=100' || call.url.startsWith('/api/inbox/proposals'))).toBe(false);
    expect(calls.some((call) => call.url === '/api/chat' || call.url.startsWith('/api/chat/'))).toBe(false);
    expect(calls.every((call) => call.url.startsWith('/api/auth/') || call.url.startsWith('/api/inbox/summary')
      || call.url.startsWith('/api/capture/') || call.url.startsWith('/api/inbox/')
      || call.url.startsWith('/api/promote/') || call.url.startsWith('/api/knowledge/'))).toBe(true);
  }, 15_000);

  it('fails closed for Promote OFF and an explicit HTTP 423 without unlock, confirm or a success link', async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input); calls.push(url);
      return url === '/api/promote/review/preview' ? json({ detail: 'synthetic_promote_off' }, 423) : json({});
    });
    render(<PromotePreviewPanel locale="zh-CN" reviewPath={reviewPath} reviewSha256={reviewSha}
      targetFilename={preview.target_filename} title="Synthetic Review" promoteEnabled={false} />);
    expect(screen.getByText(/当前 App 已关闭正式入库/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '准备正式入库预览' }));
    expect(await screen.findByText(/正式入库已关闭/)).toBeTruthy();
    expect(calls).toEqual(['/api/promote/review/preview']);
    expect(screen.queryByLabelText('独立正式入库口令')).toBeNull();
    expect(screen.queryByRole('button', { name: /确认将此版本写入/ })).toBeNull();
    expect(screen.queryByRole('link', { name: '打开 Knowledge 搜索' })).toBeNull();
  });

  it('keeps recovery_required fail-closed after one confirmation and does not suggest success', async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input); calls.push(url);
      if (url === '/api/promote/review/preview') return json(preview);
      if (url === '/api/promote/auth/unlock') return json({ status: 'unlocked' });
      if (url === '/api/promote/review/confirm') return json({ request_id: requestId, status: 'confirmed' });
      if (url === `/api/promote/operations/${requestId}`) return json({ request_id: requestId, status: 'recovery_required', error_code: 'manual_review_required' });
      return json({}, 404);
    });
    render(<PromotePreviewPanel locale="zh-CN" reviewPath={reviewPath} reviewSha256={reviewSha}
      targetFilename={preview.target_filename} title="Synthetic Review" promoteEnabled />);
    fireEvent.click(screen.getByRole('button', { name: '准备正式入库预览' }));
    expect(await screen.findByLabelText('拟入库 Markdown 原文')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('独立正式入库口令'), { target: { value: 'synthetic-only-passphrase' } });
    fireEvent.click(screen.getByRole('button', { name: '独立解锁' }));
    fireEvent.click(await screen.findByRole('button', { name: '确认将此版本写入 Knowledge' }));
    expect(await screen.findByText('需要恢复核验，请勿再次提交确认。')).toBeTruthy();
    expect(calls.filter((url) => url === '/api/promote/review/confirm')).toHaveLength(1);
    expect(calls.filter((url) => url === `/api/promote/operations/${requestId}`)).toHaveLength(1);
    expect((screen.getByRole('button', { name: /确认将此版本写入/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByText('已将精确预览版本写入 Knowledge。')).toBeNull();
    expect(screen.queryByRole('link', { name: '打开 Knowledge 搜索' })).toBeNull();
  });

  it('opens only the exact Chat Inbox receipt and exposes a Review link only for its verified source version', async () => {
    const inboxId = 'f'.repeat(32);
    const sourceSha = 'e'.repeat(64);
    const sourcePath = '10-Review/synthetic-journal-source.md';
    vi.stubEnv('VITE_ENABLE_NOTES', 'false');
    history.replaceState({}, '', `/inbox#capture-${inboxId}`);
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input); calls.push(url);
      if (url === '/api/auth/session') return json({ authenticated: true });
      if (url === `/api/inbox/entries/${inboxId}`) return json({
        inbox_id: inboxId, status: 'processing', captured_at: '2026-10-21T08:00:00Z', occurred_at: '2026-10-21T07:59:00Z',
        source: { channel: 'web', event_id: 'synthetic-journal-event' }, intent: 'journal_intent',
        consent_evidence: { kind: 'authenticated_app_explicit_action', subject: 'synthetic-user', recorded_at: '2026-10-21T07:59:00Z' },
        approved_proposal: null,
        source_ref: { capture_id: inboxId, review_path: sourcePath, review_sha256: sourceSha },
      });
      if (url === '/api/promote/review/items') return json({ items: [{
        review_path: sourcePath, review_sha256: sourceSha, target_filename: 'Knowledge/synthetic-source.md',
        title: 'Synthetic linked source', status: 'pending', captured_at: '2026-10-21T08:00:00Z',
      }] });
      if (url === '/api/promote/status') return json({ promote_enabled: false });
      if (url === `/api/promote/review/items/${sourcePath}`) return json({
        review_path: sourcePath, review_sha256: sourceSha, target_filename: 'Knowledge/synthetic-source.md',
        title: 'Synthetic linked source', status: 'pending', content: '# Synthetic source only',
      });
      return json({ detail: 'unmatched synthetic route' }, 404);
    });

    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Inbox 条目状态' })).toBeTruthy();
    expect(await screen.findByText('处理中')).toBeTruthy();
    expect(screen.getByText(/不代表.*已完成写入/)).toBeTruthy();
    expect(screen.queryByText('Original private content')).toBeNull();
    expect(calls).toEqual(['/api/auth/session', `/api/inbox/entries/${inboxId}`]);
    fireEvent.click(screen.getByRole('button', { name: '打开已核验的 Review 来源' }));
    expect(await screen.findByText('Synthetic source only')).toBeTruthy();
    expect(location.pathname).toBe('/review');
    expect(new URLSearchParams(location.search).get('review_path')).toBe(sourcePath);
    expect(new URLSearchParams(location.search).get('source_sha256')).toBe(sourceSha);
    expect(calls).toContain(`/api/promote/review/items/${sourcePath}`);
    expect(calls.some((url) => url === '/api/inbox/summary?limit=100' || url === '/api/inbox?limit=100'
      || url.startsWith('/api/inbox/') && url !== `/api/inbox/entries/${inboxId}`)).toBe(false);
    expect(calls.some((url) => url === '/api/home' || url.startsWith('/api/knowledge/'))).toBe(false);
  });

  it('does not open a linked Review version when its hash changed since the Inbox source record', async () => {
    const inboxId = '9'.repeat(32);
    const originalSha = 'a'.repeat(64);
    const changedSha = 'b'.repeat(64);
    const sourcePath = '10-Review/synthetic-drift.md';
    vi.stubEnv('VITE_ENABLE_NOTES', 'false');
    history.replaceState({}, '', `/inbox#capture-${inboxId}`);
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input); calls.push(url);
      if (url === '/api/auth/session') return json({ authenticated: true });
      if (url === `/api/inbox/entries/${inboxId}`) return json({
        inbox_id: inboxId, status: 'completed', captured_at: '2026-10-21T08:00:00Z', occurred_at: '2026-10-21T07:59:00Z',
        source: { channel: 'web', event_id: 'synthetic-drift-event' }, intent: 'journal_intent',
        consent_evidence: { kind: 'authenticated_app_explicit_action', subject: 'synthetic-user', recorded_at: '2026-10-21T07:59:00Z' },
        approved_proposal: null,
        source_ref: { capture_id: inboxId, review_path: sourcePath, review_sha256: originalSha },
      });
      if (url === '/api/promote/review/items') return json({ items: [{
        review_path: sourcePath, review_sha256: changedSha, target_filename: 'Knowledge/drift.md',
        title: 'Synthetic changed source', status: 'pending',
      }] });
      if (url === '/api/promote/status') return json({ promote_enabled: false });
      return json({}, 404);
    });

    render(<App />);
    expect(await screen.findByRole('button', { name: '打开已核验的 Review 来源' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '打开已核验的 Review 来源' }));
    expect(await screen.findByText('关联的 Review 来源版本已变化；未打开来源正文。')).toBeTruthy();
    expect(calls.some((url) => url.startsWith('/api/promote/review/items/10-Review/'))).toBe(false);
    expect(screen.queryByText('Original private content')).toBeNull();
  });

  it('withholds Review content when its detail hash differs from the verified list version', async () => {
    const sourcePath = '10-Review/synthetic-detail-drift.md';
    const listedSha = '1'.repeat(64);
    const returnedSha = '2'.repeat(64);
    vi.stubEnv('VITE_ENABLE_NOTES', 'false');
    history.replaceState({}, '', `/review?review_path=${encodeURIComponent(sourcePath)}&source_sha256=${listedSha}`);
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input); calls.push(url);
      if (url === '/api/auth/session') return json({ authenticated: true });
      if (url === '/api/promote/review/items') return json({ items: [{
        review_path: sourcePath, review_sha256: listedSha, target_filename: 'Knowledge/drift.md',
        title: 'Synthetic listed source', status: 'pending',
      }] });
      if (url === `/api/promote/review/items/${sourcePath}`) return json({
        review_path: sourcePath, review_sha256: returnedSha, target_filename: 'Knowledge/drift.md',
        title: 'Synthetic changed source', status: 'pending', content: 'PRIVATE SYNTHETIC BODY MUST NOT RENDER',
      });
      if (url === '/api/promote/status') return json({ promote_enabled: false });
      return json({}, 404);
    });

    render(<App />);
    expect(await screen.findByText('打开时 Review 来源版本发生变化；未展示来源正文。')).toBeTruthy();
    expect(screen.queryByText('PRIVATE SYNTHETIC BODY MUST NOT RENDER')).toBeNull();
    expect(calls).toContain(`/api/promote/review/items/${sourcePath}`);
    expect(calls).not.toContain('/api/promote/review/preview');
    expect(calls).not.toContain('/api/promote/auth/unlock');
    expect(calls).not.toContain('/api/promote/review/confirm');
  });

  it.each([
    [401, '登录状态已失效；重新登录后可核验此 Inbox 条目。'],
    [403, '当前账户无权读取此 Inbox 条目。'],
    [503, 'Inbox 状态暂时不可用；当前状态未核验。'],
  ])('shows a safe HTTP %i state and never offers a source link', async (status, expectedMessage) => {
    const inboxId = '8'.repeat(32);
    vi.stubEnv('VITE_ENABLE_NOTES', 'false');
    history.replaceState({}, '', `/inbox#capture-${inboxId}`);
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input); calls.push(url);
      if (url === '/api/auth/session') return json({ authenticated: true });
      if (url === `/api/inbox/entries/${inboxId}`) return json({ detail: 'synthetic-secret-detail-must-not-display' }, status);
      return json({}, 404);
    });

    render(<App />);
    expect(await screen.findByText(expectedMessage)).toBeTruthy();
    expect(screen.queryByRole('button', { name: '打开已核验的 Review 来源' })).toBeNull();
    expect(document.body.textContent).not.toContain('synthetic-secret-detail-must-not-display');
    expect(calls).toEqual(['/api/auth/session', `/api/inbox/entries/${inboxId}`]);
  });
});
