import React from 'react';
import { describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { parseReviewDocument, ReviewMarkdown } from './ReviewMarkdown';

describe('safe Review Markdown rendering', () => {
  it('removes YAML frontmatter from the body and exposes metadata separately', () => {
    const document = parseReviewDocument('---\ntype: "review"\nsource_type: "pdf"\ncaptured_at: "2026-10-15T08:00:00Z"\n---\n# Title\n\nBody');
    expect(document.metadata.source_type).toBe('pdf');
    expect(document.metadata.captured_at).toBe('2026-10-15T08:00:00Z');
    expect(document.body).toBe('# Title\n\nBody');
    const { container } = render(<ReviewMarkdown source={document.body} />);
    expect(screen.getByRole('heading', { name: 'Title' })).toBeTruthy();
    expect(container.textContent).not.toContain('source_type:');
    cleanup();
  });

  it('renders Markdown blocks as React text without executing HTML or unsafe links', () => {
    const { container } = render(<ReviewMarkdown source={'<script>window.bad = true</script>\n\n[unsafe](javascript:alert(1))\n\n```ini\nkey = value\nnext: true\n```'} />);
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
    expect(container.textContent).toContain('<script>window.bad = true</script>');
    expect(container.textContent).toContain('key = value\nnext: true');
  });

  it('preserves OCR line order and spacing verbatim', () => {
    const ocr = '第一行：A-01\nkey: value\n第三行  末尾';
    const { container } = render(<ReviewMarkdown source={ocr} preserveLines />);
    expect(container.querySelector('pre')?.textContent).toBe(ocr);
  });
});
