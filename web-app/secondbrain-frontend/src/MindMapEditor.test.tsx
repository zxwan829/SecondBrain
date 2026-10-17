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
} }));
vi.mock('simple-mind-map', () => ({
  default: class {
    handlers: Record<string, () => void> = {};
    tree: unknown = { data: { text: 'Root' }, children: [] };
    execCommand = vi.fn();
    destroy = vi.fn();
    constructor() { fake.instance = this; }
    on(name: string, callback: () => void) { this.handlers[name] = callback; }
    off(name: string) { delete this.handlers[name]; }
    getData() { return this.tree; }
  },
}));
import { MindMapEditor } from './MindMapEditor';

afterEach(() => { cleanup(); fake.instance = null; });

describe('MindMapEditor', () => {
  it('persists the reordered tree after the native drag-end event and exposes history commands', async () => {
    const onChange = vi.fn();
    const { unmount } = render(<MindMapEditor content={'{"data":{"text":"Root"},"children":[]}'} onChange={onChange} />);
    await waitFor(() => expect(fake.instance).not.toBeNull());
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
});
