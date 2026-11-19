import { marked } from 'marked';

export type MarkdownParts = { prefix: string; body: string };

function semanticMarkdown(markdown: string): string {
  const withoutRaw = (value: unknown): unknown => {
    if (Array.isArray(value)) return value
      .filter((item) => !(item && typeof item === 'object' && 'type' in item && (item as { type?: string }).type === 'space'))
      .map(withoutRaw);
    if (!value || typeof value !== 'object') return value;
    return Object.fromEntries(Object.entries(value).filter(([key]) => key !== 'raw')
      .map(([key, nested]) => [key, withoutRaw(nested)]));
  };
  const tokens = marked.lexer(markdown, { gfm: true }).filter(token => token.type !== 'space');
  return JSON.stringify(withoutRaw(tokens));
}

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
  const normalize = (value: string) => value.replace(/\r\n/g, '\n').replace(/\n+$/, '');
  const original = normalize(source);
  const roundTrip = normalize(serialized);

  if (!blockSuiteMarkdownSupportsEditing(original) || !blockSuiteMarkdownSupportsEditing(roundTrip)) return false;
  if (original === roundTrip) return true;

  try {
    // The BlockSuite adapter may canonicalize harmless Markdown formatting
    // (for example heading markers, list bullets, and table padding). Compare
    // parsed token structure and text, not raw source syntax. The original
    // terminal newline suffix is restored separately before any Core write.
    return semanticMarkdown(original) === semanticMarkdown(roundTrip);
  } catch {
    return false;
  }
}

/** Syntax whose source-level meaning the current Page editor cannot preserve. */
export function blockSuiteMarkdownSupportsEditing(markdown: string): boolean {
  return !(/^\s*[^\n]+\n[ \t]*(?:={3,}|-{3,})[ \t]*$/m.test(markdown)
    || /^(?:[ \t]*>[ \t]*)+\[![-\w]+\]/m.test(markdown));
}

/** Keep the user's exact terminal newline sequence when exporting through the adapter. */
export function preserveSourceTerminalNewlines(source: string, serialized: string): string {
  const serializedNormalized = serialized.replace(/\r\n/g, '\n');
  const sourceSuffix = source.match(/(?:\r?\n)*$/)?.[0] ?? '';
  const serializedBody = serializedNormalized.replace(/\n+$/, '');
  return `${serializedBody}${sourceSuffix}`;
}
