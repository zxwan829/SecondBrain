import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { PromotePreviewPanel } from './PromotePreviewPanel';

const preview = {
  preview_id: 'preview-synthetic-1', request_id: 'request-synthetic-1', expires_at: '2099-01-01T00:00:00Z',
  source_sha256: 'a'.repeat(64), target_filename: 'Knowledge/synthetic-note.md',
  target_precondition: { exists: false },
  source_markdown: '---\ntype: note\n# source comment\n---\n<!-- provenance: synthetic -->\n# Source note\n\nSynthetic source body.\n',
  projected_markdown: '---\ntype: note\n# projected comment\n---\n<!-- provenance: synthetic -->\n# Projected note\n\nSynthetic projected body.\n',
  output_sha256: 'b'.repeat(64), change_summary: ['Server added the approved type.', 'Target does not exist.'],
};
type PreviewFixture = typeof preview;
type OperationFixture = { request_id: string; status: string; output_sha256: string };

function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
}

const nonCanonicalPreviewCases: Array<[string, (value: PreviewFixture) => unknown]> = [
  ['missing absolute expiry', ({ expires_at: _expires_at, ...rest }) => rest],
  ['relative expiry only', ({ expires_at: _expires_at, ...rest }) => ({ ...rest, expires_in: 600 })],
  ['legacy source hash name', ({ source_sha256: _source_sha256, ...rest }) => ({ ...rest, review_sha256: preview.source_sha256 })],
  ['missing target precondition', ({ target_precondition: _target_precondition, ...rest }) => rest],
  ['legacy target availability field', ({ target_precondition: _target_precondition, ...rest }) => ({ ...rest, target_available: true })],
  ['object change summary', (value) => ({ ...value, change_summary: { changed: ['title'] } })],
  ['expiry without an absolute timezone', (value) => ({ ...value, expires_at: '2099-01-01T00:00:00' })],
  ['invalid calendar date', (value) => ({ ...value, expires_at: '2099-02-31T00:00:00Z' })],
];

const mismatchedOperationCases: Array<[string, (value: OperationFixture) => unknown]> = [
  ['different request ID', (value) => ({ ...value, request_id: 'request-other' })],
  ['different output hash', (value) => ({ ...value, output_sha256: 'c'.repeat(64) })],
];

function renderPanel(promoteEnabled = true) {
  return render(<PromotePreviewPanel locale="zh-CN" reviewPath="10-Review/synthetic.md"
    reviewSha256={preview.source_sha256} targetFilename={preview.target_filename}
    title="Synthetic Review" promoteEnabled={promoteEnabled} />);
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('Promote preview panel', () => {
  it('makes no request on mount and shows the complete server preview after an explicit action', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(preview));
    renderPanel(false);
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getByText('当前 App 已关闭正式入库。预览不会写入，解锁与确认不可用。')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /确认将此版本写入/ })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '准备正式入库预览' }));
    expect(await screen.findByLabelText('拟入库 Markdown 原文')).toBeTruthy();
    expect(screen.getByLabelText('来源 Markdown 原文')).toBeTruthy();
    expect(screen.getByText(preview.target_filename)).toBeTruthy();
    expect(screen.getByText(preview.output_sha256)).toBeTruthy();
    expect(screen.getByText('Target does not exist.')).toBeTruthy();
    expect(screen.getByLabelText('来源 Markdown 原文').textContent).toBe(preview.source_markdown);
    expect(screen.getByLabelText('拟入库 Markdown 原文').textContent).toBe(preview.projected_markdown);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(String(fetch.mock.calls[0][0])).toBe('/api/promote/review/preview');
    expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({
      review_path: '10-Review/synthetic.md', review_sha256: preview.source_sha256,
      target_filename: preview.target_filename,
    });
    expect(screen.queryByLabelText('独立正式入库口令')).toBeNull();
    expect(screen.queryAllByRole('link')).toHaveLength(0);
  });

  it('requires preview, independent unlock, explicit one-time confirm and server status before saying complete', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    let operationReads = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input); calls.push({ url, init });
      if (url === '/api/promote/review/preview') return json(preview);
      if (url === '/api/promote/auth/unlock') return json({ status: 'unlocked' });
      if (url === '/api/promote/review/confirm') return json({ request_id: preview.request_id, status: 'confirmed' });
      if (url === `/api/promote/operations/${preview.request_id}`) {
        operationReads += 1;
        return json({ request_id: preview.request_id, status: operationReads === 1 ? 'confirmed' : 'promoted', output_sha256: preview.output_sha256 });
      }
      if (url === '/api/promote/auth/lock') return json({ status: 'locked' });
      return json({ detail: 'synthetic unmatched path' }, 404);
    });
    const page = renderPanel();
    expect(calls).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: '准备正式入库预览' }));
    await screen.findByLabelText('拟入库 Markdown 原文');
    expect(screen.queryByRole('button', { name: /确认将此版本写入/ })).toBeNull();

    fireEvent.change(screen.getByLabelText('独立正式入库口令'), { target: { value: 'synthetic-test-password' } });
    fireEvent.click(screen.getByRole('button', { name: '独立解锁' }));
    await screen.findByRole('button', { name: /确认将此版本写入/ });
    expect(screen.queryByLabelText('独立正式入库口令')).toBeNull();
    const unlockCall = calls.find((call) => call.url === '/api/promote/auth/unlock')!;
    expect(JSON.parse(String(unlockCall.init?.body))).toEqual({ passphrase: 'synthetic-test-password' });
    expect(unlockCall.init?.credentials).toBe('same-origin');
    expect(unlockCall.init?.cache).toBe('no-store');

    fireEvent.click(screen.getByRole('button', { name: /确认将此版本写入/ }));
    expect(await screen.findByText('已确认；执行结果尚未核验。')).toBeTruthy();
    const confirmCalls = calls.filter((call) => call.url === '/api/promote/review/confirm');
    expect(confirmCalls).toHaveLength(1);
    expect(JSON.parse(String(confirmCalls[0].init?.body))).toEqual({
      preview_id: preview.preview_id, confirm_intent: 'promote_exact_preview',
    });
    expect(screen.queryByText('已将精确预览版本写入 Knowledge。')).toBeNull();
    expect((screen.getByRole('button', { name: /确认将此版本写入/ }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: '查询操作状态' }));
    expect(await screen.findByText('已将精确预览版本写入 Knowledge。')).toBeTruthy();
    expect(screen.getByRole('link', { name: '打开 Knowledge 搜索' }).getAttribute('href')).toBe('/knowledge');
    expect(calls.filter((call) => call.url === `/api/promote/operations/${preview.request_id}`)).toHaveLength(2);
    expect(calls.some((call) => call.url === '/api/promote/review/approve')).toBe(false);
    page.unmount();
    await waitFor(() => expect(calls.some((call) => call.url === '/api/promote/auth/lock')).toBe(true));
  });

  it('does not replay a confirmation whose response is lost; it queries the operation instead', async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input); calls.push(url);
      if (url === '/api/promote/review/preview') return json(preview);
      if (url === '/api/promote/auth/unlock') return json({ status: 'ok' });
      if (url === '/api/promote/review/confirm') throw new TypeError('synthetic connection loss');
      if (url === `/api/promote/operations/${preview.request_id}`) return json({ request_id: preview.request_id, status: 'promoting' });
      return json({}, 404);
    });
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '准备正式入库预览' }));
    await screen.findByLabelText('拟入库 Markdown 原文');
    fireEvent.change(screen.getByLabelText('独立正式入库口令'), { target: { value: 'synthetic-test-password' } });
    fireEvent.click(screen.getByRole('button', { name: '独立解锁' }));
    fireEvent.click(await screen.findByRole('button', { name: /确认将此版本写入/ }));
    expect(await screen.findByText(/确认结果未知/)).toBeTruthy();
    expect(calls.filter((url) => url === '/api/promote/review/confirm')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: '查询操作状态' }));
    expect(await screen.findByText('正在执行，尚不能视为成功。')).toBeTruthy();
    expect(calls.filter((url) => url === '/api/promote/review/confirm')).toHaveLength(1);
    expect(screen.queryByText('已将精确预览版本写入 Knowledge。')).toBeNull();
  });

  it('does not allow an expired preview to be unlocked or confirmed', async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input); calls.push(url);
      if (url === '/api/promote/review/preview') return json({ ...preview, expires_at: '2000-01-01T00:00:00Z' });
      if (url === '/api/promote/auth/unlock') return json({ status: 'unlocked' });
      return json({}, 404);
    });
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '准备正式入库预览' }));
    await screen.findByLabelText('拟入库 Markdown 原文');
    expect((screen.getByRole('button', { name: '独立解锁' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole('button', { name: /确认将此版本写入/ })).toBeNull();
    expect(screen.getByText('预览已过期，不能确认。')).toBeTruthy();
    expect(calls).not.toContain('/api/promote/auth/unlock');
    expect(calls).not.toContain('/api/promote/review/confirm');
  });

  it.each(nonCanonicalPreviewCases)('rejects non-canonical preview JSON (%s)', async (_name, alter) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(alter(preview) as typeof preview));
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '准备正式入库预览' }));
    expect(await screen.findByText('无法安全完成正式入库操作。')).toBeTruthy();
    expect(screen.queryByLabelText('拟入库 Markdown 原文')).toBeNull();
  });

  it.each(mismatchedOperationCases)('does not claim a successful operation with %s', async (_name, alter) => {
    const calls: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input); calls.push(url);
      if (url === '/api/promote/review/preview') return json(preview);
      if (url === '/api/promote/auth/unlock') return json({ status: 'unlocked' });
      if (url === '/api/promote/review/confirm') return json({ request_id: preview.request_id, status: 'confirmed' });
      if (url === `/api/promote/operations/${preview.request_id}`) return json(alter({
        request_id: preview.request_id, status: 'promoted', output_sha256: preview.output_sha256,
      }));
      return json({}, 404);
    });
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '准备正式入库预览' }));
    await screen.findByLabelText('拟入库 Markdown 原文');
    fireEvent.change(screen.getByLabelText('独立正式入库口令'), { target: { value: 'synthetic-test-passphrase' } });
    fireEvent.click(screen.getByRole('button', { name: '独立解锁' }));
    fireEvent.click(await screen.findByRole('button', { name: /确认将此版本写入/ }));
    expect(await screen.findByText(/确认结果未知/)).toBeTruthy();
    expect(screen.queryByText('已将精确预览版本写入 Knowledge。')).toBeNull();
    expect(calls.filter((url) => url === '/api/promote/review/confirm')).toHaveLength(1);
  });

  it('requires a fresh preview after a stale response and never exposes raw error details', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json({ detail: '/private/synthetic/path' }, 409));
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '准备正式入库预览' }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByText(/所选 Review 或目标已变化/)).toBeTruthy();
    expect(screen.queryByText('/private/synthetic/path')).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it.each([
    [401, 'App 登录或独立入库解锁已失效。'],
    [403, '请求未通过 Host、Origin 或传输安全校验。'],
    [409, '所选 Review 或目标已变化，请重新生成预览。'],
    [410, '预览已过期，请重新生成。'],
    [423, '正式入库已关闭；没有确认任何 Knowledge 写入。'],
    [429, '操作过于频繁，请稍后重试。'],
    [503, '操作需要恢复核验，请勿重复确认。'],
  ])('maps HTTP %i to a fixed safe message', async (status, message) => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ detail: '/private/should-not-appear' }, status));
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '准备正式入库预览' }));
    expect(await screen.findByText(message)).toBeTruthy();
    expect(screen.queryByText('/private/should-not-appear')).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
