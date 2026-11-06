export type MarkdownParts = { prefix: string; body: string };

/** Frontmatter remains an opaque byte-for-byte prefix outside BlockSuite's editor. */
export function splitOpaqueFrontmatter(markdown: string): MarkdownParts {
  const bom = markdown.startsWith('\ufeff') ? '\ufeff' : '';
  const source = markdown.slice(bom.length);
  const opening = source.match(/^---\r?\n/);
  if (!opening) return { prefix: '', body: markdown };
  const end = source.slice(opening[0].length).search(/\r?\n---(?:\r?\n|$)/);
  if (end < 0) throw new Error('Frontmatter is incomplete');
  const close = source.slice(opening[0].length + end).match(/^\r?\n---(?:\r?\n|$)/)![0];
  const prefixEnd = bom.length + opening[0].length + end + close.length;
  let bodyStart = prefixEnd;
  const lineBreaks = markdown.slice(bodyStart).match(/^(?:\r?\n)+/)?.[0] ?? '';
  bodyStart += lineBreaks.length;
  return { prefix: markdown.slice(0, bodyStart), body: markdown.slice(bodyStart) };
}

export function blockSuiteMarkdownMatches(source: string, serialized: string): boolean {
  // The adapter normalizes the number of terminal line breaks. Treat that
  // suffix as opaque (it is restored by preserveSourceTerminalNewlines) while
  // keeping all content and whitespace before it byte-significant after EOL
  // normalization.
  const normalize = (value: string) => value.replace(/\r\n/g, '\n').replace(/\n+$/, '');
  return normalize(source) === normalize(serialized);
}

/** Keep the user's exact terminal newline sequence when exporting through the adapter. */
export function preserveSourceTerminalNewlines(source: string, serialized: string): string {
  const serializedNormalized = serialized.replace(/\r\n/g, '\n');
  const sourceSuffix = source.match(/(?:\r?\n)*$/)?.[0] ?? '';
  const serializedBody = serializedNormalized.replace(/\n+$/, '');
  return `${serializedBody}${sourceSuffix}`;
}
