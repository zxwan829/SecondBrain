import React, { useEffect, useRef, useState } from 'react';

type Locale = 'zh-CN' | 'en';
type Capture = {
  capture_id: string;
  raw_path: string;
  review_path?: string | null;
  status: string;
  error?: { message?: string } | null;
};

const ACCEPTED_FILES = '.txt,.md,.markdown,.pdf,.png,.jpg,.jpeg,.webp,.gif,.wav,.mp3,.m4a,.aac,.ogg,.flac';
const ACCEPTED_NAME = /\.(txt|md|markdown|pdf|png|jpe?g|webp|gif|wav|mp3|m4a|aac|ogg|flac)$/i;
const MAX_FILE_SIZE = 20 * 1024 * 1024;

function validHttpUrl(value: string): boolean {
  if (!value || /\s/.test(value)) return false;
  try {
    const url = new URL(value);
    return (url.protocol === 'http:' || url.protocol === 'https:') && Boolean(url.hostname);
  } catch { return false; }
}

function pasteImageName(type: string): string {
  const extension = type === 'image/jpeg' ? 'jpg' : type.split('/')[1]?.replace('svg+xml', 'svg') || 'png';
  return `pasted-image.${extension}`;
}

function statusLabel(status: string, en: boolean): string {
  const labels: Record<string, [string, string]> = {
    receiving: ['接收中', 'Receiving'], processing: ['处理中', 'Processing'],
    completed: ['已完成', 'Completed'], partial_success: ['部分成功', 'Partial success'], failed: ['失败', 'Failed'],
  };
  return (labels[status] ?? labels.receiving)[en ? 1 : 0];
}

function formatSize(size: number): string {
  return size < 1024 * 1024 ? `${(size / 1024).toFixed(1)} KiB` : `${(size / (1024 * 1024)).toFixed(2)} MiB`;
}

export function UnifiedCaptureComposer({ locale, onComplete, onGoInbox }: {
  locale: Locale;
  onComplete: () => void;
  onGoInbox: () => void;
}) {
  const en = locale === 'en';
  const [value, setValue] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [filePreview, setFilePreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [result, setResult] = useState<Capture | null>(null);
  const [error, setError] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const submitting = useRef(false);

  useEffect(() => {
    if (!file || !file.type.startsWith('image/')) { setFilePreview(null); return; }
    const url = URL.createObjectURL(file);
    setFilePreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    if (!result || result.status !== 'processing') return;
    let active = true;
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(`/api/capture/${encodeURIComponent(result.capture_id)}`, { credentials: 'same-origin' });
        if (!response.ok) return;
        const latest = await response.json() as Capture;
        if (!active) return;
        setResult(latest);
        if (latest.status !== 'processing') onComplete();
      } catch { /* The Inbox remains the durable view after a transient disconnect. */ }
    }, 900);
    return () => { active = false; window.clearInterval(timer); };
  }, [result?.capture_id, result?.status, onComplete]);

  const acceptFile = (candidate?: File) => {
    if (!candidate || busy) return;
    if (!ACCEPTED_NAME.test(candidate.name)) {
      setError(en ? 'This file type is not supported.' : '此文件类型不受支持。');
      return;
    }
    if (candidate.size > MAX_FILE_SIZE) {
      setError(en ? 'Files must be 20 MiB or smaller.' : '文件不能超过 20 MiB。');
      return;
    }
    setError(''); setResult(null); setFile(candidate);
  };

  const submit = async (event?: React.FormEvent) => {
    event?.preventDefault();
    if (submitting.current || busy || (!file && !value.trim())) return;
    if (file && value.length > 2000) {
      setError(en ? 'Attachment notes must be 2,000 characters or fewer.' : '附件补充说明最多 2,000 个字符。');
      return;
    }
    submitting.current = true; setBusy(true); setError(''); setResult(null);
    try {
      let response: Response;
      if (file) {
        const form = new FormData();
        form.set('file', file);
        form.set('capture_context', value);
        response = await fetch('/api/capture/files', { method: 'POST', credentials: 'same-origin', body: form });
      } else if (validHttpUrl(value.trim())) {
        response = await fetch('/api/capture/url', {
          method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: value.trim(), capture_context: '' }),
        });
      } else {
        response = await fetch('/api/capture/text', {
          method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: value, source_type: 'text', capture_context: '' }),
        });
      }
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
      if (!payload.capture_id || !payload.raw_path) {
        throw new Error(en ? 'The server did not confirm that the original was saved. Your input is still here.' : '服务器未确认原件已保存，输入已保留。');
      }
      setValue(''); setFile(null);
      if (fileInput.current) fileInput.current.value = '';
      setResult(payload as Capture); onComplete();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { submitting.current = false; setBusy(false); }
  };

  const handlePaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const image = Array.from(event.clipboardData.items).find((item) => item.type.startsWith('image/'));
    if (!image) return; // Keep ordinary text paste native.
    const blob = image.getAsFile();
    if (!blob) return;
    event.preventDefault();
    acceptFile(new File([blob], pasteImageName(blob.type), { type: blob.type, lastModified: Date.now() }));
  };

  const removeFile = () => {
    setFile(null); setError('');
    if (fileInput.current) fileInput.current.value = '';
  };

  return <section
    className={`unified-composer ${dragOver ? 'is-drag-over' : ''}`}
    aria-label={en ? 'Quick capture' : '快速收录'}
    onDragEnter={(event) => { if (event.dataTransfer.types.includes('Files')) { event.preventDefault(); setDragOver(true); } }}
    onDragOver={(event) => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); }}
    onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragOver(false); }}
    onDrop={(event) => { if (event.dataTransfer.files.length) { event.preventDefault(); setDragOver(false); acceptFile(event.dataTransfer.files[0]); } }}
  >
    <form onSubmit={(event) => void submit(event)}>
      <textarea
        ref={textarea}
        aria-label={en ? 'Capture content' : '收录内容'}
        maxLength={file ? 2000 : 200000}
        disabled={busy}
        value={value}
        onChange={(event) => { setValue(event.target.value); if (result) setResult(null); }}
        onPaste={handlePaste}
        onKeyDown={(event) => {
          if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return;
          event.preventDefault(); void submit();
        }}
        placeholder={en ? 'Write, paste a URL, or add a file…' : '写点什么、粘贴网址，或添加文件…'}
      />
      {file && <div className="unified-attachment" aria-label={en ? 'Pending attachment' : '待发送附件'}>
        {filePreview ? <img src={filePreview} alt={file.name} /> : <span className="unified-attachment-icon" aria-hidden="true">{file.name.split('.').pop()?.toUpperCase()}</span>}
        <span className="unified-attachment-copy"><strong>{file.name}</strong><small>{file.type || file.name.split('.').pop()?.toUpperCase()} · {formatSize(file.size)}</small></span>
        <button type="button" className="unified-attachment-replace" onClick={() => fileInput.current?.click()}>{en ? 'Replace' : '更换'}</button>
        <button type="button" className="unified-attachment-remove" aria-label={en ? 'Remove attachment' : '移除附件'} onClick={removeFile}>×</button>
      </div>}
      <input ref={fileInput} className="unified-file-input" type="file" accept={ACCEPTED_FILES} aria-label={en ? 'Choose attachment' : '选择附件'} onChange={(event) => { acceptFile(event.target.files?.[0]); event.currentTarget.value = ''; }} />
      {error && <p role="alert" className="capture-alert">{error}</p>}
      {result && <div role="status" className={`capture-result capture-result-${result.status}`}>
        <strong>{statusLabel(result.status, en)}</strong>
        <span>{result.status === 'partial_success'
          ? `${en ? 'Original saved: ' : '原件已保存：'}${result.raw_path}. ${result.error?.message || ''}`
          : result.error?.message || result.review_path || result.raw_path}</span>
        <div className="unified-result-actions">
          <button type="button" className="capture-secondary" onClick={() => { setResult(null); setError(''); textarea.current?.focus(); }}>{en ? 'Continue capture' : '继续收录'}</button>
          <button type="button" className="capture-primary" onClick={onGoInbox}>{en ? 'Go to Inbox' : '前往收件箱'}</button>
        </div>
      </div>}
      {!result && <footer className="unified-composer-toolbar">
        <button type="button" className="unified-add-button" aria-label={file ? (en ? 'Replace attachment' : '更换附件') : (en ? 'Add attachment' : '添加附件')} title={file ? (en ? 'Replace attachment' : '更换附件') : (en ? 'Add attachment' : '添加附件')} disabled={busy} onClick={() => fileInput.current?.click()}>{file ? '↻' : '+'}</button>
        <span className="unified-composer-hint">{file ? (en ? 'Text will be saved as context for this file.' : '文字将作为此附件的补充说明。') : (en ? 'TXT, Markdown, PDF, image or audio · max 20 MiB' : 'TXT、Markdown、PDF、图片或音频 · 单附件最大 20 MiB')}</span>
        <button type="submit" className="unified-send-button" aria-label={en ? 'Send capture' : '发送收录'} disabled={busy || (!file && !value.trim())}>{busy ? <span className="unified-send-spinner" /> : '↑'}</button>
      </footer>}
      {busy && <div role="status" className="unified-busy-status">{en ? 'Saving original…' : '正在保存原件…'}</div>}
    </form>
    {dragOver && <div className="unified-drop-hint" aria-live="polite">{en ? 'Drop one file to attach' : '松开鼠标添加一个附件'}</div>}
  </section>;
}

export const unifiedCaptureFileRules = { accept: ACCEPTED_FILES, maxBytes: MAX_FILE_SIZE };
