import { describe, expect, it } from 'vitest';
// @ts-ignore Node built-ins are available to Vitest's test worker.
import { readFileSync } from 'fs';

const css = readFileSync('src/styles/app.css', 'utf8');

describe('Calendar responsive layout contract', () => {
  it('lets the calendar flex item shrink within the workspace content width', () => {
    expect(css).toMatch(/\.calendar-page\s*\{[^}]*min-width:\s*0\s*;?[^}]*\}/s);
  });
});
