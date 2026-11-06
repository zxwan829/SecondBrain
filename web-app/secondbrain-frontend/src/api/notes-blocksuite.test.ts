import { describe, expect, it, vi } from 'vitest';
import { notesApi, type BlockSuiteResource, type BlockSuiteResourceWrite, type Note } from './notes';

const note: Note = { collection: 'drafts', path: '00000000-0000-4000-8000-000000000001', content: '# Test\n', etag: 'a'.repeat(64), artifactSetEtag: 'c'.repeat(64), read_only: false, safety_reasons: [] };
const write: BlockSuiteResourceWrite = {
  schemaVersion: 1, resourceId: '0123456789abcdef0123456789abcdef', resourceKind: 'database',
  docId: '00000000-0000-4000-8000-000000000002', updateB64: 'AQ==', snapshot: { schemaVersion: 1 },
};
const resource: BlockSuiteResource = { ...write, etag: 'b'.repeat(64), note_etag: note.etag, filename: `${write.resourceId}.blocksuite.json` };

describe('Core note-bound BlockSuite resource API contract', () => {
  it('uses note If-Match for create and both resource ETags for update', async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), init });
      const body = calls.length === 1
        ? { resource_id: write.resourceId, resource_kind: write.resourceKind, doc_id: write.docId, filename: resource.filename, reference: `[BlockSuite resource](attachments/${resource.filename})`, etag: resource.etag, note_etag: note.etag }
        : { resource_id: write.resourceId, resource_kind: write.resourceKind, doc_id: write.docId, filename: resource.filename, etag: 'c'.repeat(64), note_etag: note.etag };
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));

    const createBody = { schemaVersion: write.schemaVersion, resourceKind: write.resourceKind, docId: write.docId, updateB64: write.updateB64, snapshot: write.snapshot };
    await notesApi.createBlockSuiteResource(note, createBody);
    await notesApi.saveBlockSuiteResource(note, resource, write);

    expect(calls[0].url).toBe(`/api/notes/drafts/${note.path}/blocksuite/resources`);
    expect(calls[0].init?.method).toBe('POST');
    expect(new Headers(calls[0].init?.headers).get('If-Match')).toBe(`"${note.etag}"`);
    expect(Object.keys(JSON.parse(String(calls[0].init?.body))).sort()).toEqual(['docId', 'resourceKind', 'schemaVersion', 'snapshot', 'updateB64']);
    expect(calls[1].url).toBe(`/api/notes/drafts/${note.path}/blocksuite/resources/${write.resourceId}`);
    expect(calls[1].init?.method).toBe('PUT');
    expect(new Headers(calls[1].init?.headers).get('If-Match')).toBe(`"${note.etag}"`);
    expect(new Headers(calls[1].init?.headers).get('If-Resource-Match')).toBe(`"${resource.etag}"`);
  });

  it('reads a snapshot detail and restores it with both current closure ETags', async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    const detail = { snapshot_id: 'f'.repeat(64), note: { content: '# Prior\n', etag: 'd'.repeat(64) },
      artifact_set_etag: 'e'.repeat(64), artifacts: [] };
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), init });
      return new Response(JSON.stringify(calls.length === 1 ? detail : {
        snapshot_id: detail.snapshot_id, note_etag: note.etag, artifact_set_etag: note.artifactSetEtag, restored: true, duplicate: false,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));
    await notesApi.readBlockSuiteSnapshot(note, detail.snapshot_id);
    await notesApi.restoreBlockSuiteSnapshot(note, detail.snapshot_id);
    expect(calls[0].url).toBe(`/api/notes/drafts/${note.path}/blocksuite/snapshots/${detail.snapshot_id}`);
    expect(calls[1].url).toBe(`${calls[0].url}/restore`);
    expect(calls[1].init?.method).toBe('POST');
    expect(new Headers(calls[1].init?.headers).get('If-Match')).toBe(`"${note.etag}"`);
    expect(new Headers(calls[1].init?.headers).get('If-Artifact-Set-Match')).toBe(`"${note.artifactSetEtag}"`);
  });
});
