import type { BlobSource } from '@blocksuite/sync';
import { sha } from '@blocksuite/global/utils';
import type { Note } from './notes';

export const MAX_BLOCKSUITE_BLOB_BYTES = 5 * 1024 * 1024;

type NoteSource = () => Note;

export class NoteBoundBlockSuiteBlobSource implements BlobSource {
  readonly name = 'core-notes-blocksuite-blob-source';
  readonly readonly = false;
  artifactSetEtag = '';

  constructor(private readonly getNote: NoteSource, private readonly fetcher: typeof fetch = fetch,
    private readonly onArtifactSetEtag?: (etag: string) => void) {
    this.artifactSetEtag = getNote().artifactSetEtag ?? '';
  }

  async get(key: string): Promise<Blob | null> {
    assertCanonicalBlockSuiteBlobKey(key);
    const note = this.getNote();
    const response = await this.fetcher(blobUrl(note, key), {
      credentials: 'same-origin', cache: 'no-store',
    });
    if (response.status === 404) return null;
    if (!response.ok) throw httpError('GET', response.status);
    assertNoteEtag(response.headers.get('X-Note-ETag'), note.etag);
    this.assertArtifactSet(response.headers.get('X-Artifact-Set-ETag'));
    const bytes = await readBounded(response, MAX_BLOCKSUITE_BLOB_BYTES);
    if (bytes.byteLength > MAX_BLOCKSUITE_BLOB_BYTES) throw new Error('Core Notes 返回了超过限制的图片资源');
    const mediaType = sniffSupportedImage(bytes);
    const contentKey = await blockSuiteSha(bytes);
    if (contentKey !== key || trimEtag(response.headers.get('ETag')) !== shaKeyHex(key)) {
      throw new Error('Core Notes Blob 摘要与 BlockSuite sourceId 不一致');
    }
    this.updateArtifactSetEtag(response.headers.get('X-Artifact-Set-ETag'));
    if (response.headers.get('Content-Type')?.split(';', 1)[0]?.trim().toLowerCase() !== mediaType) {
      throw new Error('Core Notes Blob 类型与图片内容不匹配');
    }
    return new Blob([bytes], { type: mediaType });
  }

  async set(key: string, value: Blob): Promise<string> {
    assertCanonicalBlockSuiteBlobKey(key);
    if (value.size > MAX_BLOCKSUITE_BLOB_BYTES) throw new Error('单个 BlockSuite 图片不得超过 5 MiB');
    const bytes = new Uint8Array(await value.arrayBuffer());
    const mediaType = sniffSupportedImage(bytes);
    if (value.type && value.type.toLowerCase() !== mediaType) {
      throw new Error('BlockSuite 图片 MIME 与实际文件类型不一致');
    }
    if (await blockSuiteSha(bytes) !== key) throw new Error('BlockSuite Blob key 与内容 SHA-256 不一致');
    const note = this.getNote();
    const response = await this.fetcher(blobUrl(note, key), {
      method: 'PUT', credentials: 'same-origin', cache: 'no-store',
      headers: { 'Content-Type': mediaType, 'If-Match': `"${note.etag}"`,
        'If-Artifact-Set-Match': `"${this.artifactSetEtag || note.artifactSetEtag || ''}"` },
      body: value,
    });
    if (!response.ok) throw httpError('PUT', response.status);
    const result = await response.json().catch(() => null) as null | { blob_id?: unknown; etag?: unknown; size_bytes?: unknown; content_type?: unknown; note_etag?: unknown; artifact_set_etag?: unknown };
    if (!result || result.blob_id !== key || result.etag !== shaKeyHex(key) || result.size_bytes !== bytes.byteLength
      || result.content_type !== mediaType || trimEtag(response.headers.get('ETag')) !== shaKeyHex(key)
      || trimEtag(String(result.note_etag ?? '')) !== note.etag
      || trimEtag(response.headers.get('X-Note-ETag')) !== note.etag
      || trimEtag(response.headers.get('X-Artifact-Set-ETag')) !== trimEtag(String(result.artifact_set_etag ?? ''))) {
      throw new Error('Core Notes Blob 写入确认的摘要与上传内容不匹配');
    }
    this.updateArtifactSetEtag(response.headers.get('X-Artifact-Set-ETag'));
    return key;
  }

  async delete(_key: string): Promise<void> {
    throw new Error('Core Notes BlockSuite Blob 是不可变的；此接口不提供删除。');
  }

  async list(): Promise<string[]> {
    throw new Error('Core Notes 未提供 Blob 列举接口；请从当前 BlockSuite Yjs 文档读取引用。');
  }

  private updateArtifactSetEtag(value: string | null) {
    const next = trimEtag(value);
    if (!next) throw new Error('Core Notes 未返回 Artifact Set ETag；没有继续混合版本 Blob 读写。');
    this.artifactSetEtag = next;
    this.onArtifactSetEtag?.(next);
  }

  private assertArtifactSet(value: string | null) {
    const actual = trimEtag(value);
    if (!actual || (this.artifactSetEtag && actual !== this.artifactSetEtag)) {
      const error = new Error('笔记附件集合已变化；未读取混合版本的 Blob。') as Error & { status?: number };
      error.status = 412;
      throw error;
    }
    this.updateArtifactSetEtag(value);
  }
}

function blobUrl(note: Note, key: string) {
  const path = note.path.split('/').map(encodeURIComponent).join('/');
  return `/api/notes/${encodeURIComponent(note.collection)}/${path}/blocksuite/blobs/${encodeURIComponent(key)}`;
}

function httpError(method: string, status: number) {
  const error = new Error(`Core Notes BlockSuite Blob ${method} 失败（HTTP ${status}）`) as Error & { status?: number };
  error.status = status;
  return error;
}

function trimEtag(value: string | null) { return value?.replace(/^"|"$/g, '') ?? ''; }

function assertNoteEtag(actual: string | null, expected: string) {
  if (trimEtag(actual) !== expected) {
    const error = new Error('笔记版本已变化；未读取混合版本的 Blob。') as Error & { status?: number };
    error.status = 412;
    throw error;
  }
}

function assertCanonicalBlockSuiteBlobKey(value: string) {
  if (!/^[A-Za-z0-9_-]{43}=$/.test(value) || !atob(value.replace(/-/g, '+').replace(/_/g, '/')).length) {
    throw new Error('无效的 BlockSuite SHA-256 Blob key');
  }
}

async function blockSuiteSha(bytes: Uint8Array) {
  return sha(bytes.slice().buffer as ArrayBuffer);
}

function shaKeyHex(key: string) {
  const raw = atob(key.replace(/-/g, '+').replace(/_/g, '/'));
  return Array.from(raw, (char) => char.charCodeAt(0).toString(16).padStart(2, '0')).join('');
}

async function readBounded(response: Response, limit: number) {
  if (!response.body) return new Uint8Array(await response.arrayBuffer());
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > limit) {
      await reader.cancel();
      throw new Error('Core Notes 返回了超过 5 MiB 限制的图片资源');
    }
    chunks.push(value);
  }
  const output = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { output.set(chunk, offset); offset += chunk.byteLength; }
  return output;
}

function sniffSupportedImage(bytes: Uint8Array): string {
  if (bytes.length >= 8 && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47
    && bytes[4] === 0x0d && bytes[5] === 0x0a && bytes[6] === 0x1a && bytes[7] === 0x0a) return 'image/png';
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return 'image/jpeg';
  if (bytes.length >= 6 && String.fromCharCode(...bytes.subarray(0, 6)).match(/^GIF8[79]a$/)) return 'image/gif';
  if (bytes.length >= 12 && String.fromCharCode(...bytes.subarray(0, 4)) === 'RIFF'
    && String.fromCharCode(...bytes.subarray(8, 12)) === 'WEBP') return 'image/webp';
  throw new Error('当前只支持 PNG、JPEG、GIF 或 WebP 图片；SVG 与其他 Blob 类型不会上传。');
}
