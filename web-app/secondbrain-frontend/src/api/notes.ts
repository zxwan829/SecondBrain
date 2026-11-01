export type Note = { collection: string; path: string; content: string; etag: string; read_only: boolean; safety_reasons: string[] };
export type NoteCollection = { id: string; kind: 'drafts' | 'authorized' };
export type NotesBrowseFolder = { name: string; path: string };
export type NotesBrowseItem = { path: string; title: string };
export type NotesBrowseResult = {
  source_kind: 'notes' | 'drafts'; collection: string; path: string; status: 'ok' | 'partial';
  items: NotesBrowseItem[]; total: number; total_complete: boolean; offset: number; limit: number;
  next_offset: number | null; scan: { entries: number; bytes: number; complete: boolean };
};
export type NotesFoldersResult = {
  source_kind: 'notes' | 'drafts'; collection: string; path: string; status: 'ok' | 'partial';
  folders: NotesBrowseFolder[]; scan: { entries: number; complete: boolean };
};
export type NoteProperties = { type: string; tags: string[]; etag: string };
export type VisualKind = 'mindmap' | 'excalidraw';
export type VisualAsset = { filename: string; etag: string; content: string };
export type NotesTrashItem = {
  trash_id: string; collection: string; path: string; sha256: string;
  size_bytes: number; trashed_at: string; status: string; duplicate: boolean;
  recovery_reason: string | null;
};

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', ...init });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(result.detail || `HTTP ${response.status}`) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return result as T;
}

function isRelativeNotePath(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= 4096
    && !value.startsWith('/') && !/[\\\u0000-\u001f\u007f]/.test(value)
    && !/%(?:2e|2f|5c|25(?:2e|2f|5c))/i.test(value)
    && value.split('/').every((part) => part && part.length <= 255 && part !== '.' && part !== '..' && !part.startsWith('.') && part !== 'attachments');
}

function isNonNegativeInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && Number(value) >= 0;
}

function contractError(): Error & { status: number } {
  return Object.assign(new Error('Notes browse response is invalid'), { status: 502 });
}

const pathUrl = (collection: string, path: string) => `/api/notes/${encodeURIComponent(collection)}/${path.split('/').map(encodeURIComponent).join('/')}`;

export const notesApi = {
  collections: (signal?: AbortSignal) => json<{ collections: NoteCollection[] }>('/api/notes', signal ? { signal } : undefined),
  list: (collection: string, signal?: AbortSignal) => json<{ items: { path: string; title: string }[] }>(`/api/notes/${encodeURIComponent(collection)}`, signal ? { signal } : undefined),
  folders: (collection: string, path: string, signal: AbortSignal) => {
    const params = new URLSearchParams({ path });
    return json<unknown>(`/api/notes/${encodeURIComponent(collection)}/folders?${params}`, { signal }).then((value) => {
      if (!value || typeof value !== 'object') throw contractError();
      const result = value as NotesFoldersResult;
      const expectedKind = collection === 'drafts' ? 'drafts' : 'notes';
      if (result.source_kind !== expectedKind || result.collection !== collection || result.path !== path
        || !['ok', 'partial'].includes(result.status) || !Array.isArray(result.folders)
        || !result.folders.every((folder) => folder && typeof folder.name === 'string' && folder.name.length > 0
          && !folder.name.includes('/') && !folder.name.includes('\\') && !folder.name.startsWith('.') && folder.name !== 'attachments'
          && isRelativeNotePath(folder.path) && folder.path === (path ? `${path}/${folder.name}` : folder.name))
        || !result.scan || typeof result.scan.complete !== 'boolean' || !isNonNegativeInteger(result.scan.entries)) {
        throw contractError();
      }
      return result;
    });
  },
  browse: (collection: string, path: string, offset: number, signal: AbortSignal) => {
    const params = new URLSearchParams({ path, offset: String(offset), limit: '20' });
    return json<unknown>(`/api/notes/${encodeURIComponent(collection)}/browse?${params}`, { signal }).then((value) => {
      if (!value || typeof value !== 'object') throw contractError();
      const result = value as NotesBrowseResult;
      const expectedKind = collection === 'drafts' ? 'drafts' : 'notes';
      if (result.source_kind !== expectedKind || result.collection !== collection || result.path !== path
        || !['ok', 'partial'].includes(result.status) || !Array.isArray(result.items)
        || !result.items.every((item) => item && isRelativeNotePath(item.path) && typeof item.title === 'string' && item.title.length <= 200)
        || !isNonNegativeInteger(result.total) || typeof result.total_complete !== 'boolean'
        || result.offset !== offset || result.limit !== 20
        || (result.next_offset !== null && (!isNonNegativeInteger(result.next_offset) || result.next_offset !== offset + 20))
        || !result.scan || !isNonNegativeInteger(result.scan.entries) || !isNonNegativeInteger(result.scan.bytes)
        || typeof result.scan.complete !== 'boolean') throw contractError();
      if (collection === 'drafts' && result.items.some((item) => !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(item.path))) throw contractError();
      return result;
    });
  },
  read: (collection: string, path: string, signal?: AbortSignal) => json<Note>(pathUrl(collection, path), signal ? { signal } : undefined),
  create: (content: string) => json<Note>('/api/notes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }) }),
  save: (note: Note, content: string) => json<Note>(pathUrl(note.collection, note.path), { method: 'PUT', headers: { 'Content-Type': 'application/json', 'If-Match': `"${note.etag}"` }, body: JSON.stringify({ content }) }),
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
  listTrash: (offset = 0, signal?: AbortSignal) => json<{ status: string; items: NotesTrashItem[]; pagination: { limit: number; offset: number; has_more: boolean } }>(
    `/api/notes/trash?limit=50&offset=${encodeURIComponent(String(offset))}`, signal ? { signal } : undefined,
  ),
  trash: (note: Note, idempotencyKey: string) => json<NotesTrashItem>(
    `/api/notes/trash/${encodeURIComponent(note.collection)}/${note.path.split('/').map(encodeURIComponent).join('/')}`,
    { method: 'DELETE', headers: { 'If-Match': `"${note.etag}"`, 'Idempotency-Key': idempotencyKey } },
  ),
  restoreTrash: (trashId: string) => json<NotesTrashItem>(
    `/api/notes/trash/${encodeURIComponent(trashId)}/restore`, { method: 'POST' },
  ),
};
