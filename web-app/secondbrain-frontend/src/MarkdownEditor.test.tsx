import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MarkdownEditor } from './MarkdownEditor';

describe('MarkdownEditor', () => {
  it('opens ordinary Markdown structure without dropping its main blocks', async () => {
    const onChange = vi.fn();
    const { container } = render(<MarkdownEditor value={'# Heading\n\n**bold text**\n\n- first\n- second\n\n> quote\n\n[link](https://example.com)\n\n| Name | Value |\n| --- | --- |\n| one | 1 |\n'} disabled={false} onChange={onChange} />);
    await screen.findByRole('heading', { level: 1, name: 'Heading' });
    expect(screen.getByText('bold text').tagName).toBe('STRONG');
    expect(screen.getByRole('list').textContent).toContain('first');
    expect(container.querySelector('blockquote')?.textContent).toContain('quote');
    expect(container.querySelector('a[href="https://example.com"]')?.textContent).toBe('link');
    expect(container.querySelector('table')?.textContent).toContain('Name');
    await waitFor(() => expect(onChange).not.toHaveBeenCalled());
  });
});
