import { describe, expect, it } from 'vitest';
// @ts-ignore Node built-ins are available to Vitest's test worker.
import { readFileSync } from 'fs';

const css = readFileSync('src/styles/app.css', 'utf8');

describe('Review responsive layout contract', () => {
  it('keeps proportional desktop columns, independent scroll panes, and protects the grid from long content', () => {
    expect(css).toMatch(/\.review-page-grid\s*\{[^}]*grid-template-columns:\s*minmax\(240px,\s*0\.36fr\)\s+minmax\(0,\s*0\.64fr\)/s);
    expect(css).toMatch(/\.review-page-list\s*\{[^}]*overflow:\s*auto/s);
    expect(css).toMatch(/\.review-page-detail\s*\{[^}]*overflow:\s*auto[^}]*overflow-wrap:\s*anywhere/s);
    expect(css).toMatch(/\.review-page-grid\s*\{[^}]*min-height:\s*0/s);
    expect(css).toMatch(/\.review-page-detail\s*\{[^}]*min-height:\s*0/s);
  });

  it('switches to the detail-first mobile layout without imposing double-pane scrolling', () => {
    expect(css).toMatch(/@media\s*\(max-width:\s*760px\)\s*\{[\s\S]*?\.review-page-grid\s*\{\s*display:\s*flex;\s*flex-direction:\s*column/s);
    expect(css).toMatch(/\.review-page-list\.is-mobile-collapsed\s*\{\s*display:\s*none\s*;?\s*\}/);
    expect(css).toMatch(/\.review-page-detail\s*\{\s*order:\s*1;\s*min-height:\s*45dvh;\s*overflow:\s*visible\s*;?\s*\}/);
  });
});
