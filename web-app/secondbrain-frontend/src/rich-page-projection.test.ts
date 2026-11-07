import { describe, expect, it } from 'vitest';
import { assertRichPageMarkdownBinding, bindRichPageSnapshot, markdownSha256, richPageReadableMarkdown } from './rich-page-projection';
import type { Note } from './api/notes';
const note: Note = { collection: 'drafts', path: 'synthetic.md', content: '---\ncustom: preserve\n---\n\nold projection\n', etag: 'a'.repeat(64), read_only: false, safety_reasons: [] };
const id = 'b'.repeat(32);
const snapshot = { blocks: { props: {}, children: [{ props: { text: { delta: [{ insert: '正文 <script>\n下一行' }] }, textAlign: 'center' }, children: [] }] } };
describe('rich-page readable projection and exact revision binding', () => {
  it('keeps frontmatter and readable text while the native snapshot retains rich geometry', () => {
    const richSnapshot = { ...snapshot, blocks: { ...snapshot.blocks, children: [
      { props: { type: 'h1', text: { delta: [{ insert: 'My title' }] } }, children: [] },
      ...snapshot.blocks.children,
    ] } };
    const markdown = richPageReadableMarkdown(note, { resourceId: id }, richSnapshot);
    expect(markdown).toContain('# My title');
    expect(markdown).toContain('---\ncustom: preserve\n---\n\n');
    expect(markdown).toContain(`attachments/${id}.blocksuite.json`);
    expect(markdown).toContain('正文 \\<script\\>\n下一行');
    expect(snapshot.blocks.children[0].props.textAlign).toBe('center');
  });
  it('rejects missing or stale receipts, including frontmatter-only external changes', async () => {
    expect(() => assertRichPageMarkdownBinding(note, snapshot)).toThrow(/版本不一致/);
    const bound = bindRichPageSnapshot(snapshot, note.etag);
    expect(() => assertRichPageMarkdownBinding(note, bound)).not.toThrow();
    const changed = { ...note, etag: await markdownSha256(note.content.replace('preserve', 'external')) };
    expect(() => assertRichPageMarkdownBinding(changed, bound)).toThrow(/双方均已保留/);
  });
  it('refuses an unfinished nested canvas reference and preserves native data', () => {
    const native = { blocks: { props: { resourceId: '' }, children: [] } };
    expect(() => richPageReadableMarkdown(note, { resourceId: id }, native)).toThrow(/尚未创建完成/);
    expect(native.blocks.props.resourceId).toBe('');
  });
});
