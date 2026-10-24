import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NotePropertiesPanel } from './NotePropertiesPanel';

const note = { collection: 'drafts', path: '00000000-0000-4000-8000-000000000001', content: '# Synthetic\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
const catalog = { schema_version: 1, revision: 2,
  types: [{ id: 'type-note', name: '笔记', enabled: true }, { id: 'type-summary', name: '摘要', enabled: true }],
  tags: [{ id: 'tag-core', name: 'SecondBrain', enabled: true }], synonyms: [], audit: [] };

describe('NotePropertiesPanel', () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('loads the Core vocabulary and saves explicit properties with the note ETag', async () => {
    const saved = { ...note, content: '---\n类型: "摘要"\ntags: ["SecondBrain"]\n---\n\n# Synthetic\n', etag: 'b'.repeat(64), read_only: true, safety_reasons: ['frontmatter'] };
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input); calls.push({ url, init });
      if (url.endsWith('/properties') && !init?.method) return new Response(JSON.stringify({ type: '', tags: [], etag: note.etag }), { status: 200 });
      if (url === '/api/vocabulary') return new Response(JSON.stringify(catalog), { status: 200 });
      if (url.endsWith('/properties') && init?.method === 'PUT') return new Response(JSON.stringify(saved), { status: 200 });
      throw new Error(`Unexpected request ${url}`);
    });
    const onSaved = vi.fn();
    render(<NotePropertiesPanel note={note} onSaved={onSaved} />);
    fireEvent.click(screen.getByRole('button', { name: '编辑类型与标签' }));
    await screen.findByRole('combobox', { name: '类型' });
    fireEvent.change(screen.getByRole('combobox', { name: '类型' }), { target: { value: '摘要' } });
    fireEvent.click(screen.getByLabelText('SecondBrain'));
    fireEvent.click(screen.getByRole('button', { name: '确认保存属性' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved));
    const put = calls.find((call) => call.init?.method === 'PUT');
    expect(put?.url).toBe(`/api/notes/drafts/${note.path}/properties`);
    expect(new Headers(put?.init?.headers).get('If-Match')).toBe(`"${note.etag}"`);
    expect(JSON.parse(String(put?.init?.body))).toEqual({ type: '摘要', tags: ['SecondBrain'], confirmed: true });
  });

  it('does not write when a note property format is unsupported', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (String(input).endsWith('/properties')) return new Response(JSON.stringify({ detail: 'Managed tags are unsupported' }), { status: 422 });
      if (String(input) === '/api/vocabulary') return new Response(JSON.stringify(catalog), { status: 200 });
      throw new Error('Unexpected vocabulary request');
    });
    render(<NotePropertiesPanel note={note} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '编辑类型与标签' }));
    expect((await screen.findByRole('alert')).textContent).toContain('Managed tags are unsupported');
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });

  it('shows an inactive existing tag so the user can retain or remove it explicitly', async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input); calls.push({ url, init });
      if (url.endsWith('/properties') && !init?.method) return new Response(JSON.stringify({ type: '旧类型', tags: ['CRM'], etag: note.etag }), { status: 200 });
      if (url === '/api/vocabulary') return new Response(JSON.stringify(catalog), { status: 200 });
      if (url.endsWith('/properties') && init?.method === 'PUT') return new Response(JSON.stringify(note), { status: 200 });
      throw new Error(`Unexpected request ${url}`);
    });
    render(<NotePropertiesPanel note={note} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '编辑类型与标签' }));
    const oldTag = await screen.findByLabelText('CRM（已停用或未入库，可移除）');
    expect((oldTag as HTMLInputElement).checked).toBe(true);
    fireEvent.click(oldTag);
    fireEvent.change(screen.getByRole('combobox', { name: '类型' }), { target: { value: '笔记' } });
    fireEvent.click(screen.getByRole('button', { name: '确认保存属性' }));
    await waitFor(() => expect(calls.some((call) => call.init?.method === 'PUT')).toBe(true));
    const put = calls.find((call) => call.init?.method === 'PUT');
    expect(JSON.parse(String(put?.init?.body))).toEqual({ type: '笔记', tags: [], confirmed: true });
  });
});
