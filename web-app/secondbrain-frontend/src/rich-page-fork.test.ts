import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sha } from '@blocksuite/global/utils';
import { forkRichPageNote } from './rich-page-fork';
import { markdownSha256 } from './rich-page-projection';
import { notesApi } from './api/notes';
import { NoteBoundBlockSuiteBlobSource } from './api/notes-blocksuite-blobs';
import * as Y from 'yjs';

vi.mock('./api/notes', () => ({ notesApi: {
  readWithArtifactSet: vi.fn(), readBlockSuiteResource: vi.fn(), create: vi.fn(),
  createBlockSuiteResource: vi.fn(), saveBlockSuiteResource: vi.fn(), save: vi.fn(),
} }));

describe('forkRichPageNote', () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.unstubAllGlobals());

  const encodedYjsText = (key: string, value: string) => {
    const doc = new Y.Doc();
    doc.getMap('wp5-synthetic').set(key, value);
    const bytes = Y.encodeStateAsUpdate(doc);
    doc.destroy();
    let binary = ''; for (const byte of bytes) binary += String.fromCharCode(byte);
    return btoa(binary);
  };
  const readYjsText = (updateB64: string, key: string) => {
    const doc = new Y.Doc();
    Y.applyUpdate(doc, Uint8Array.from(atob(updateB64), value => value.charCodeAt(0)));
    const value = doc.getMap('wp5-synthetic').get(key);
    doc.destroy();
    return value;
  };

  it('rejects a local image without a verified Blob copy before creating any Draft', async () => {
    const source = { collection: 'drafts', path: 'source-note', content: '# Synthetic\n',
      etag: 'source-etag', artifactSetEtag: 'source-set', read_only: false, safety_reasons: [] };
    const blobKey = `A${'B'.repeat(42)}=`;
    vi.mocked(notesApi.readWithArtifactSet).mockResolvedValue(source as any);
    const payload = { schemaVersion: 1 as const, resourceId: 'a'.repeat(32), resourceKind: 'rich-page' as const,
      docId: 'root-doc', updateB64: encodedYjsText('body', 'synthetic'),
      snapshot: { blocks: { children: [{ props: { sourceId: blobKey } }] } } };
    await expect(forkRichPageNote(source as any, payload, new Map())).rejects.toThrow('完整图片副本尚未就绪；未创建新笔记');
    expect(notesApi.create).not.toHaveBeenCalled();
  });

  it('copies a pinned Page, nested Canvas, Yjs JSON and Blob while preserving literal source links', async () => {
    const rootId = 'a'.repeat(32);
    const canvasId = 'b'.repeat(32);
    const copiedRootId = 'c'.repeat(32);
    const copiedCanvasId = 'd'.repeat(32);
    const blobBytes = Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3, 4]);
    const blobKey = await sha(blobBytes.slice().buffer as ArrayBuffer);
    const blobHex = Array.from(atob(blobKey.replace(/-/g, '+').replace(/_/g, '/')),
      value => value.charCodeAt(0).toString(16).padStart(2, '0')).join('');
    const source = { collection: 'drafts', path: 'source-note', content:
      `# Remote winner\n\n[笔记数据](attachments/${rootId}.blocksuite.json)\n`,
    etag: 'remote-note-etag', artifactSetEtag: 'source-set', read_only: false, safety_reasons: [] };
    const sourceNote = { ...source, etag: 'stale-local-note-etag' };
    const rootUpdate = encodedYjsText('rootBody', 'synthetic root Yjs state');
    const canvasUpdate = encodedYjsText('canvasBody', 'synthetic canvas Yjs state');
    const rootSnapshot = { blocks: { children: [
      { props: { type: 'h1', text: { delta: [{ insert: 'Fork title' }] } } },
      { props: { resourceId: canvasId, title: 'Synthetic canvas' } },
    ] } };
    const canvasSnapshot = { shapes: [{ props: { sourceId: blobKey, type: 'image' } }] };
    const persisted = new Map<string, any>();
    const resourceEtag = new Map<string, string>();
    let destinationNote: any;
    let artifactSet = 'empty-destination-set';
    let resourceSequence = 0;
    let writeSequence = 0;

    vi.mocked(notesApi.readWithArtifactSet).mockResolvedValue(source as any);
    vi.mocked(notesApi.readBlockSuiteResource).mockImplementation(async (note, id) => {
      if (note.path === 'source-note' && id === canvasId) return {
        schemaVersion: 1, resourceId: canvasId, resourceKind: 'edgeless-canvas', docId: 'canvas-doc',
        updateB64: canvasUpdate, snapshot: canvasSnapshot, etag: 'source-canvas-etag',
        note_etag: source.etag, artifact_set_etag: source.artifactSetEtag,
      } as any;
      if (note.path === 'fork-note' && persisted.has(id)) return {
        ...persisted.get(id), etag: resourceEtag.get(id), note_etag: destinationNote.etag,
        artifact_set_etag: artifactSet,
      };
      throw new Error(`Unexpected synthetic resource read: ${note.path}/${id}`);
    });
    vi.mocked(notesApi.create).mockImplementation(async content => {
      destinationNote = { collection: 'drafts', path: 'fork-note', content, etag: 'empty-note-etag',
        artifactSetEtag: artifactSet, read_only: false, safety_reasons: [] };
      return destinationNote;
    });
    vi.mocked(notesApi.createBlockSuiteResource).mockImplementation(async (_note, body) => {
      const resource_id = resourceSequence++ === 0 ? copiedRootId : copiedCanvasId;
      persisted.set(resource_id, { ...body, resourceId: resource_id });
      resourceEtag.set(resource_id, `created-${resource_id}`);
      artifactSet = `created-set-${resource_id}`;
      return { resource_id, resource_kind: body.resourceKind, doc_id: body.docId,
        filename: `${resource_id}.blocksuite.json`, reference: '', etag: resourceEtag.get(resource_id)!,
        note_etag: destinationNote.etag, artifact_set_etag: artifactSet };
    });
    vi.mocked(notesApi.saveBlockSuiteResource).mockImplementation(async (_note, resource, body) => {
      persisted.set(resource.resourceId, { ...body, resourceId: resource.resourceId });
      resourceEtag.set(resource.resourceId, `saved-${++writeSequence}-${resource.resourceId}`);
      artifactSet = `saved-set-${writeSequence}`;
      return { resource_id: resource.resourceId, resource_kind: body.resourceKind, doc_id: body.docId,
        filename: `${resource.resourceId}.blocksuite.json`, etag: resourceEtag.get(resource.resourceId)!,
        note_etag: destinationNote.etag, artifact_set_etag: artifactSet };
    });
    vi.mocked(notesApi.save).mockImplementation(async (_note, content) => {
      const etag = await markdownSha256(content);
      destinationNote = { ...destinationNote, content, etag, artifactSetEtag: artifactSet };
      return destinationNote;
    });

    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const requestUrl = new URL(String(input), 'https://secondbrain.test');
      if (init?.method === 'PUT') {
        artifactSet = 'destination-set-with-blob';
        return new Response(JSON.stringify({ blob_id: blobKey, etag: blobHex, size_bytes: blobBytes.byteLength,
          content_type: 'image/png', note_etag: destinationNote.etag, artifact_set_etag: artifactSet }), {
          status: 201, headers: { ETag: `"${blobHex}"`, 'X-Note-ETag': `"${destinationNote.etag}"`,
            'X-Artifact-Set-ETag': `"${artifactSet}"` },
        });
      }
      if (requestUrl.pathname.endsWith(`/source-note/blocksuite/blobs/${encodeURIComponent(blobKey)}`)) {
        return new Response(blobBytes, { status: 200, headers: { ETag: `"${blobHex}"`,
          'X-Note-ETag': `"${source.etag}"`, 'X-Artifact-Set-ETag': `"${source.artifactSetEtag}"`,
          'Content-Type': 'image/png' } });
      }
      if (requestUrl.pathname.endsWith(`/fork-note/blocksuite/blobs/${encodeURIComponent(blobKey)}`)) {
        return new Response(blobBytes, { status: 200, headers: { ETag: `"${blobHex}"`,
          'X-Note-ETag': `"${destinationNote.etag}"`, 'X-Artifact-Set-ETag': `"${artifactSet}"`,
          'Content-Type': 'image/png' } });
      }
      throw new Error(`Unexpected synthetic Blob request: ${requestUrl.pathname}`);
    });
    vi.stubGlobal('fetch', fetcher);

    const remap = (payload: any, mapping: Map<string, string>) => {
      const visit = (value: any): any => {
        if (Array.isArray(value)) return value.map(visit);
        if (!value || typeof value !== 'object') return value;
        return Object.fromEntries(Object.entries(value).map(([key, child]) => [key,
          key === 'resourceId' && typeof child === 'string' ? mapping.get(child) ?? child : visit(child)]));
      };
      return { ...payload, snapshot: visit(payload.snapshot) };
    };
    const payload = { schemaVersion: 1 as const, resourceId: rootId, resourceKind: 'rich-page' as const,
      docId: 'root-doc', updateB64: rootUpdate, snapshot: rootSnapshot };
    const { note, resource } = await forkRichPageNote(sourceNote as any, payload, new Map(), remap);

    expect(notesApi.create).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls.some(([url, init]) => init?.method === 'PUT' && String(url).includes(encodeURIComponent(blobKey)))).toBe(true);
    expect(resource.resourceId).toBe(copiedRootId);
    expect(resource.resourceKind).toBe('rich-page');
    expect(resource.updateB64).toBe(rootUpdate);
    expect(readYjsText(resource.updateB64, 'rootBody')).toBe('synthetic root Yjs state');
    expect((resource.snapshot as any).blocks.children[1].props.resourceId).toBe(copiedCanvasId);
    expect(note.content).toContain(`[笔记数据](attachments/${copiedRootId}.blocksuite.json)`);
    expect(note.content).toContain(`[画布数据](attachments/${copiedCanvasId}.blocksuite.json)`);
    expect(note.content).toContain(source.content);
    const projectedPrefix = note.content.split('\n## 冲突时的外部 Markdown 原文\n', 1)[0];
    expect(projectedPrefix).not.toContain(`[笔记数据](attachments/${rootId}.blocksuite.json)`);
    expect(persisted.get(copiedCanvasId).updateB64).toBe(canvasUpdate);
    expect(readYjsText(persisted.get(copiedCanvasId).updateB64, 'canvasBody')).toBe('synthetic canvas Yjs state');
    expect(persisted.get(copiedCanvasId).snapshot.shapes[0].props.sourceId).toBe(blobKey);
    expect(note.etag).toBe((resource.snapshot as any).secondbrainRichPage.markdownSha256);

    const reopenedCanvas = await notesApi.readBlockSuiteResource(note as any, copiedCanvasId);
    expect(reopenedCanvas.updateB64).toBe(canvasUpdate);
    const reopenedBlob = await new NoteBoundBlockSuiteBlobSource(() => note as any, fetcher as any).get(blobKey);
    expect(reopenedBlob).not.toBeNull();
    expect(new Uint8Array(await reopenedBlob!.arrayBuffer())).toEqual(blobBytes);
    const originalBlob = await new NoteBoundBlockSuiteBlobSource(() => source as any, fetcher as any).get(blobKey);
    expect(originalBlob).not.toBeNull();
    expect(new Uint8Array(await originalBlob!.arrayBuffer())).toEqual(blobBytes);
    expect(fetcher).toHaveBeenCalledTimes(4);
    expect(source.content).toContain(`[笔记数据](attachments/${rootId}.blocksuite.json)`);
    expect(source.etag).toBe('remote-note-etag');
  });
});
