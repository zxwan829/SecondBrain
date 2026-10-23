import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { VocabularyPage } from './VocabularyPage';

const initial = { schema_version: 1, revision: 0, types: [
  { id: 'builtin-1', name: '日记', enabled: true, built_in: true },
  { id: 'builtin-2', name: '笔记', enabled: true, built_in: true },
  { id: 'builtin-3', name: '头脑风暴', enabled: true, built_in: true },
  { id: 'builtin-4', name: '摘要', enabled: true, built_in: true },
  { id: 'builtin-5', name: '会议纪要', enabled: true, built_in: true },
], tags: [], synonyms: [], audit: [] };

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function json(value: unknown, status = 200, etag?: string) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json', ...(etag ? { ETag: etag } : {}) } });
}

describe('VocabularyPage', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) =>
    String(input) === '/api/vocabulary' ? json(initial, 200, '"0"') : json({ detail: 'unexpected request' }, 404))));

  it('shows Core-owned initial types, keeps initial tags empty, and confirms new terms explicitly', async () => {
    const request = vi.mocked(fetch);
    render(<VocabularyPage locale="zh-CN" />);
    expect(await screen.findByText('会议纪要 · 初始类型')).toBeTruthy();
    expect(screen.getByText('尚无已盘点标签；真实 Vault 只读盘点需另行授权。')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('新增类型'), { target: { value: '访谈' } });
    const submit = screen.getByRole('button', { name: '确认新增类型' }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText('我确认将此类型加入 Core 词库。'));
    expect(submit.disabled).toBe(false);
    let revision = 1;
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === '/api/vocabulary/types') {
        expect(init?.headers).toMatchObject({ 'If-Match': '"0"' });
        expect(JSON.parse(String(init?.body))).toMatchObject({ name: '访谈', confirmed: true });
        return json({ ...initial, revision, types: [...initial.types, { id: 'type-6', name: '访谈', enabled: true, built_in: false }], audit: [{ revision, operation: 'type.add', actor: 'owner', target: { kind: 'type', id: 'type-6', name: '访谈' }, at: '2026-10-17T00:00:00Z' }] }, 200, '"1"');
      }
      return json(initial, 200, '"0"');
    });
    fireEvent.click(submit);
    expect(await screen.findByText('已保存至 Core 词库并记录审计版本。')).toBeTruthy();
    expect(screen.getByText('访谈')).toBeTruthy();
    expect(request).toBeTruthy();
  });

  it('uses optimistic revisions and reloads after a stale write', async () => {
    const request = vi.mocked(fetch);
    let reads = 0;
    request.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input) === '/api/vocabulary') {
        reads += 1;
        return json({ ...initial, revision: reads > 1 ? 4 : 3 }, 200, reads > 1 ? '"4"' : '"3"');
      }
      return json({ detail: 'Vocabulary revision changed; reload before retrying' }, 412);
    });
    render(<VocabularyPage locale="zh-CN" />);
    await screen.findByText('版本 3 · 类型 5/10');
    fireEvent.change(screen.getByLabelText('新增标签'), { target: { value: 'CRM' } });
    fireEvent.click(screen.getByLabelText('我确认将此标签加入 Core 词库。'));
    fireEvent.click(screen.getByRole('button', { name: '确认新增标签' }));
    expect(await screen.findByText(/词库已被其他操作更新/)).toBeTruthy();
    await waitFor(() => expect(screen.getByText('版本 4 · 类型 5/10')).toBeTruthy());
    expect(request.mock.calls.filter(([url]) => String(url) === '/api/vocabulary')).toHaveLength(2);
  });

  it('offers a retry after the initial vocabulary read fails', async () => {
    const request = vi.mocked(fetch);
    let reads = 0;
    request.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input) !== '/api/vocabulary') return json({ detail: 'unexpected request' }, 404);
      reads += 1;
      if (reads === 1) throw new Error('temporary read failure');
      return json(initial);
    });

    render(<VocabularyPage locale="zh-CN" />);
    expect((await screen.findByRole('alert')).textContent).toContain('temporary read failure');
    fireEvent.click(screen.getByRole('button', { name: '重试读取词库' }));
    expect(await screen.findByText('版本 0 · 类型 5/10')).toBeTruthy();
    expect(reads).toBe(2);
  });

  it('does not claim a stale-write refresh succeeded when that read fails, and retries safely', async () => {
    const request = vi.mocked(fetch);
    let reads = 0;
    request.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input) === '/api/vocabulary') {
        reads += 1;
        if (reads === 1) return json({ ...initial, revision: 3 });
        if (reads === 2) throw new Error('temporary refresh failure');
        return json({ ...initial, revision: 4 });
      }
      return json({ detail: 'Vocabulary revision changed' }, 412);
    });

    render(<VocabularyPage locale="zh-CN" />);
    await screen.findByText('版本 3 · 类型 5/10');
    fireEvent.change(screen.getByLabelText('新增标签'), { target: { value: 'CRM' } });
    fireEvent.click(screen.getByLabelText('我确认将此标签加入 Core 词库。'));
    fireEvent.click(screen.getByRole('button', { name: '确认新增标签' }));

    expect((await screen.findByRole('alert')).textContent).toContain('词库版本已变化，但最新版本读取失败');
    expect(screen.queryByRole('button', { name: '确认新增标签' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '重试读取词库' }));
    expect(await screen.findByText('版本 4 · 类型 5/10')).toBeTruthy();
    expect(reads).toBe(3);
  });

  it('confirms tag deactivation and leaves the term visible as disabled', async () => {
    const request = vi.mocked(fetch);
    const withTag = { ...initial, revision: 1, tags: [{ id: 'tag-1', name: 'CRM', enabled: true }] };
    request.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === '/api/vocabulary') return json(withTag);
      if (String(input) === '/api/vocabulary/tags/tag-1') {
        expect(init?.method).toBe('PATCH');
        expect(JSON.parse(String(init?.body))).toMatchObject({ enabled: false, confirmed: true });
        return json({ ...withTag, revision: 2, tags: [{ id: 'tag-1', name: 'CRM', enabled: false }] });
      }
      return json({ detail: 'unexpected request' }, 404);
    });
    vi.stubGlobal('confirm', vi.fn(() => true));
    render(<VocabularyPage locale="zh-CN" />);
    await waitFor(() => expect(screen.getAllByText('CRM').length).toBeGreaterThan(0));
    fireEvent.click(within(screen.getByRole('region', { name: '标签' })).getByRole('button', { name: '停用' }));
    expect(await screen.findByText('CRM · 已停用')).toBeTruthy();
    expect(confirm).toHaveBeenCalledWith('确认停用“CRM”？历史笔记中的引用会保留。');
  });

  it('requires explicit confirmation and saves a manual alias to an active canonical tag', async () => {
    const tagged = { ...initial, revision: 4, tags: [{ id: 'tag-crm', name: 'CRM', enabled: true }] };
    const request = vi.mocked(fetch);
    request.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === '/api/vocabulary') return json(tagged, 200, '"4"');
      if (String(input) === '/api/vocabulary/synonyms') {
        expect(init?.method).toBe('POST');
        expect(init?.headers).toMatchObject({ 'If-Match': '"4"' });
        expect(JSON.parse(String(init?.body))).toEqual({ alias: '客户关系', tag_id: 'tag-crm', confirmed: true });
        return json({ ...tagged, revision: 5, synonyms: [{ id: 'syn-1', alias: '客户关系', tag_id: 'tag-crm', enabled: true }] }, 200, '"5"');
      }
      return json({ detail: 'unexpected request' }, 404);
    });

    render(<VocabularyPage locale="zh-CN" />);
    await screen.findByText('版本 4 · 类型 5/10');
    const synonyms = screen.getByRole('region', { name: '同义词' });
    fireEvent.change(within(synonyms).getByLabelText('同义词'), { target: { value: '客户关系' } });
    fireEvent.change(within(synonyms).getByLabelText('规范标签'), { target: { value: 'tag-crm' } });
    const submit = within(synonyms).getByRole('button', { name: '确认映射' }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    fireEvent.click(within(synonyms).getByLabelText('我确认保存此持久映射。'));
    expect(submit.disabled).toBe(false);
    fireEvent.click(submit);

    expect(await screen.findByText('已保存至 Core 词库并记录审计版本。')).toBeTruthy();
    expect(within(synonyms).getByText('客户关系 → CRM')).toBeTruthy();
  });
});
