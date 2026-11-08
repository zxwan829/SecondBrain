import { describe, expect, it } from 'vitest';
import { sameBlockSuiteSnapshot } from './resource-snapshot-equality';

describe('BlockSuite snapshot equality', () => {
  it('ignores object key order while preserving array order and content changes', () => {
    expect(sameBlockSuiteSnapshot(
      { blocks: [{ props: { width: 320, sourceId: 'blob' } }], meta: { id: 'doc' } },
      { meta: { id: 'doc' }, blocks: [{ props: { sourceId: 'blob', width: 320 } }] },
    )).toBe(true);
    expect(sameBlockSuiteSnapshot({ blocks: ['a', 'b'] }, { blocks: ['b', 'a'] })).toBe(false);
    expect(sameBlockSuiteSnapshot({ blocks: [{ width: 320 }] }, { blocks: [{ width: 321 }] })).toBe(false);
  });
});
