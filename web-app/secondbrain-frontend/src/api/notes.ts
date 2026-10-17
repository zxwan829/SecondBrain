export type Note = { collection: string; path: string; content: string; etag: string; read_only: boolean; safety_reasons: string[] };
export type NoteCollection = { id: string; kind: 'drafts' | 'authorized' };

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
  collections: () => json<{ collections: NoteCollection[] }>('/api/notes'),
  list: (collection: string) => json<{ items: { path: string; title: string }[] }>(`/api/notes/${encodeURIComponent(collection)}`),
  read: (collection: string, path: string) => json<Note>(pathUrl(collection, path)),
  create: (content: string) => json<Note>('/api/notes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }) }),
  save: (note: Note, content: string) => json<Note>(pathUrl(note.collection, note.path), { method: 'PUT', headers: { 'Content-Type': 'application/json', 'If-Match': `"${note.etag}"` }, body: JSON.stringify({ content }) }),
  history: (note: Note) => json<{ versions: { etag: string; content: string }[] }>(`${pathUrl(note.collection, note.path)}/history`),
  upload: async (note: Note, file: File) => {
    const data = new FormData(); data.append('file', file);
    return json<{ path: string; url: string }>(`${pathUrl(note.collection, note.path)}/attachments`, { method: 'POST', body: data });
  },
};
