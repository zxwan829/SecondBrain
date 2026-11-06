import { describe, expect, it } from 'vitest';
import { createBlockSuiteResourcePayload, restoreBlockSuiteResourceSnapshot } from './BlockSuiteResourceEditor';

function stableShape(snapshot: Record<string, unknown>) {
  const json = JSON.stringify(snapshot);
  return {
    flavours: [...json.matchAll(/"flavour":"([^"]+)"/g)].map((match) => match[1]).sort(),
    textMarkers: ['测试数据库', '测试记录', '可编辑测试画布', '独立 Edgeless 便签'].filter((marker) => json.includes(marker)),
  };
}

describe('note-bound BlockSuite Yjs resource snapshots', () => {
  it.each([
    { kind: 'database' as const, requiredFlavour: 'affine:database', requiredText: '测试记录' },
    { kind: 'edgeless-canvas' as const, requiredFlavour: 'affine:edgeless-text', requiredText: '独立 Edgeless 便签' },
  ])('restores $kind from the persisted Yjs update into a BlockSuite Store', ({ kind, requiredFlavour, requiredText }) => {
    const resource = createBlockSuiteResourcePayload(kind);
    const restored = restoreBlockSuiteResourceSnapshot(resource);
    const originalShape = stableShape(resource.snapshot);
    const restoredShape = stableShape(restored);

    expect(originalShape.flavours).toContain(requiredFlavour);
    expect(restoredShape.flavours).toContain(requiredFlavour);
    expect(originalShape.textMarkers).toEqual(restoredShape.textMarkers);
    expect(JSON.stringify(restored)).toContain(requiredText);
  });
});
