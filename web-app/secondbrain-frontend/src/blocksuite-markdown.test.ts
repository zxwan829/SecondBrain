import { describe, expect, it } from 'vitest';
import { blockSuiteMarkdownMatches, blockSuiteMarkdownSupportsEditing, preserveSourceTerminalNewlines, splitOpaqueFrontmatter } from './blocksuite-markdown';

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

  it('accepts semantic Markdown normalization while preserving exact source terminal newlines', () => {
    expect(blockSuiteMarkdownMatches('# Title\r\n\r\nBody\r\n', '# Title\n\nBody\n')).toBe(true);
    expect(blockSuiteMarkdownMatches('Plain Markdown\n', 'Plain Markdown')).toBe(true);
    expect(blockSuiteMarkdownMatches('Plain Markdown\n\n', 'Plain Markdown')).toBe(true);
    expect(preserveSourceTerminalNewlines('Plain Markdown\r\n\r\n', 'Plain Markdown\n')).toBe('Plain Markdown\r\n\r\n');
    expect(blockSuiteMarkdownMatches('# Heading\n\n- one\n- two\n', '# Heading\n\n* one\n* two\n')).toBe(true);
    expect(blockSuiteMarkdownMatches('| A | B |\n| --- | --- |\n| x | y |\n', '|A|B|\n|---|---|\n|x|y|\n')).toBe(true);
    expect(blockSuiteMarkdownMatches('[label](https://example.invalid)\n', '[label](https://example.invalid "title")\n')).toBe(false);
    expect(blockSuiteMarkdownMatches('| A | B |\n| --- | --- |\n| x | y |\n', '| A | B |\n| :--- | ---: |\n| x | y |\n')).toBe(false);
    expect(blockSuiteMarkdownMatches('| A | B |\n| --- | --- |\n| x | y |\n', '| A | B |\n| --- | --- |\n| x | |\n')).toBe(false);
    expect(blockSuiteMarkdownMatches('```text\nline  \n\n\n```\n', '```text\nline\n\n```\n')).toBe(false);
    expect(blockSuiteMarkdownMatches('Plain Markdown\n\n', 'Plain Markdown changed')).toBe(false);
    expect(blockSuiteMarkdownMatches('Body  \n', 'Body\n')).toBe(false);
    expect(blockSuiteMarkdownMatches('[[Obsidian]]\n', '')).toBe(false);
    expect(blockSuiteMarkdownMatches('Heading\n---\n', '# Heading\n')).toBe(false);
    expect(blockSuiteMarkdownMatches('Heading\n---\n', 'Heading\n---\n')).toBe(false);
    expect(blockSuiteMarkdownMatches('> [!NOTE]\n> keep as callout\n', '> keep as callout\n')).toBe(false);
    expect(blockSuiteMarkdownMatches('> [!NOTE]\n> keep as callout\n', '> [!NOTE]\n> keep as callout\n')).toBe(false);
    expect(blockSuiteMarkdownMatches('> > [!NOTE]\n> > keep as nested callout\n', '> > keep as nested callout\n')).toBe(false);
    expect(blockSuiteMarkdownMatches('>> [!NOTE]\n>> keep as compact nested callout\n', '>> keep as compact nested callout\n')).toBe(false);
  });

  it('rejects unsupported source syntax from later editor projections before save', () => {
    expect(blockSuiteMarkdownSupportsEditing('A Setext title\n===\n')).toBe(false);
    expect(blockSuiteMarkdownSupportsEditing('> [!WARNING]\n> Keep the callout\n')).toBe(false);
    expect(blockSuiteMarkdownSupportsEditing('A supported paragraph\n\n# A supported heading\n')).toBe(true);
  });
});
