import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { InboxPage, QuickCapture, ReviewPage, scrollReviewItemIntoView } from './App';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const callbacks = () => ({ onClose: vi.fn(), onComplete: vi.fn(), onGoInbox: vi.fn() });
const ok = (body: unknown, contentType = 'application/json') => ({
  ok: true, status: 200, headers: { get: () => contentType },
  json: async () => body, text: async () => typeof body === 'string' ? body : JSON.stringify(body),
});

describe('D075.1 capture interactions', () => {
  it('accepts a single dropped file and allows removing it', async () => {
    const props = callbacks();
    render(<QuickCapture locale="zh-CN" {...props} />);
    fireEvent.click(screen.getByRole('button', { name: '文件' }));
    const file = new File(['hello'], 'notes.txt', { type: 'text/plain' });
    const dropzone = screen.getByText('将一个文件拖到这里').closest('.capture-dropzone')!;
    fireEvent.dragEnter(dropzone, { dataTransfer: { files: [file] } });
    fireEvent.drop(dropzone, { dataTransfer: { files: [file] } });
    expect(await screen.findByText('notes.txt')).toBeTruthy();
    expect(screen.getByText(/KiB/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '撤销' }));
    expect(screen.queryByText('notes.txt')).toBeNull();
  });

  it('clears input only after server confirms Raw and keeps the result actions', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ capture_id: 'a'.repeat(32), raw_path: 'note.md', status: 'processing' })));
    const props = callbacks();
    render(<QuickCapture locale="zh-CN" {...props} />);
    const input = screen.getByPlaceholderText('粘贴文本…') as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: 'keep this capture' } });
    fireEvent.change(screen.getByPlaceholderText('补充说明（可选）'), { target: { value: 'context' } });
    fireEvent.click(screen.getByRole('button', { name: '保存到收件箱' }));
    await screen.findByText('note.md');
    expect(input.value).toBe('');
    expect((screen.getByPlaceholderText('补充说明（可选）') as HTMLInputElement).value).toBe('');
    expect(screen.getByRole('button', { name: '继续收录' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '前往收件箱' }));
    expect(props.onGoInbox).toHaveBeenCalledOnce();
  });

  it('preserves text when the server rejects capture before Raw is saved', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 400, json: async () => ({ detail: 'invalid input' }) }));
    render(<QuickCapture locale="zh-CN" {...callbacks()} />);
    const input = screen.getByPlaceholderText('粘贴文本…') as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: 'retry this' } });
    fireEvent.click(screen.getByRole('button', { name: '保存到收件箱' }));
    await screen.findByRole('alert');
    expect(input.value).toBe('retry this');
  });

  it('does not issue duplicate requests while a capture is in flight', async () => {
    let resolveResponse!: (value: unknown) => void;
    const pending = new Promise((resolve) => { resolveResponse = resolve; });
    const request = vi.fn().mockReturnValue(pending);
    vi.stubGlobal('fetch', request);
    render(<QuickCapture locale="zh-CN" {...callbacks()} />);
    fireEvent.change(screen.getByPlaceholderText('粘贴文本…'), { target: { value: 'single request' } });
    const form = screen.getByPlaceholderText('粘贴文本…').closest('form')!;
    fireEvent.submit(form); fireEvent.submit(form);
    expect(request).toHaveBeenCalledTimes(1);
    resolveResponse(ok({ capture_id: 'e'.repeat(32), raw_path: 'single.md', status: 'completed' }));
    await screen.findByText('single.md');
  });

  it('routes to the exact associated Review and renders that selected detail', async () => {
    const item = { capture_id: 'b'.repeat(32), source_type: 'text', input_type: 'md', captured_at: '2026-10-14T00:00:00Z', original_asset: '/raw/x.md', raw_path: 'x.md', review_path: 'nested/exact.md', status: 'completed', title: 'Inbox source' };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ items: [item] })));
    const onReview = vi.fn();
    render(<InboxPage locale="zh-CN" onCapture={vi.fn()} onReview={onReview} />);
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

  it('renders Review body without frontmatter and keeps full metadata collapsible', async () => {
    const review = {
      review_path: 'scan.md', review_sha256: 'hash', target_filename: 'scan.md',
      title: '扫描资料', status: 'pending',
      content: '---\ntype: "review"\nsource_type: "pdf"\ncaptured_at: "2026-10-15T08:00:00Z"\noriginal_asset: "/inbox/scan.pdf"\n---\n# 扫描资料\n\n正文第一行\n正文第二行',
    };
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => String(input).endsWith('/review/items') ? ok({ items: [review] }) : String(input).endsWith('/status') ? ok({ promote_enabled: false }) : ok(review)));
    const { container } = render(<ReviewPage locale="zh-CN" onBack={vi.fn()} />);
    await waitFor(() => expect(container.querySelector('.review-markdown')?.textContent).toContain('正文第一行'));
    expect(container.querySelector('.review-page-detail')?.textContent).not.toContain('type: "review"');
    expect(screen.getByRole('heading', { level: 2, name: '扫描资料' })).toBeTruthy();
    expect(screen.getByText('完整元数据')).toBeTruthy();
    expect(screen.getAllByText('2026-10-15T08:00:00Z').length).toBe(2);
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
    expect(await screen.findByText('第一行：编号 A-01', { exact: false })).toBeTruthy();
    expect(container.querySelector('.review-markdown-raw')?.textContent).toContain('第二行  key: value');
    expect(screen.getByText('OCR 识别可能存在误差，请对照原件核对。')).toBeTruthy();
  });

  it('shows a safe text preview and download separately', async () => {
    const item = { capture_id: 'd'.repeat(32), source_type: 'markdown', input_type: 'md', captured_at: '2026-10-14T00:00:00Z', original_asset: '/raw/readme.md', raw_path: 'readme.md', status: 'completed', title: 'Read me', content_preview: '# safe' };
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => String(input).endsWith('/preview') ? ok('# Safe text\n<script>text only</script>', 'text/plain') : ok({ items: [item] })));
    render(<InboxPage locale="zh-CN" onCapture={vi.fn()} onReview={vi.fn()} />);
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
    const { container } = render(<InboxPage locale="zh-CN" onCapture={vi.fn()} onReview={vi.fn()} />);
    await screen.findByRole('heading', { name: 'p.png' });
    expect(screen.getByText('文字识别完成，画面理解暂未接入。')).toBeTruthy();
    expect(container.querySelector('.capture-alert')).toBeNull();
    expect(screen.queryByRole('button', { name: '重试处理' })).toBeNull();
  });

  it('keeps retry and a clear error for actual OCR failures without a Review', async () => {
    const item = { capture_id: 'c'.repeat(32), source_type: 'image', input_type: 'png', captured_at: '2026-10-14T00:00:00Z', original_asset: '/raw/p.png', raw_path: 'p.png', status: 'partial_success', title: 'p', error: { code: 'processing_failed', message: 'Image OCR exceeded its time limit' } };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ items: [item] })));
    render(<InboxPage locale="zh-CN" onCapture={vi.fn()} onReview={vi.fn()} />);
    await screen.findByRole('heading', { name: 'p.png' });
    expect(screen.getByText('Image OCR exceeded its time limit')).toBeTruthy();
    expect(screen.getByRole('button', { name: '重试处理' })).toBeTruthy();
  });

  it('shows the validated upload filename instead of PDF metadata and falls back to the legacy Raw filename', async () => {
    const newer = { capture_id: 'f'.repeat(32), source_type: 'pdf', input_type: 'pdf', captured_at: '2026-10-14T00:00:00Z', original_asset: '/raw/safe.pdf', raw_path: 'safe.pdf', status: 'completed', title: 'safe', display_filename: '会议纪要.pdf', document_title: '(anonymous)' };
    const legacy = { ...newer, capture_id: 'e'.repeat(32), display_filename: undefined, raw_path: '旧版计划.pdf', title: '(anonymous)' };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ items: [newer, legacy] })));
    render(<InboxPage locale="zh-CN" onCapture={vi.fn()} onReview={vi.fn()} />);

    expect(await screen.findByRole('heading', { name: '会议纪要.pdf' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: '旧版计划.pdf' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: '(anonymous)' })).toBeNull();
  });

  it('does not offer a Review action when no Review path exists', async () => {
    const item = { capture_id: 'c'.repeat(32), source_type: 'image', input_type: 'png', captured_at: '2026-10-14T00:00:00Z', original_asset: '/raw/p.png', raw_path: 'p.png', status: 'partial_success', title: 'Image', error: { code: 'processor_unavailable', message: 'No processor' } };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ items: [item] })));
    render(<InboxPage locale="zh-CN" onCapture={vi.fn()} onReview={vi.fn()} />);
    await screen.findByRole('heading', { name: 'p.png' });
    expect(screen.queryByRole('button', { name: '查看 Review' })).toBeNull();
    expect(screen.getByText('No processor')).toBeTruthy();
  });
});
