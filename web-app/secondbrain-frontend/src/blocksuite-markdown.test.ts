import { describe, expect, it } from 'vitest';
import { blockSuiteMarkdownMatches, splitOpaqueFrontmatter } from './blocksuite-markdown';

describe('BlockSuite Markdown safety boundary', () => {
  it('keeps BOM, CRLF metadata, unknown YAML keys and separator bytes opaque', () => {
    const source = '\ufeff---\r\n类型: 摘要\r\ntags: [CRM, SecondBrain]\r\ncustom: 保持原样\r\nupdated: 2026-01-01\r\n---\r\n\r\n# 标题\r\n';
    const { prefix, body } = splitOpaqueFrontmatter(source);
    expect(prefix).toBe('\ufeff---\r\n类型: 摘要\r\ntags: [CRM, SecondBrain]\r\ncustom: 保持原样\r\nupdated: 2026-01-01\r\n---\r\n\r\n');
    expect(body).toBe('# 标题\r\n');
    expect(`${prefix}${body}`).toBe(source);
  });

  it('does not invent frontmatter for plain Markdown and rejects an unterminated header', () => {
    expect(splitOpaqueFrontmatter('# 普通笔记\n')).toEqual({ prefix: '', body: '# 普通笔记\n' });
    expect(() => splitOpaqueFrontmatter('---\ntags: [x]\n正文')).toThrow('Frontmatter is incomplete');
  });

  it('accepts line-ending and single terminal-newline normalization but rejects content loss', () => {
    expect(blockSuiteMarkdownMatches('# Title\r\n\r\nBody\r\n', '# Title\n\nBody\n')).toBe(true);
    expect(blockSuiteMarkdownMatches('Plain Markdown\n', 'Plain Markdown')).toBe(true);
    expect(blockSuiteMarkdownMatches('Plain Markdown\n\n', 'Plain Markdown')).toBe(false);
    expect(blockSuiteMarkdownMatches('```text\nline  \n\n\n```\n', '```text\nline\n\n```\n')).toBe(false);
    expect(blockSuiteMarkdownMatches('Body  \n', 'Body\n')).toBe(false);
    expect(blockSuiteMarkdownMatches('[[Obsidian]]\n', '')).toBe(false);
  });
});
