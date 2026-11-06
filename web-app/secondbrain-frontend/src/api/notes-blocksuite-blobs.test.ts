import { describe, expect, it, vi } from 'vitest';
import { sha } from '@blocksuite/global/utils';
import { NoteBoundBlockSuiteBlobSource } from './notes-blocksuite-blobs';
import type { Note } from './notes';

const note: Note = {
  collection: 'drafts', path: 'folder/note.md', content: '# Image resource\n',
  etag: 'a'.repeat(64), artifactSetEtag: 'c'.repeat(64), read_only: false, safety_reasons: [],
};
const nextSet = 'd'.repeat(64);
const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x01, 0x02, 0x03]);

async function digest(bytes: Uint8Array) {
  const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  const hex = [...hash].map((byte) => byte.toString(16).padStart(2, '0')).join('');
  let binary = '';
  for (const byte of hash) binary += String.fromCharCode(byte);
  return { hex, key: btoa(binary).replace(/\+/g, '-').replace(/\//g, '_') };
}

describe('note-scoped BlockSuite BlobSource', () => {
  it('uploads immutable binary bytes with the canonical padded BlockSuite key and note ETag', async () => {
    const { hex, key } = await digest(png);
    expect(key).toMatch(/^[A-Za-z0-9_-]{43}=$/);
    expect(key).toBe(await sha(png.slice().buffer as ArrayBuffer));
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify({ blob_id: key, etag: hex, size_bytes: png.byteLength, content_type: 'image/png', note_etag: note.etag, artifact_set_etag: nextSet }), { status: 201, headers: { ETag: `"${hex}"`, 'X-Note-ETag': `"${note.etag}"`, 'X-Artifact-Set-ETag': `"${nextSet}"` } }));
    const changed = vi.fn();
    const source = new NoteBoundBlockSuiteBlobSource(() => note, fetcher as typeof fetch, changed);

    await expect(source.set(key, new Blob([png], { type: 'image/png' }))).resolves.toBe(key);
    expect(fetcher.mock.contexts[0]).toBe(globalThis);
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(`/api/notes/drafts/folder/note.md/blocksuite/blobs/${encodeURIComponent(key)}`);
    expect(init.method).toBe('PUT');
    expect(new Headers(init.headers).get('Content-Type')).toBe('image/png');
    expect(new Headers(init.headers).get('If-Match')).toBe(`"${note.etag}"`);
    expect(new Headers(init.headers).get('If-Artifact-Set-Match')).toBe(`"${note.artifactSetEtag}"`);
    expect(source.artifactSetEtag).toBe(nextSet);
    expect(changed).toHaveBeenCalledWith(nextSet);
    expect(init.body).toBeInstanceOf(Blob);
  });

  it('reads a Blob only when content hash, canonical key, and note ETag all agree', async () => {
    const { hex, key } = await digest(png);
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(png, { status: 200, headers: {
      ETag: `"${hex}"`, 'X-Note-ETag': `"${note.etag}"`, 'X-Artifact-Set-ETag': `"${note.artifactSetEtag}"`, 'Content-Type': 'image/png',
    } }));
    const source = new NoteBoundBlockSuiteBlobSource(() => note, fetcher as typeof fetch);

    const loaded = await source.get(key);
    expect(fetcher.mock.contexts[0]).toBe(globalThis);
    expect(loaded?.type).toBe('image/png');
    expect([...new Uint8Array(await loaded!.arrayBuffer())]).toEqual([...png]);
    expect(fetcher.mock.calls[0]?.[1]).toMatchObject({ credentials: 'same-origin', cache: 'no-store' });
  });

  it('rejects changed note versions, unsupported data, and mismatched keys without writing', async () => {
    const { key } = await digest(png);
    const fetcher = vi.fn(async () => new Response(null, { status: 204 }));
    const source = new NoteBoundBlockSuiteBlobSource(() => note, fetcher as typeof fetch);
    await expect(source.set(`${key.slice(0, -1)}A`, new Blob([png], { type: 'image/png' }))).rejects.toThrow(/key/);
    await expect(source.set(key, new Blob(['<svg/>'], { type: 'image/svg+xml' }))).rejects.toThrow(/SVG/);
    expect(fetcher).not.toHaveBeenCalled();

    const staleSource = new NoteBoundBlockSuiteBlobSource(() => note, vi.fn(async () => new Response(png, {
      status: 200, headers: { ETag: `"${(await digest(png)).hex}"`, 'X-Note-ETag': `"${'c'.repeat(64)}"`, 'Content-Type': 'image/png' },
    })) as typeof fetch);
    await expect(staleSource.get(key)).rejects.toMatchObject({ status: 412 });
  });

  it('does not claim to enumerate or delete immutable Core blobs', async () => {
    const source = new NoteBoundBlockSuiteBlobSource(() => note, vi.fn() as typeof fetch);
    await expect(source.list()).rejects.toThrow(/列举/);
    await expect(source.delete('unused')).rejects.toThrow(/不可变/);
  });
});
