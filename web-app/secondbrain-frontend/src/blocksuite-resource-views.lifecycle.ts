import { describe, expect, it } from 'vitest';
import { markdownViewManager, resourceViewManager } from './blocksuite-resource-views';

describe('BlockSuite shared view lifecycle', () => {
  it('can alternate page and edgeless scopes without registering elements again', () => {
    expect(resourceViewManager).toBe(markdownViewManager);
    expect(markdownViewManager.get('page').length).toBeGreaterThan(0);
    expect(resourceViewManager.get('edgeless').length).toBeGreaterThan(0);
    expect(markdownViewManager.get('page').length).toBeGreaterThan(0);
  });
});
