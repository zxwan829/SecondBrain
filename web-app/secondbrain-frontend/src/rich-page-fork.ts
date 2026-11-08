import { notesApi, type BlockSuiteResource, type BlockSuiteResourceWrite, type Note } from './api/notes';
import { NoteBoundBlockSuiteBlobSource } from './api/notes-blocksuite-blobs';
import { bindRichPageSnapshot, markdownSha256, richPageReadableMarkdown } from './rich-page-projection';

export type VerifiedBlobCopy = { contentType: string; bytes: Uint8Array };
function snapshotIds(snapshot: unknown, key: string): string[] {
  const ids = new Set<string>();
  const walk = (value: unknown) => {
    if (!value || typeof value !== 'object') return;
    if (Array.isArray(value)) { value.forEach(walk); return; }
    for (const [name, child] of Object.entries(value)) {
      if (name === key && typeof child === 'string' && child) ids.add(child);
      else walk(child);
    }
  };
  walk(snapshot); return [...ids];
}
export const snapshotBlobIds = (snapshot: unknown) => snapshotIds(snapshot, 'sourceId');
export const snapshotCanvasIds = (snapshot: unknown) => snapshotIds(snapshot, 'resourceId');
const writePayload = (resource: BlockSuiteResourceWrite): BlockSuiteResourceWrite => ({ schemaVersion: 1, resourceId: resource.resourceId,
  resourceKind: resource.resourceKind, docId: resource.docId, updateB64: resource.updateB64, snapshot: resource.snapshot });

/** Explicit fork: read one pinned source closure, then write only a new Draft. */
export async function forkRichPageNote(sourceNote: Note, payload: BlockSuiteResourceWrite, copies: Map<string, VerifiedBlobCopy>,
  remap?: (payload: BlockSuiteResourceWrite, mapping: Map<string, string>) => BlockSuiteResourceWrite) {
  if (payload.resourceKind !== 'rich-page') throw new Error('只能将富 Page 另存为新笔记');
  const nestedIds = snapshotCanvasIds(payload.snapshot);
  if (nestedIds.length && !remap) throw new Error('画布深拷贝尚未就绪；未创建新笔记');
  // Pin the current Markdown and native-resource collection together, even if
  // this Page has no child canvases. The conflict fork must preserve the
  // external version alongside the local Yjs document.
  const source = await notesApi.readWithArtifactSet(sourceNote.collection, sourceNote.path);
  const graph = new Map<string, BlockSuiteResourceWrite>([[payload.resourceId, writePayload(payload)]]);
  const queue = [...nestedIds];
  while (queue.length) {
    const id = queue.shift()!;
    if (graph.has(id)) continue;
    if (graph.size >= 64 || !/^[0-9a-f]{32}$/.test(id)) throw new Error('画布引用集合无效或超过现有限额；未创建新笔记');
    const resource = await notesApi.readBlockSuiteResource(source, id);
    if (resource.note_etag !== source.etag || resource.artifact_set_etag !== source.artifactSetEtag) {
      throw Object.assign(new Error('引用资源在读取期间变化；未创建混合版本副本'), { status: 412 });
    }
    if (resource.resourceKind !== 'edgeless-canvas') throw new Error('画布引用指向非画布资源；未创建新笔记');
    graph.set(id, writePayload(resource)); queue.push(...snapshotCanvasIds(resource.snapshot));
  }
  const verified = new Map(copies);
  const sourceBlobs = new NoteBoundBlockSuiteBlobSource(() => source);
  for (const resource of graph.values()) {
    for (const id of snapshotBlobIds(resource.snapshot)) {
      if (verified.has(id)) continue;
      // Local unsaved images must already have a verified copy; nested remote
      // resources may be loaded from the pinned source closure before any write.
      if (resource.resourceId === payload.resourceId) throw new Error('完整图片副本尚未就绪；未创建新笔记');
      const blob = await sourceBlobs.get(id);
      if (!blob) throw new Error('引用画布图片缺失；未创建新笔记');
      verified.set(id, { contentType: blob.type, bytes: new Uint8Array(await blob.arrayBuffer()) });
    }
  }
  let note = await notesApi.create('# 富 Page 冲突副本\n\n');
  const destinationBlobs = new NoteBoundBlockSuiteBlobSource(() => note, fetch, etag => { note = { ...note, artifactSetEtag: etag }; });
  for (const id of new Set([...graph.values()].flatMap(value => snapshotBlobIds(value.snapshot)))) {
    const copy = verified.get(id)!;
    await destinationBlobs.set(id, new Blob([copy.bytes.slice().buffer as ArrayBuffer], { type: copy.contentType }));
  }
  const mapping = new Map<string, string>();
  const destination = new Map<string, BlockSuiteResource>();
  for (const [oldId, body] of graph) {
    const { resourceId: _old, ...newPayload } = body;
    const created = await notesApi.createBlockSuiteResource(note, newPayload);
    note = { ...note, artifactSetEtag: created.artifact_set_etag };
    mapping.set(oldId, created.resource_id);
    destination.set(oldId, { ...body, resourceId: created.resource_id, filename: created.filename, etag: created.etag,
      note_etag: created.note_etag, artifact_set_etag: created.artifact_set_etag });
  }
  for (const [oldId, body] of graph) {
    const previous = destination.get(oldId)!;
    const rewritten = snapshotCanvasIds(body.snapshot).length ? remap!(body, mapping) : body;
    const updated = { ...writePayload(rewritten), resourceId: previous.resourceId };
    const saved = await notesApi.saveBlockSuiteResource(note, previous, updated);
    note = { ...note, artifactSetEtag: saved.artifact_set_etag };
    destination.set(oldId, { ...previous, ...updated, etag: saved.etag, artifact_set_etag: saved.artifact_set_etag });
  }
  let resource = destination.get(payload.resourceId)!;
  let markdown = richPageReadableMarkdown(source, resource, resource.snapshot);
  if (source.etag !== sourceNote.etag) {
    const longestFence = Math.max(0, ...[...source.content.matchAll(/`+/g)].map(match => match[0].length));
    const fence = '`'.repeat(Math.max(3, longestFence + 1));
    markdown += `\n\n## 冲突时的外部 Markdown 原文\n\n${fence}markdown\n${source.content}\n${fence}\n`;
  }
  note = await notesApi.save(note, markdown);
  if (note.etag !== await markdownSha256(markdown)) throw new Error('新副本投影版本未能确认；原件未改变');
  const bound = { ...writePayload(resource), snapshot: bindRichPageSnapshot(resource.snapshot, note.etag) };
  const saved = await notesApi.saveBlockSuiteResource(note, resource, bound);
  note = { ...note, artifactSetEtag: saved.artifact_set_etag };
  resource = { ...resource, ...bound, etag: saved.etag, note_etag: saved.note_etag, artifact_set_etag: saved.artifact_set_etag };
  return { note, resource };
}
