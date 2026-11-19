import { describe, expect, it } from 'vitest';
import { assertPlainSnapshotMarkdownCompatible, findPlainMarkdownFormatViolations } from './plain-markdown-format-guard';
const block = (flavour: string, props: Record<string, unknown>) => ({ id: 'synthetic-block', flavour, props, children: [] });
const page = (...blocks: unknown[]) => ({ type: 'page', blocks: { ...block('affine:page', {}), children: blocks } });

describe('ordinary Markdown format persistence boundary', () => {
  it('accepts Markdown text marks and default layout without adding authority', () => {
    expect(() => assertPlainSnapshotMarkdownCompatible(page(block('affine:paragraph', { textAlign: 'left', text: { delta: [{ insert: 'text', attributes: { bold: true, italic: true, link: 'https://example.test' } }] } }), block('affine:table', { cells: { a: { textAlign: 'left', verticalAlign: 'top' } }, rows: { a: {} }, columns: { a: {} }, mergeRegions: {} })))).not.toThrow();
  });
  it.each([
    ['paragraph-alignment', 'affine:paragraph', { textAlign: 'center' }],
    ['table-merge', 'affine:table', { mergeRegions: { r: { rowIds: ['a'] } } }],
    ['table-alignment', 'affine:table', { cells: { a: { verticalAlign: 'middle' } } }],
    ['table-color', 'affine:table', { cells: { a: { textColor: 'red' } } }],
    ['table-color', 'affine:table', { rows: { a: { backgroundColor: '#fff' } } }],
    ['table-row-height', 'affine:table', { rows: { a: { minHeight: 64 } } }],
    ['table-column-width', 'affine:table', { columns: { a: { width: 180 } } }],
    ['inline-format', 'affine:paragraph', { text: { delta: [{ insert: 'text', attributes: { color: 'red' } }] } }],
    ['native-resource-block', 'sb:canvas-ref', { resourceId: 'synthetic-canvas' }],
    ['native-graphics', 'affine:surface', { elements: { a: { type: 'shape' } } }],
  ])('rejects %s before Markdown export', (reason, flavour, props) => {
    const input = page(block(String(flavour), props as Record<string, unknown>));
    expect(findPlainMarkdownFormatViolations(input)).toContainEqual({ reason, blockId: 'synthetic-block' });
    expect(() => assertPlainSnapshotMarkdownCompatible(input)).toThrow(/停止正文写入/);
  });
  it('does not change the input while detecting unsupported data', () => {
    const input = page(block('affine:paragraph', { textAlign: 'right' }));
    const before = JSON.stringify(input); findPlainMarkdownFormatViolations(input);
    expect(JSON.stringify(input)).toBe(before);
  });
});
