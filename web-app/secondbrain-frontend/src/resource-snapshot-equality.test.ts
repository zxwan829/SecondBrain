import { describe, expect, it } from 'vitest';
import { sameBlockSuiteSnapshot, sameBlockSuiteSnapshotExceptEdgelessNoteFrames } from './resource-snapshot-equality';

describe('BlockSuite snapshot equality', () => {
  it('ignores object key order while preserving array order and content changes', () => {
    expect(sameBlockSuiteSnapshot(
      { blocks: [{ props: { width: 320, sourceId: 'blob' } }], meta: { id: 'doc' } },
      { meta: { id: 'doc' }, blocks: [{ props: { sourceId: 'blob', width: 320 } }] },
    )).toBe(true);
    expect(sameBlockSuiteSnapshot({ blocks: ['a', 'b'] }, { blocks: ['b', 'a'] })).toBe(false);
    expect(sameBlockSuiteSnapshot({ blocks: [{ width: 320 }] }, { blocks: [{ width: 321 }] })).toBe(false);
  });

  it('ignores only Edgeless note frame geometry during hydration comparison', () => {
    const saved = { blocks: { children: [{ flavour: 'affine:note', props: { xywh: '[0,0,498,92]', title: 'note' } }] } };
    const hydrated = { blocks: { children: [{ flavour: 'affine:note', props: { xywh: '[0,0,498,124]', title: 'note' } }] } };
    expect(sameBlockSuiteSnapshotExceptEdgelessNoteFrames(saved, hydrated)).toBe(true);
    expect(sameBlockSuiteSnapshotExceptEdgelessNoteFrames(saved,
      { blocks: { children: [{ flavour: 'affine:note', props: { xywh: '[0,0,498,124]', title: 'edited' } }] } })).toBe(false);
    expect(sameBlockSuiteSnapshotExceptEdgelessNoteFrames(saved,
      { blocks: { children: [{ flavour: 'affine:paragraph', props: { xywh: '[0,0,498,124]', title: 'note' } }] } })).toBe(false);
  });
});
