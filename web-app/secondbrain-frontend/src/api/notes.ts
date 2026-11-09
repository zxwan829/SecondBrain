export type Note = { collection: string; path: string; content: string; etag: string; artifactSetEtag?: string; read_only: boolean; safety_reasons: string[] };
export type NoteCollection = { id: string; kind: 'drafts' | 'authorized' };
export type NoteProperties = { type: string; tags: string[]; etag: string };
export type VisualKind = 'mindmap' | 'excalidraw';
export type VisualAsset = { filename: string; etag: string; content: string };
export type BlockSuiteResourceKind = 'database' | 'edgeless-canvas' | 'rich-page';
export type BlockSuiteResource = {
  schemaVersion: 1; resourceId: string; resourceKind: BlockSuiteResourceKind; docId: string;
  updateB64: string; snapshot: Record<string, unknown>; etag: string; note_etag: string; artifact_set_etag?: string; filename: string;
};
export type BlockSuiteResourceWrite = Omit<BlockSuiteResource, 'etag' | 'note_etag' | 'filename'>;
export type NotesTrashItem = {
  trash_id: string; collection: string; path: string; sha256: string;
  size_bytes: number; trashed_at: string; status: string; duplicate: boolean;
  recovery_reason: string | null;
};
export type BlockSuiteSnapshotEntry = { snapshot_id: string; note_sha256: string; artifact_set_etag: string; created_at: string; artifact_count: number; artifact_bytes: number };
export type BlockSuiteSnapshots = { note_etag: string; artifact_set_etag: string; snapshots: BlockSuiteSnapshotEntry[] };
export type BlockSuiteSnapshotDetail = {
  snapshot_id: string; note: { content: string; etag: string }; artifact_set_etag: string;
  artifacts: BlockSuiteSnapshotArtifact[];
};
export type BlockSuiteSnapshotArtifact = {
  kind?: 'resource' | 'blob'; id?: string; resource_id?: string; etag?: string; sha256?: string;
  bytes?: number; size_bytes?: number; content_type?: string; data_base64?: string;
  resource?: BlockSuiteResourceWrite; blob?: Record<string, unknown>;
};
export type BlockSuiteSnapshotRestoreResult = {
  snapshot_id: string; note_etag: string; artifact_set_etag: string; restored: boolean; duplicate: boolean;
};

const etagHeader = (value?: string) => value ? `"${value.replace(/^"|"$/g, '')}"` : undefined;
function withArtifactSet(note: Note, init: RequestInit = {}): RequestInit {
  if (!note.artifactSetEtag) return init;
  const headers = new Headers(init.headers);
  headers.set('If-Artifact-Set-Match', etagHeader(note.artifactSetEtag)!);
  return { ...init, headers };
}

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: 'same-origin', ...init });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(result.detail || `HTTP ${response.status}`) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  if (result && typeof result === 'object') {
    const data = result as Record<string, unknown>;
    const noteHeader = response.headers.get('X-Note-ETag')?.replace(/^"|"$/g, '');
    const bodyNoteEtag = typeof data.note_etag === 'string' ? data.note_etag
      : data.note && typeof data.note === 'object' && typeof (data.note as Record<string, unknown>).etag === 'string'
        ? (data.note as Record<string, unknown>).etag as string : undefined;
    const artifactHeader = response.headers.get('X-Artifact-Set-ETag')?.replace(/^"|"$/g, '');
    if ((noteHeader && bodyNoteEtag && noteHeader !== bodyNoteEtag)
        || (artifactHeader && typeof data.artifact_set_etag === 'string' && artifactHeader !== data.artifact_set_etag)) {
      throw Object.assign(new Error('Core Notes 响应头与 BlockSuite 版本摘要不一致。'), { status: 412 });
    }
    if (artifactHeader) data.artifact_set_etag = artifactHeader;
    if (typeof data.artifact_set_etag === 'string') data.artifactSetEtag = data.artifact_set_etag;
  }
  return result as T;
}

const pathUrl = (collection: string, path: string) => `/api/notes/${encodeURIComponent(collection)}/${path.split('/').map(encodeURIComponent).join('/')}`;

export const notesApi = {
  collections: (signal?: AbortSignal) => json<{ collections: NoteCollection[] }>('/api/notes', signal ? { signal } : undefined),
  list: (collection: string, signal?: AbortSignal) => json<{ items: { path: string; title: string }[] }>(`/api/notes/${encodeURIComponent(collection)}`, signal ? { signal } : undefined),
  read: (collection: string, path: string, signal?: AbortSignal) => json<Note>(pathUrl(collection, path), signal ? { signal } : undefined),
  create: (content: string) => json<Note>('/api/notes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }) }),
  save: async (note: Note, content: string) => {
    const saved = await json<Note>(pathUrl(note.collection, note.path), withArtifactSet(note, { method: 'PUT', headers: { 'Content-Type': 'application/json', 'If-Match': etagHeader(note.etag)! }, body: JSON.stringify({ content }) }));
    if (!saved.artifactSetEtag) saved.artifactSetEtag = note.artifactSetEtag;
    return saved;
  },
  readWithArtifactSet: async (collection: string, path: string): Promise<Note> => {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const note = await json<Note>(pathUrl(collection, path));
      const closure = await json<BlockSuiteSnapshots>(`${pathUrl(collection, path)}/blocksuite/snapshots`);
      if (note.etag === closure.note_etag) return { ...note, artifactSetEtag: closure.artifact_set_etag };
    }
    throw Object.assign(new Error('笔记与 BlockSuite 附件集合持续变化；请刷新后重试。'), { status: 412 });
  },
  readBlockSuiteSnapshots: (note: Note) => json<BlockSuiteSnapshots>(`${pathUrl(note.collection, note.path)}/blocksuite/snapshots`),
  readBlockSuiteSnapshot: (note: Note, snapshotId: string) => json<BlockSuiteSnapshotDetail>(
    `${pathUrl(note.collection, note.path)}/blocksuite/snapshots/${encodeURIComponent(snapshotId)}`,
  ),
  restoreBlockSuiteSnapshot: (note: Note, snapshotId: string) => json<BlockSuiteSnapshotRestoreResult>(
    `${pathUrl(note.collection, note.path)}/blocksuite/snapshots/${encodeURIComponent(snapshotId)}/restore`,
    { method: 'POST', headers: {
      'If-Match': etagHeader(note.etag)!,
      'If-Artifact-Set-Match': etagHeader(note.artifactSetEtag)!,
    } },
  ),
  readProperties: (note: Note) => json<NoteProperties>(`${pathUrl(note.collection, note.path)}/properties`),
  saveProperties: (note: Note, type: string, tags: string[]) => json<Note>(`${pathUrl(note.collection, note.path)}/properties`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json', 'If-Match': `"${note.etag}"` },
    body: JSON.stringify({ type, tags, confirmed: true }),
  }),
  history: (note: Note) => json<{ versions: { etag: string; content: string }[] }>(`${pathUrl(note.collection, note.path)}/history`),
  upload: async (note: Note, file: File) => {
    const data = new FormData(); data.append('file', file);
    return json<{ path: string; url: string }>(`${pathUrl(note.collection, note.path)}/attachments`, { method: 'POST', body: data });
  },
  createVisualAsset: (note: Note, kind: VisualKind, content: string) =>
    json<{ path: string; filename: string; etag: string }>(`${pathUrl(note.collection, note.path)}/visual-assets/${kind}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'If-Match': `"${note.etag}"` }, body: JSON.stringify({ content }),
    }),
  readVisualAsset: async (note: Note, filename: string): Promise<VisualAsset> => {
    const response = await fetch(`${pathUrl(note.collection, note.path)}/attachments/${encodeURIComponent(filename)}`, { credentials: 'same-origin' });
    if (!response.ok) throw Object.assign(new Error(`HTTP ${response.status}`), { status: response.status });
    return { filename, content: await response.text(), etag: (response.headers.get('ETag') || '').replace(/^"|"$/g, '') };
  },
  saveVisualAsset: (note: Note, asset: VisualAsset, content: string) =>
    json<{ etag: string }>(`${pathUrl(note.collection, note.path)}/attachments/${encodeURIComponent(asset.filename)}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json', 'If-Match': `"${note.etag}"`, 'If-Asset-Match': `"${asset.etag}"` },
      body: JSON.stringify({ content }),
    }),
  createBlockSuiteResource: (note: Note, body: Omit<BlockSuiteResourceWrite, 'resourceId'>) =>
    json<{ resource_id: string; resource_kind: BlockSuiteResourceKind; doc_id: string; filename: string; reference: string; etag: string; note_etag: string; artifact_set_etag: string }>(
      `${pathUrl(note.collection, note.path)}/blocksuite/resources`,
      withArtifactSet(note, { method: 'POST', headers: { 'Content-Type': 'application/json', 'If-Match': etagHeader(note.etag)! }, body: JSON.stringify(body) }),
    ),
  readBlockSuiteResource: (note: Note, resourceId: string) =>
    json<BlockSuiteResource>(`${pathUrl(note.collection, note.path)}/blocksuite/resources/${encodeURIComponent(resourceId)}`),
  saveBlockSuiteResource: (note: Note, resource: BlockSuiteResource, body: BlockSuiteResourceWrite) =>
    json<{ resource_id: string; resource_kind: BlockSuiteResourceKind; doc_id: string; filename: string; etag: string; note_etag: string; artifact_set_etag: string }>(
      `${pathUrl(note.collection, note.path)}/blocksuite/resources/${encodeURIComponent(resource.resourceId)}`,
      withArtifactSet(note, { method: 'PUT', headers: { 'Content-Type': 'application/json', 'If-Match': etagHeader(note.etag)!, 'If-Resource-Match': etagHeader(resource.etag)! }, body: JSON.stringify(body) }),
    ),
  listTrash: (offset = 0, signal?: AbortSignal) => json<{ status: string; items: NotesTrashItem[]; pagination: { limit: number; offset: number; has_more: boolean } }>(
    `/api/notes/trash?limit=50&offset=${encodeURIComponent(String(offset))}`, signal ? { signal } : undefined,
  ),
  trash: (note: Note, idempotencyKey: string, artifactSetEtag = note.artifactSetEtag) => json<NotesTrashItem>(
    `/api/notes/trash/${encodeURIComponent(note.collection)}/${note.path.split('/').map(encodeURIComponent).join('/')}`,
    { method: 'DELETE', headers: {
      'If-Match': `"${note.etag}"`, 'Idempotency-Key': idempotencyKey,
      ...(artifactSetEtag ? { 'If-Artifact-Set-Match': etagHeader(artifactSetEtag)! } : {}),
    } },
  ),
  restoreTrash: (trashId: string) => json<NotesTrashItem>(
    `/api/notes/trash/${encodeURIComponent(trashId)}/restore`, { method: 'POST' },
  ),
};
