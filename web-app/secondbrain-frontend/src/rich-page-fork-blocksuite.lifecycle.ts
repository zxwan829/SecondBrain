import { describe, expect, it, vi } from 'vitest';
import { forkRichPageNote } from './rich-page-fork';
import { markdownSha256 } from './rich-page-projection';
import { notesApi } from './api/notes';
import { createBlockSuiteResourcePayload, restoreBlockSuiteResourceSnapshot } from './BlockSuiteResourceEditor';
import { TransientMarkdownWorkspace } from './transient-blocksuite-workspace';
import { archiveManagers } from './archive-rich-page-runtime';
import { CANVAS_REF_FLAVOUR } from './canvas-ref-block';
import { nativeResourceBase64, nativeResourceSnapshot, remapNativeResourceReferences } from './native-resource-state';
import { MemoryBlobSource } from '@blocksuite/sync';
import { sha } from '@blocksuite/global/utils';
import { writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import * as Y from 'yjs';

vi.mock('./api/notes', () => ({ notesApi: {
  readWithArtifactSet: vi.fn(), readBlockSuiteResource: vi.fn(), create: vi.fn(),
  createBlockSuiteResource: vi.fn(), saveBlockSuiteResource: vi.fn(), save: vi.fn(), trash: vi.fn(),
} }));

describe('real BlockSuite 412 recovery fork', () => {
  it('exports a verified synthetic PNG, native Page Yjs, and Canvas fixture for production API setup', async () => {
    const blobSource = new MemoryBlobSource();
    const workspace = new TransientMarkdownWorkspace(blobSource);
    try {
      workspace.storeExtensions = archiveManagers().stores.get('store');
      workspace.meta.initialize();
      const pageWrite = createBlockSuiteResourcePayload('rich-page');
      const pageDoc = workspace.createDoc(pageWrite.docId);
      Y.applyUpdate(pageDoc.spaceDoc, Uint8Array.from(atob(pageWrite.updateB64), char => char.charCodeAt(0)));
      pageDoc.load();
      const store = pageDoc.getStore();
      const surface = store.getBlocksByFlavour('affine:surface')[0]?.model;
      if (!surface) throw new Error('Fixture Page surface is missing');
      const pngBytes = Uint8Array.from(Buffer.from(
        // Keep every PNG chunk checksum valid; BlockSuite's in-memory BlobSource
        // did not validate the IDAT CRC in the previous fixture.
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=', 'base64'));
      const blob = new Blob([pngBytes], { type: 'image/png' });
      const sourceId = await store.blobSync.set(blob);
      store.addBlock('affine:image', { sourceId, width: 1, height: 1, size: pngBytes.byteLength, rotate: 0, xywh: '[0,0,1,1]' }, surface.id);
      const page = { schemaVersion: 1 as const, resourceKind: 'rich-page' as const, docId: pageWrite.docId,
        updateB64: nativeResourceBase64(Y.encodeStateAsUpdate(pageDoc.spaceDoc)), snapshot: nativeResourceSnapshot(store) };
      const restoredPage = restoreBlockSuiteResourceSnapshot(page);
      expect(JSON.stringify(page.snapshot)).toContain(sourceId);
      expect(JSON.stringify(restoredPage)).toContain(sourceId);
      const persistedBlob = await blobSource.get(sourceId);
      expect(persistedBlob).not.toBeNull();
      const persistedBytes = new Uint8Array(await persistedBlob!.arrayBuffer());
      expect(persistedBytes).toEqual(pngBytes);
      expect(await sha(persistedBytes.slice().buffer as ArrayBuffer)).toBe(sourceId);

      const canvasWrite = createBlockSuiteResourcePayload('edgeless-canvas');
      const restoredCanvas = restoreBlockSuiteResourceSnapshot({ ...canvasWrite, resourceKind: 'edgeless-canvas' } as any);
      expect(JSON.stringify(restoredCanvas)).toContain('可编辑测试画布');
      expect(JSON.stringify(restoredCanvas)).toContain('独立 Edgeless 便签');
      const output = { schemaVersion: 1, fixtureType: 'wp5-rich-page-blob', page, sourceId,
        png: { contentType: 'image/png', sizeBytes: persistedBytes.byteLength,
          sha256: createHash('sha256').update(persistedBytes).digest('hex'), base64: Buffer.from(persistedBytes).toString('base64') },
        canvas: { schemaVersion: 1, resourceKind: canvasWrite.resourceKind, docId: canvasWrite.docId,
          updateB64: canvasWrite.updateB64, snapshot: canvasWrite.snapshot } };
      const fixturePath = process.env.SB_WP5_BLOB_FIXTURE_PATH;
      if (!fixturePath) throw new Error('SB_WP5_BLOB_FIXTURE_PATH is required to export the synthetic fixture');
      await writeFile(fixturePath, JSON.stringify(output));
    } finally { workspace.dispose(); }
  });

  it('round trips real BlockSuite Yjs resources and rebinds the embedded Canvas preview', async () => {
    const sourceRootId = 'e'.repeat(32);
    const sourceCanvasId = 'f'.repeat(32);
    const copiedRootId = '1'.repeat(32);
    const copiedCanvasId = '2'.repeat(32);
    const source = { collection: 'drafts', path: 'real-source', content: '# Remote winner\n',
      etag: 'remote-note-etag', artifactSetEtag: 'source-set', read_only: false, safety_reasons: [] };
    const sourceNote = { ...source, etag: 'stale-local-etag' };
    const canvasWrite = createBlockSuiteResourcePayload('edgeless-canvas');
    const restoredSourceCanvas = restoreBlockSuiteResourceSnapshot({ ...canvasWrite,
      resourceKind: 'edgeless-canvas' } as any);
    expect(JSON.stringify(restoredSourceCanvas)).toContain('可编辑测试画布');
    expect(JSON.stringify(restoredSourceCanvas)).toContain('独立 Edgeless 便签');
    const sourceCanvas = { ...canvasWrite, resourceId: sourceCanvasId,
      etag: 'source-canvas-etag', note_etag: source.etag, artifact_set_etag: source.artifactSetEtag,
      filename: `${sourceCanvasId}.blocksuite.json` };

    const pageWrite = createBlockSuiteResourcePayload('rich-page');
    const workspace = new TransientMarkdownWorkspace();
    workspace.storeExtensions = archiveManagers().stores.get('store');
    workspace.meta.initialize();
    const pageDoc = workspace.createDoc(pageWrite.docId);
    Y.applyUpdate(pageDoc.spaceDoc, Uint8Array.from(atob(pageWrite.updateB64), char => char.charCodeAt(0)));
    pageDoc.load();
    const pageStore = pageDoc.getStore();
    const parent = pageStore.getBlocksByFlavour('affine:note')[0]?.model;
    expect(parent).toBeTruthy();
    const previewJson = JSON.stringify([{ id: 'synthetic-shape', type: 'shape', shapeType: 'rect', bound: [80, 100, 260, 150], text: '可编辑测试画布' }]);
    pageStore.addBlock(CANVAS_REF_FLAVOUR, { resourceId: sourceCanvasId, docId: canvasWrite.docId,
      title: 'Synthetic canvas', state: 'ready', revision: 'source-canvas-etag', previewJson,
      error: '', previewWidth: 0, previewHeight: 220 }, parent!.id);
    const sourceRoot = { schemaVersion: 1 as const, resourceId: sourceRootId, resourceKind: 'rich-page' as const,
      docId: pageWrite.docId, updateB64: nativeResourceBase64(Y.encodeStateAsUpdate(pageDoc.spaceDoc)),
      snapshot: nativeResourceSnapshot(pageStore) };
    workspace.dispose();

    let destinationNote: any;
    let artifactSet = 'empty-destination-set';
    let resourceSequence = 0;
    let writeSequence = 0;
    const resources = new Map<string, any>();
    const resourceEtags = new Map<string, string>();
    vi.mocked(notesApi.readWithArtifactSet).mockImplementation(async (_collection, path) => path === source.path
      ? source as any : { ...destinationNote, artifactSetEtag: artifactSet } as any);
    vi.mocked(notesApi.readBlockSuiteResource).mockImplementation(async (note, id) => {
      if (note.path === source.path && id === sourceCanvasId) return sourceCanvas as any;
      if (note.path === 'real-fork' && resources.has(id)) return { ...resources.get(id), etag: resourceEtags.get(id),
        note_etag: destinationNote.etag, artifact_set_etag: artifactSet, filename: `${id}.blocksuite.json` } as any;
      throw new Error(`Unexpected real BlockSuite resource read: ${note.path}/${id}`);
    });
    vi.mocked(notesApi.create).mockImplementation(async content => {
      destinationNote = { collection: 'drafts', path: 'real-fork', content, etag: 'empty-note-etag',
        artifactSetEtag: artifactSet, read_only: false, safety_reasons: [] };
      return destinationNote;
    });
    vi.mocked(notesApi.createBlockSuiteResource).mockImplementation(async (_note, body) => {
      const resource_id = resourceSequence++ === 0 ? copiedRootId : copiedCanvasId;
      resources.set(resource_id, { ...body, resourceId: resource_id });
      resourceEtags.set(resource_id, `created-${resource_id}`);
      artifactSet = `created-set-${resource_id}`;
      return { resource_id, resource_kind: body.resourceKind, doc_id: body.docId,
        filename: `${resource_id}.blocksuite.json`, reference: '', etag: resourceEtags.get(resource_id)!,
        note_etag: destinationNote.etag, artifact_set_etag: artifactSet };
    });
    vi.mocked(notesApi.saveBlockSuiteResource).mockImplementation(async (_note, resource, body) => {
      resources.set(resource.resourceId, { ...body, resourceId: resource.resourceId });
      resourceEtags.set(resource.resourceId, `saved-${++writeSequence}-${resource.resourceId}`);
      artifactSet = `saved-set-${writeSequence}`;
      return { resource_id: resource.resourceId, resource_kind: body.resourceKind, doc_id: body.docId,
        filename: `${resource.resourceId}.blocksuite.json`, etag: resourceEtags.get(resource.resourceId)!,
        note_etag: destinationNote.etag, artifact_set_etag: artifactSet };
    });
    vi.mocked(notesApi.save).mockImplementation(async (_note, content) => {
      destinationNote = { ...destinationNote, content, etag: await markdownSha256(content), artifactSetEtag: artifactSet };
      return destinationNote;
    });

    const { note, resource } = await forkRichPageNote(sourceNote as any, sourceRoot, new Map(), remapNativeResourceReferences);
    expect(resource.docId).not.toBe(sourceRoot.docId);
    const copiedRoot = await notesApi.readBlockSuiteResource(note as any, copiedRootId);
    const reopenedRoot = restoreBlockSuiteResourceSnapshot(copiedRoot);
    const findCanvasRef = (value: any): any => {
      if (!value || typeof value !== 'object') return null;
      if (value.props?.resourceId) return value;
      if (Array.isArray(value)) return value.map(findCanvasRef).find(Boolean) ?? null;
      for (const child of Object.values(value)) { const found = findCanvasRef(child); if (found) return found; }
      return null;
    };
    const ref = findCanvasRef(reopenedRoot);
    expect(ref.props.resourceId).toBe(copiedCanvasId);
    expect(ref.props.docId).toBe(resources.get(copiedCanvasId).docId);
    expect(ref.props.revision).toBe(resourceEtags.get(copiedCanvasId));
    expect(ref.props.previewJson).toBe(previewJson);

    const copiedCanvas = await notesApi.readBlockSuiteResource(note as any, copiedCanvasId);
    const reopenedCanvas = restoreBlockSuiteResourceSnapshot(copiedCanvas);
    expect(JSON.stringify(reopenedCanvas)).toContain('可编辑测试画布');
    expect(JSON.stringify(reopenedCanvas)).toContain('独立 Edgeless 便签');
    expect(copiedCanvas.updateB64).toBe(canvasWrite.updateB64);
    expect(source.etag).toBe('remote-note-etag');
    expect(source.content).toBe('# Remote winner\n');
  });
});
