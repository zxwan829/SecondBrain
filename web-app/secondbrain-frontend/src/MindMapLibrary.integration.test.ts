import MindMap from 'simple-mind-map';
import { describe, expect, it } from 'vitest';

describe('SimpleMindMap persisted config contract', () => {
  it('uses the installed library getData(true) envelope with root, layout, theme and view', () => {
    const tree = { data: { text: 'Root' }, children: [
      { data: { text: 'Branch B' }, children: [{ data: { text: 'Nested child' }, children: [] }] },
      { data: { text: 'Branch A' }, children: [] },
    ] };
    const getData = MindMap.prototype.getData as (this: unknown, withConfig: boolean) => unknown;
    const instance = {
      command: { getCopyData: () => tree },
      getLayout: () => 'mindMap',
      getTheme: () => 'default',
      getCustomThemeConfig: () => ({}),
      view: { getTransformData: () => ({ scale: 1, x: 12, y: 24 }) },
    };

    const persisted = JSON.parse(JSON.stringify(getData.call(instance, true))) as {
      root: typeof tree; layout: string; theme: { template: string }; view: unknown;
    };
    expect(persisted).toEqual({ layout: 'mindMap', root: tree, theme: { template: 'default', config: {} }, view: { scale: 1, x: 12, y: 24 } });
    // This is the exact persisted envelope consumed by MindMapEditor. The
    // root tree proves both parent assignment and sibling ordering survive.
    const reopenedRoot = persisted.root;
    expect(reopenedRoot.children.map((node) => node.data.text)).toEqual(['Branch B', 'Branch A']);
    expect(reopenedRoot.children[0].children[0].data.text).toBe('Nested child');
  });
});
