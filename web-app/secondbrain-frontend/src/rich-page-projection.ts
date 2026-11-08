import type { BlockSuiteResource, Note } from './api/notes';
import { splitOpaqueFrontmatter } from './blocksuite-markdown';

const marker = 'secondbrainRichPage';
const hex = /^[0-9a-f]{64}$/;
const resourceId = /^[0-9a-f]{32}$/;
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);

/** The receipt binds a native page to one exact Markdown revision, including frontmatter. */
export function richPageMarkdownBinding(snapshot: Record<string, unknown>): string | null {
  const value = snapshot[marker];
  return object(value) && value.schemaVersion === 1 && typeof value.markdownSha256 === 'string' && hex.test(value.markdownSha256)
    ? value.markdownSha256 : null;
}
export function assertRichPageMarkdownBinding(note: Note, snapshot: Record<string, unknown>) {
  if (richPageMarkdownBinding(snapshot) !== note.etag) {
    throw Object.assign(new Error('笔记内容与 Markdown 版本不一致；双方均已保留。请下载双方副本后显式处理，未自动覆盖。'), { status: 412 });
  }
}
export function bindRichPageSnapshot(snapshot: Record<string, unknown>, markdownSha256: string): Record<string, unknown> {
  if (!hex.test(markdownSha256)) throw new Error('笔记 Markdown 版本无效');
  return { ...snapshot, [marker]: { ...(object(snapshot[marker]) ? snapshot[marker] : {}), schemaVersion: 1, markdownSha256 } };
}
export async function markdownSha256(content: string): Promise<string> {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(content));
  return [...new Uint8Array(bytes)].map(value => value.toString(16).padStart(2, '0')).join('');
}
const escapeText = (value: string) => value.replace(/[\\`*_{}\[\]<>#|]/g, '\\$&');

/** A readable derivative, never a replacement for the complete native state. */
export function richPageReadableMarkdown(note: Note, resource: Pick<BlockSuiteResource, 'resourceId'>, snapshot: Record<string, unknown>): string {
  if (!resourceId.test(resource.resourceId)) throw new Error('笔记资源标识无效');
  const lines: string[] = [];
  const references = new Set<string>([resource.resourceId]);
  const propsText = (value: unknown): string[] => {
    if (Array.isArray(value)) return value.flatMap(propsText);
    if (!object(value)) return [];
    if (Array.isArray(value.delta)) return [value.delta.map(part => object(part) && typeof part.insert === 'string' ? part.insert : '').join('')];
    return Object.entries(value).filter(([key]) => key !== marker).flatMap(([key, nested]) =>
      ['text', 'title', 'name', 'description', 'label', 'caption'].includes(key) && typeof nested === 'string' ? [nested] : propsText(nested));
  };
  let documentTitleConsumed = false;
  const walk = (value: unknown) => {
    if (!object(value)) return;
    if (object(value.props)) {
      if (typeof value.props.resourceId === 'string') {
        if (!resourceId.test(value.props.resourceId)) throw new Error('画布引用尚未创建完成；请完成后再保存');
        references.add(value.props.resourceId);
      }
      const isDocumentTitle = value.props.type === 'h1' && !documentTitleConsumed;
      if (isDocumentTitle) documentTitleConsumed = true;
      const text = isDocumentTitle ? '' : propsText(value.props).filter(value => value.trim()).map(escapeText).join(' | ');
      if (text) lines.push(text);
    }
    if (Array.isArray(value.children)) value.children.forEach(walk);
  };
  const pageTitle = (value: unknown): string | null => {
    if (!object(value)) return null;
    if (object(value.props) && value.props.type === 'h1') {
      const title = propsText(value.props.text).join('').replace(/\s+/g, ' ').trim();
      if (title) return title;
    }
    if (Array.isArray(value.children)) {
      for (const child of value.children) {
        const title = pageTitle(child);
        if (title) return title;
      }
    }
    return null;
  };
  walk(snapshot.blocks);
  // The projection is allowed to refresh readable body content and stable
  // resource links. Existing frontmatter remains byte-for-byte as authored;
  // taxonomy changes continue through Core's controlled properties API.
  const prefix = splitOpaqueFrontmatter(note.content).prefix;
  const links = [...references].map(id => `[${id === resource.resourceId ? '笔记数据' : '画布数据'}](attachments/${id}.blocksuite.json)`).join('\n\n');
  const body = lines.join('\n\n');
  return `${prefix}# ${escapeText(pageTitle(snapshot.blocks) || '新建笔记')}\n\n${links}${body ? `\n\n## 正文\n\n${body}` : ''}\n`;
}
