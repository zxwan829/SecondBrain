import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const fake = vi.hoisted(() => ({ instance: null as null | {
  handlers: Record<string, () => void>;
  tree: unknown;
  on: (name: string, callback: () => void) => void;
  off: (name: string) => void;
  getData: () => unknown;
  execCommand: ReturnType<typeof vi.fn>;
  destroy: ReturnType<typeof vi.fn>;
}, options: undefined as undefined | Record<string, unknown>, viewTransform: undefined as unknown, registerPlugin: vi.fn() }));
vi.mock('simple-mind-map', () => ({
  default: class {
    static usePlugin = fake.registerPlugin;
    handlers: Record<string, () => void> = {};
    tree: unknown = { data: { text: 'Root' }, children: [] };
    execCommand = vi.fn();
    destroy = vi.fn();
    view = { setTransformData: (data: unknown) => { fake.viewTransform = data; } };
    constructor(options: Record<string, unknown>) { fake.instance = this; fake.options = options; }
    on(name: string, callback: () => void) { this.handlers[name] = callback; }
    off(name: string) { delete this.handlers[name]; }
    getData() { return this.tree; }
  },
}));
vi.mock('simple-mind-map/src/plugins/Drag.js', () => ({ default: { name: 'SyntheticDragPlugin' } }));
import { MindMapEditor } from './MindMapEditor';

afterEach(() => { cleanup(); fake.instance = null; fake.options = undefined; fake.viewTransform = undefined; fake.registerPlugin.mockClear(); });

describe('MindMapEditor', () => {
  it('persists the reordered tree after the native drag-end event and exposes history commands', async () => {
    const onChange = vi.fn();
    const { unmount } = render(<MindMapEditor content={'{"data":{"text":"Root"},"children":[]}'} onChange={onChange} />);
    await waitFor(() => expect(fake.instance).not.toBeNull());
    expect(fake.registerPlugin).toHaveBeenCalled();
    const moved = { data: { text: 'Root' }, children: [
      { data: { text: 'Branch B' }, children: [{ data: { text: 'Child' }, children: [] }] },
      { data: { text: 'Branch A' }, children: [] },
    ] };
    fake.instance!.tree = moved;
    fake.instance!.handlers.node_dragend();
    expect(JSON.parse(onChange.mock.calls[0][0])).toEqual(moved);
    fireEvent.click(screen.getByRole('button', { name: '添加子节点' }));
    fireEvent.click(screen.getByRole('button', { name: '撤销' }));
    fireEvent.click(screen.getByRole('button', { name: '重做' }));
    expect(fake.instance!.execCommand.mock.calls).toEqual([['INSERT_CHILD_NODE'], ['BACK'], ['FORWARD']]);
    const instance = fake.instance!;
    unmount();
    expect(instance.destroy).toHaveBeenCalled();
    expect(instance.handlers).toEqual({});
  });

  it('opens the real-library persisted config shape using its root tree and layout', async () => {
    const root = { data: { text: 'Root' }, children: [{ data: { text: 'Branch' }, children: [] }] };
    const persisted = { layout: 'logicalStructure', root, theme: { template: 'default', config: { lineWidth: 3 } }, view: { scale: 1, x: 10, y: 20 } };
    render(<MindMapEditor content={JSON.stringify(persisted)} onChange={vi.fn()} />);
    await waitFor(() => expect(fake.options).toBeDefined());
    expect(fake.options).toMatchObject({ data: root, layout: 'logicalStructure', theme: 'default', themeConfig: { lineWidth: 3 } });
    expect(fake.viewTransform).toEqual(persisted.view);
  });
});
