export type Note = { collection: string; path: string; content: string; etag: string; read_only: boolean; safety_reasons: string[] };
export type NoteCollection = { id: string; kind: 'drafts' | 'authorized' };
export type VisualKind = 'mindmap' | 'excalidraw';
export type VisualAsset = { filename: string; etag: string; content: string };

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: 'same-origin', ...init });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(result.detail || `HTTP ${response.status}`) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return result as T;
}

const pathUrl = (collection: string, path: string) => `/api/notes/${encodeURIComponent(collection)}/${path.split('/').map(encodeURIComponent).join('/')}`;

export const notesApi = {
  collections: (signal?: AbortSignal) => json<{ collections: NoteCollection[] }>('/api/notes', signal ? { signal } : undefined),
  list: (collection: string, signal?: AbortSignal) => json<{ items: { path: string; title: string }[] }>(`/api/notes/${encodeURIComponent(collection)}`, signal ? { signal } : undefined),
  read: (collection: string, path: string, signal?: AbortSignal) => json<Note>(pathUrl(collection, path), signal ? { signal } : undefined),
  create: (content: string) => json<Note>('/api/notes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }) }),
  save: (note: Note, content: string) => json<Note>(pathUrl(note.collection, note.path), { method: 'PUT', headers: { 'Content-Type': 'application/json', 'If-Match': `"${note.etag}"` }, body: JSON.stringify({ content }) }),
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
};
