const EDITABLE_KEYS = new Set(['tags', 'aliases', 'type', 'status', 'created', 'updated', 'description', 'source', 'related']);

export type FrontmatterFields = Partial<Record<'tags' | 'aliases' | 'type' | 'status' | 'created' | 'updated' | 'description' | 'source' | 'related', string | string[]>>;

export function splitMarkdownFrontmatter(markdown: string) {
  const normalized = markdown.startsWith('\uFEFF') ? markdown.slice(1) : markdown;
  const match = normalized.match(/^(---\r?\n)([\s\S]*?)(\r?\n---(?:\r?\n|$))/);
  if (!match) return { frontmatter: '', body: markdown, hasFrontmatter: false };
  const bodyStart = match[0].length;
  return { frontmatter: match[2] ?? '', body: normalized.slice(bodyStart), hasFrontmatter: true };
}

function unquote(value: string): string {
  const trimmed = value.trim();
  if (trimmed.startsWith('"')) {
    try { const parsed = JSON.parse(trimmed); if (typeof parsed === 'string') return parsed; } catch { /* keep raw YAML */ }
  }
  if (trimmed.startsWith("'") && trimmed.endsWith("'")) return trimmed.slice(1, -1).replace(/''/g, "'");
  return trimmed;
}

export function readKnownFrontmatter(markdown: string): FrontmatterFields {
  const { frontmatter } = splitMarkdownFrontmatter(markdown);
  const result: FrontmatterFields = {};
  const lines = frontmatter.split(/\r?\n/);
  for (const key of EDITABLE_KEYS) {
    const index = lines.findIndex(line => new RegExp(`^${key}\\s*:`).test(line));
    if (index < 0) continue;
    const first = lines[index]!.slice(lines[index]!.indexOf(':') + 1).trim();
    if (first) {
      try {
        const parsed = JSON.parse(first);
        if (typeof parsed === 'string' || Array.isArray(parsed) && parsed.every(item => typeof item === 'string')) (result as any)[key] = parsed;
        else (result as any)[key] = unquote(first);
      } catch { (result as any)[key] = unquote(first); }
    } else {
      const items: string[] = [];
      for (let cursor = index + 1; cursor < lines.length && /^\s+-\s+/.test(lines[cursor]!); cursor++) items.push(unquote(lines[cursor]!.replace(/^\s+-\s+/, '')));
      if (items.length) (result as any)[key] = items;
    }
  }
  return result;
}

/** Updates only explicitly named top-level fields; unknown YAML and body text remain untouched. */
export function updateKnownFrontmatter(markdown: string, updates: FrontmatterFields): string {
  const { frontmatter, body, hasFrontmatter } = splitMarkdownFrontmatter(markdown);
  const bom = markdown.startsWith('\uFEFF') ? '\uFEFF' : '';
  const lines = frontmatter ? frontmatter.split(/\r?\n/) : [];
  const eol = markdown.includes('\r\n') ? '\r\n' : '\n';
  for (const [rawKey, value] of Object.entries(updates)) {
    const key = rawKey.toLowerCase();
    if (!EDITABLE_KEYS.has(key) || value === undefined) continue;
    const index = lines.findIndex(line => new RegExp(`^${key}\\s*:`).test(line));
    const encoded = `${key}: ${JSON.stringify(value)}`;
    if (index >= 0) {
      let end = index + 1;
      while (end < lines.length && /^\s+/.test(lines[end]!)) end++;
      lines.splice(index, end - index, encoded);
    } else lines.push(encoded);
  }
  const yaml = lines.join(eol);
  if (!hasFrontmatter) return `${bom}---${eol}${yaml}${eol}---${body.startsWith(eol) ? '' : eol}${body.replace(/^\uFEFF/, '')}`;
  const original = markdown.startsWith('\uFEFF') ? markdown.slice(1) : markdown;
  const prefix = original.match(/^---\r?\n/)?.[0] ?? `---${eol}`;
  const closing = original.match(/\r?\n---(?:\r?\n|$)/)?.[0] ?? `${eol}---${eol}`;
  return `${bom}${prefix}${yaml}${closing}${body}`;
}
