import React from 'react';

export type ReviewDocument = { metadata: Record<string, string>; body: string };

export function parseReviewDocument(content: string): ReviewDocument {
  const lines = content.replace(/\r\n?/g, '\n').split('\n');
  if (lines[0]?.trim() !== '---') return { metadata: {}, body: content };
  const end = lines.indexOf('---', 1);
  if (end < 0) return { metadata: {}, body: content };
  const metadata: Record<string, string> = {};
  for (const line of lines.slice(1, end)) {
    const match = /^([A-Za-z0-9_-]+):\s*(.*)$/.exec(line);
    if (!match) continue;
    const [, key, raw] = match;
    let value = raw;
    if (raw.startsWith('"')) {
      try { value = JSON.parse(raw) as string; } catch { /* retain plain metadata text */ }
    }
    metadata[key] = value;
  }
  return { metadata, body: lines.slice(end + 1).join('\n').replace(/^\n/, '') };
}

function safeInline(text: string, keyPrefix: string): React.ReactNode[] {
  const tokens = /(\`[^\`]*\`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;
  const nodes: React.ReactNode[] = [];
  let offset = 0;
  for (const match of text.matchAll(tokens)) {
    const index = match.index ?? 0;
    if (index > offset) nodes.push(text.slice(offset, index));
    const token = match[0];
    if (token.startsWith('`')) nodes.push(<code key={keyPrefix + index}>{token.slice(1, -1)}</code>);
    else if (token.startsWith('**')) nodes.push(<strong key={keyPrefix + index}>{token.slice(2, -2)}</strong>);
    else if (token.startsWith('*')) nodes.push(<em key={keyPrefix + index}>{token.slice(1, -1)}</em>);
    else {
      const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
      if (link) {
        let safe = false;
        try { safe = ['http:', 'https:'].includes(new URL(link[2], window.location.origin).protocol); } catch { /* render as text */ }
        nodes.push(safe
          ? <a key={keyPrefix + index} href={link[2]} target="_blank" rel="noreferrer">{link[1]}</a>
          : link[1]);
      }
    }
    offset = index + token.length;
  }
  if (offset < text.length) nodes.push(text.slice(offset));
  return nodes;
}

export function ReviewMarkdown({ source, preserveLines = false }: { source: string; preserveLines?: boolean }) {
  if (preserveLines) return <pre className="review-markdown-raw">{source}</pre>;
  const lines = source.split('\n');
  const blocks: React.ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index += 1; continue; }
    const fence = /^\s*(`{3,}|~{3,})/.exec(line);
    if (fence) {
      const marker = fence[1][0];
      index += 1;
      const code: string[] = [];
      while (index < lines.length && !new RegExp(`^\\s*${marker}{3,}\\s*$`).test(lines[index])) {
        code.push(lines[index++]);
      }
      if (index < lines.length) index += 1;
      blocks.push(<pre className="review-markdown-code" key={blocks.length}><code>{code.join('\n')}</code></pre>);
      continue;
    }
    const heading = /^(#{1,6})\s+(.+)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      blocks.push(React.createElement(`h${level}`, { key: blocks.length }, safeInline(heading[2], `h${blocks.length}-`)));
      index += 1;
      continue;
    }
    if (/^\s*[-*+]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*[-*+]\s+/.test(lines[index])) items.push(lines[index++].replace(/^\s*[-*+]\s+/, ''));
      blocks.push(<ul key={blocks.length}>{items.map((item, itemIndex) => <li key={itemIndex}>{safeInline(item, `li${blocks.length}-${itemIndex}-`)}</li>)}</ul>);
      continue;
    }
    const paragraph: string[] = [];
    while (index < lines.length && lines[index].trim() && !/^(#{1,6})\s+/.test(lines[index]) && !/^\s*[-*+]\s+/.test(lines[index]) && !/^\s*(`{3,}|~{3,})/.test(lines[index])) {
      paragraph.push(lines[index++]);
    }
    blocks.push(<p key={blocks.length}>{paragraph.map((part, partIndex) => <React.Fragment key={partIndex}>{partIndex > 0 && <br />}{safeInline(part, `p${blocks.length}-${partIndex}-`)}</React.Fragment>)}</p>);
  }
  return <div className="review-markdown">{blocks}</div>;
}
