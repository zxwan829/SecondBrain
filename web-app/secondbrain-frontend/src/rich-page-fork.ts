import { notesApi, type BlockSuiteResource, type BlockSuiteResourceWrite, type Note } from './api/notes';
import { NoteBoundBlockSuiteBlobSource } from './api/notes-blocksuite-blobs';
import { sameBlockSuiteSnapshot } from './resource-snapshot-equality';
import type { NativeResourceBinding } from './native-resource-state';
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
const sameBytes = (left: Uint8Array, right: Uint8Array) => left.byteLength === right.byteLength
  && left.every((value, index) => value === right[index]);
const writePayload = (resource: BlockSuiteResourceWrite): BlockSuiteResourceWrite => ({ schemaVersion: 1, resourceId: resource.resourceId,
  resourceKind: resource.resourceKind, docId: resource.docId, updateB64: resource.updateB64, snapshot: resource.snapshot });

/** Explicit fork: read one pinned source closure, then write only a new Draft. */
export async function forkRichPageNote(sourceNote: Note, payload: BlockSuiteResourceWrite, copies: Map<string, VerifiedBlobCopy>,
  remap?: (payload: BlockSuiteResourceWrite, mapping: Map<string, NativeResourceBinding>) => BlockSuiteResourceWrite) {
  if (payload.resourceKind !== 'rich-page') throw new Error('只能将完整格式笔记另存为新笔记');
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
  const checkAcyclic = (id: string, visiting = new Set<string>(), visited = new Set<string>()) => {
    if (visiting.has(id)) throw new Error('画布资源引用形成循环；未创建新笔记');
    if (visited.has(id)) return;
    const resource = graph.get(id);
    if (!resource) throw new Error('画布资源引用映射不完整；未创建新笔记');
    visiting.add(id);
    for (const childId of snapshotCanvasIds(resource.snapshot)) checkAcyclic(childId, visiting, visited);
    visiting.delete(id); visited.add(id);
  };
  checkAcyclic(payload.resourceId);
  const referencedBlobs = new Set([...graph.values()].flatMap(value => snapshotBlobIds(value.snapshot)));
  let note = await notesApi.create('# 笔记冲突副本\n\n');
  try {
    const destinationBlobs = new NoteBoundBlockSuiteBlobSource(() => note, fetch, etag => { note = { ...note, artifactSetEtag: etag }; });
    for (const id of referencedBlobs) {
      const copy = verified.get(id)!;
      await destinationBlobs.set(id, new Blob([copy.bytes.slice().buffer as ArrayBuffer], { type: copy.contentType }));
    }
    const mapping = new Map<string, NativeResourceBinding>();
    const destination = new Map<string, BlockSuiteResource>();
    for (const [oldId, body] of graph) {
      const { resourceId: _old, ...newPayload } = body;
      // A fork owns fresh BlockSuite document identities as well as fresh
      // attachment IDs. The Yjs update is portable across the new docId.
      const created = await notesApi.createBlockSuiteResource(note, { ...newPayload, docId: crypto.randomUUID() });
      note = { ...note, artifactSetEtag: created.artifact_set_etag };
      mapping.set(oldId, { resourceId: created.resource_id, docId: created.doc_id, revision: created.etag });
      destination.set(oldId, { ...body, resourceId: created.resource_id, docId: created.doc_id, filename: created.filename, etag: created.etag,
        note_etag: created.note_etag, artifact_set_etag: created.artifact_set_etag });
    }

    // Save descendants first so each CanvasRef can bind to the final child
    // resource revision. A cycle is invalid; do not produce a partial success.
    const savedIds = new Set<string>();
    const activeIds = new Set<string>();
    const saveResource = async (oldId: string): Promise<void> => {
      if (savedIds.has(oldId)) return;
      if (activeIds.has(oldId)) throw new Error('画布资源引用形成循环；未确认新副本完整性');
      activeIds.add(oldId);
      const body = graph.get(oldId);
      if (!body) throw new Error('画布资源引用映射不完整；未确认新副本完整性');
      for (const childId of snapshotCanvasIds(body.snapshot)) await saveResource(childId);
      const previous = destination.get(oldId)!;
      const destinationBody = { ...body, docId: previous.docId };
      const rewritten = snapshotCanvasIds(body.snapshot).length ? remap!(destinationBody, mapping) : destinationBody;
      const updated = { ...writePayload(rewritten), resourceId: previous.resourceId, docId: previous.docId };
      const saved = await notesApi.saveBlockSuiteResource(note, previous, updated);
      note = { ...note, artifactSetEtag: saved.artifact_set_etag };
      destination.set(oldId, { ...previous, ...updated, etag: saved.etag, note_etag: saved.note_etag,
        artifact_set_etag: saved.artifact_set_etag });
      mapping.set(oldId, { resourceId: previous.resourceId, docId: previous.docId, revision: saved.etag });
      activeIds.delete(oldId);
      savedIds.add(oldId);
    };
    for (const oldId of graph.keys()) await saveResource(oldId);
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
    destination.set(payload.resourceId, resource);

    // Do not claim a successful recovery until the new note's complete native
    // resource and Blob closure can be read back under one pinned version.
    const persistedNote = await notesApi.readWithArtifactSet(note.collection, note.path);
    if (persistedNote.etag !== note.etag) throw new Error('新副本正文版本回读不一致；原件未改变，未确认副本成功');
    const persistedResources = new Map<string, BlockSuiteResource>();
    for (const expected of destination.values()) {
      const actual = await notesApi.readBlockSuiteResource(persistedNote, expected.resourceId);
      if (actual.resourceKind !== expected.resourceKind || actual.docId !== expected.docId
        || actual.updateB64 !== expected.updateB64 || !sameBlockSuiteSnapshot(actual.snapshot, expected.snapshot)
        || actual.note_etag !== persistedNote.etag || actual.artifact_set_etag !== persistedNote.artifactSetEtag) {
        throw new Error('新副本的 BlockSuite/Yjs 资源回读校验失败；原件未改变，未确认副本成功');
      }
      persistedResources.set(expected.resourceId, actual);
    }
    const persistedBlobs = new NoteBoundBlockSuiteBlobSource(() => persistedNote);
    for (const id of referencedBlobs) {
      const expected = verified.get(id)!;
      const actual = await persistedBlobs.get(id);
      if (!actual || actual.type !== expected.contentType
        || !sameBytes(new Uint8Array(await actual.arrayBuffer()), expected.bytes)) {
        throw new Error('新副本的图片/附件回读校验失败；原件未改变，未确认副本成功');
      }
    }
    note = persistedNote;
    resource = persistedResources.get(resource.resourceId)!;
    return { note, resource };
  } catch (cause) {
    const detail = cause instanceof Error ? cause.message : '保存或回读失败';
    try {
      const trashed = await notesApi.trash(note, crypto.randomUUID(), note.artifactSetEtag);
      if (trashed.status !== 'trashed' && trashed.status !== 'duplicate') {
        throw new Error(`回收站返回未确认状态 ${trashed.status}`);
      }
      throw Object.assign(new Error(`${detail}；未完成的新副本已移入回收站，可恢复。原笔记未改变。`),
        cause && typeof cause === 'object' && 'status' in cause ? { status: (cause as { status?: number }).status } : {});
    } catch (cleanupError) {
      if (cleanupError instanceof Error && cleanupError.message.startsWith(`${detail}；未完成的新副本已移入回收站`)) throw cleanupError;
      throw new Error(`${detail}；未能安全移入回收站，未完成副本可能仍留在 Drafts：${note.path}。原笔记未改变。`);
    }
  }
}
