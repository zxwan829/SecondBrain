import MindMap from 'simple-mind-map';
import { describe, expect, it } from 'vitest';

Object.defineProperty(SVGElement.prototype, 'getBBox', {
  configurable: true,
  value: () => ({ x: 0, y: 0, width: 120, height: 24 }),
});
Object.defineProperty(SVGElement.prototype, 'getBoundingClientRect', {
  configurable: true,
  value: () => ({ width: 120, height: 24, top: 0, left: 0, right: 120, bottom: 24, x: 0, y: 0, toJSON: () => ({}) }),
});

describe('SimpleMindMap persisted config contract', () => {
  it.each([
    { data: { text: 'Root' }, children: [] },
    { data: { text: 'Legacy Root' }, children: [{ data: { text: 'Child' }, children: [] }] },
  ])('initializes and reopens a real tree with library defaults when theme config is absent', async (root) => {
    const element = document.createElement('div');
    element.getBoundingClientRect = () => ({ width: 800, height: 600, top: 0, left: 0, right: 800, bottom: 600, x: 0, y: 0, toJSON: () => ({}) });
    document.body.append(element);
    const instance = new MindMap({ el: element, data: root, fit: true });
    await new Promise((resolve) => setTimeout(resolve, 25));
    const persisted = JSON.parse(JSON.stringify((MindMap.prototype.getData as (this: unknown, withConfig: boolean) => unknown).call(instance, true))) as {
      root: typeof root; layout: string; theme: { template: string; config: Record<string, unknown> };
    };
    type Tree = { data: { text: string }; children: Tree[] };
    const getTexts = (node: Tree): string[] => [node.data.text, ...node.children.flatMap(getTexts)];
    instance.destroy();
    element.remove();

    const reopenedElement = document.createElement('div');
    reopenedElement.getBoundingClientRect = element.getBoundingClientRect;
    document.body.append(reopenedElement);
    const reopened = new MindMap({
      el: reopenedElement,
      data: persisted.root,
      layout: persisted.layout,
      theme: persisted.theme.template,
      themeConfig: persisted.theme.config,
      fit: true,
    });
    await new Promise((resolve) => setTimeout(resolve, 25));
    const reopenedData = JSON.parse(JSON.stringify((MindMap.prototype.getData as (this: unknown, withConfig: boolean) => unknown).call(reopened, true))) as { root: Tree };
    expect(getTexts(reopenedData.root)).toEqual(getTexts(persisted.root));
    reopened.destroy();
    reopenedElement.remove();
  });

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
