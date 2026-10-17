import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ChatPage, InboxPage, ReviewPage, scrollReviewItemIntoView, sortByCapturedAt } from './App';
import { UnifiedCaptureComposer } from './UnifiedCaptureComposer';

afterEach(() => { cleanup(); window.history.replaceState({}, '', '/'); vi.unstubAllGlobals(); vi.useRealTimers(); });

const callbacks = () => ({ onComplete: vi.fn(), onGoInbox: vi.fn() });
const TestCaptureComposer = ({ locale, onGoInbox = () => undefined }: { locale: 'zh-CN' | 'en'; onGoInbox?: () => void }) => <UnifiedCaptureComposer locale={locale} onComplete={() => undefined} onGoInbox={onGoInbox} />;
const ok = (body: unknown, contentType = 'application/json') => ({
  ok: true, status: 200, headers: { get: () => contentType },
  json: async () => body, text: async () => typeof body === 'string' ? body : JSON.stringify(body),
});

describe('D075.1 capture interactions', () => {
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

  it('routes an explicit Journal phrase directly without creating a Hermes run', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    const request = vi.fn().mockResolvedValueOnce(ok({ sessions: [] })).mockResolvedValueOnce(ok({ status: 'created', date: '2026-10-17' }));
    vi.stubGlobal('fetch', request);
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    const input = await screen.findByPlaceholderText('发送消息给 Hermes…');
    const original = '  记一下：测试时完整保留空格  ';
    fireEvent.change(input, { target: { value: original } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    expect(await screen.findByText(/已保存到 2026-10-17 的 Journal，原话已保留/)).toBeTruthy();
    expect(request).toHaveBeenCalledTimes(2);
    expect(request.mock.calls[1][0]).toBe('/api/journal/entries');
    expect(JSON.parse(request.mock.calls[1][1].body)).toEqual({ text: original });
    expect(new Headers(request.mock.calls[1][1].headers).get('Idempotency-Key')).toBeTruthy();
    expect((input as HTMLTextAreaElement).value).toBe('');
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
  });

  it('keeps explicit Journal text on failure and safely retries with the same idempotency key', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    const request = vi.fn().mockResolvedValueOnce(ok({ sessions: [] }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Journal append failed safely' }), { status: 500 }))
      .mockResolvedValueOnce(ok({ status: 'created', date: '2026-10-17' }));
    vi.stubGlobal('fetch', request);
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    const input = await screen.findByPlaceholderText('发送消息给 Hermes…');
    fireEvent.change(input, { target: { value: '记一下：失败后保留' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    expect((await screen.findByRole('alert')).textContent).toMatch(/Journal append failed safely/);
    expect((input as HTMLTextAreaElement).value).toBe('记一下：失败后保留');
    const firstKey = new Headers(request.mock.calls[1][1].headers).get('Idempotency-Key');
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    expect(await screen.findByText(/已保存到 2026-10-17 的 Journal/)).toBeTruthy();
    expect(new Headers(request.mock.calls[2][1].headers).get('Idempotency-Key')).toBe(firstKey);
    expect(request.mock.calls.every(([url]) => url === '/api/chat/sessions?limit=50&offset=0' || url === '/api/journal/entries')).toBe(true);
  });

  it('reports disabled Journal without clearing the input or pretending it was saved', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    const request = vi.fn().mockResolvedValueOnce(ok({ sessions: [] }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Journal is not enabled' }), { status: 503 }));
    vi.stubGlobal('fetch', request);
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    const input = await screen.findByPlaceholderText('发送消息给 Hermes…');
    fireEvent.change(input, { target: { value: '记一下：Journal 未启用' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    expect((await screen.findByRole('alert')).textContent).toMatch(/当前环境未启用 Journal/);
    expect((input as HTMLTextAreaElement).value).toBe('记一下：Journal 未启用');
    expect(screen.queryByText(/已保存到 .* Journal/)).toBeNull();
  });

  it('creates an explicit Task directly and preserves its command on failure for same-key retry', async () => {
    window.localStorage.clear(); window.sessionStorage.clear();
    const request = vi.fn().mockResolvedValueOnce(ok({ sessions: [] }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Task update failed safely' }), { status: 500 }))
      .mockResolvedValueOnce(ok({ status: 'created', task: { title: '测试任务' } }));
    vi.stubGlobal('fetch', request);
    render(<ChatPage locale="zh-CN" onGoInbox={vi.fn()} />);
    const input = await screen.findByPlaceholderText('发送消息给 Hermes…');
    fireEvent.change(input, { target: { value: '添加待办：测试任务 截止：2026-10-20' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    expect((await screen.findByRole('alert')).textContent).toMatch(/Task update failed safely/);
    expect((input as HTMLTextAreaElement).value).toBe('添加待办：测试任务 截止：2026-10-20');
    const firstKey = new Headers(request.mock.calls[1][1].headers).get('Idempotency-Key');
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    expect(await screen.findByText(/待办已创建/)).toBeTruthy();
    expect(request).toHaveBeenCalledTimes(3);
    expect(request.mock.calls[1][0]).toBe('/api/tasks');
    expect(JSON.parse(request.mock.calls[1][1].body)).toEqual({ title: '测试任务', due_date: '2026-10-20', original_command: '添加待办：测试任务 截止：2026-10-20' });
    expect(new Headers(request.mock.calls[2][1].headers).get('Idempotency-Key')).toBe(firstKey);
    expect(request.mock.calls.every(([url]) => url !== '/api/chat/sessions' && !String(url).includes('/runs'))).toBe(true);
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

  it('orders Reviews by verified capture time, joins legacy dates from exact Inbox paths, and keeps unknown last', async () => {
    const review = (review_path: string, captured_at?: string | null) => ({
      review_path, review_sha256: review_path, target_filename: review_path,
      title: review_path, status: 'pending', captured_at, content: `# ${review_path}`,
    });
    const reviews = [review('old.md', '2026-10-10T00:00:00Z'), review('date-only.md', '2026-10-13'), review('legacy.md'), review('unknown.md')];
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/review/items')) return ok({ items: reviews });
      if (url.includes('/api/inbox')) return ok({ items: [
        { capture_id: 'legacy-source', captured_at: '2026-10-15T00:00:00Z', review_path: 'legacy.md' },
      ] });
      if (url.endsWith('/status')) return ok({ promote_enabled: false });
      return ok(reviews.find((item) => url.endsWith(item.review_path)));
    }));
    const { container } = render(<ReviewPage locale="zh-CN" onBack={vi.fn()} />);
    await screen.findByText('legacy.md', { selector: '.review-page-item strong' });
    const titles = [...container.querySelectorAll('.review-page-item strong')].map((node) => node.textContent);
    expect(titles).toEqual(['legacy.md', 'date-only.md', 'old.md', 'unknown.md']);
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
