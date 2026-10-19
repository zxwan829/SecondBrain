import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import MindMap from 'simple-mind-map';
import { MindMapEditor } from './MindMapEditor';
import { defaultMindMap } from './visualAssets';

Object.defineProperty(HTMLElement.prototype, 'getBoundingClientRect', {
  configurable: true,
  value() { return { width: 800, height: 600, top: 0, left: 0, right: 800, bottom: 600, x: 0, y: 0, toJSON: () => ({}) }; },
});
Object.defineProperty(SVGElement.prototype, 'getBBox', {
  configurable: true,
  value: () => ({ x: 0, y: 0, width: 120, height: 24 }),
});
Object.defineProperty(SVGElement.prototype, 'getBoundingClientRect', {
  configurable: true,
  value: () => ({ width: 120, height: 24, top: 0, left: 0, right: 120, bottom: 24, x: 0, y: 0, toJSON: () => ({}) }),
});

afterEach(() => cleanup());

describe('MindMapEditor with the installed SimpleMindMap library', () => {
  it.each([
    defaultMindMap(),
    JSON.stringify({
      layout: 'logicalStructure',
      root: { data: { text: 'Legacy root' }, children: [{ data: { text: 'Child' }, children: [] }] },
      theme: { template: 'default', config: null },
      view: { transform: {} },
    }),
  ])('opens actual stored content without an initialization alert', async (content) => {
    const destroy = vi.spyOn(MindMap.prototype, 'destroy');
    const { container, unmount } = render(<MindMapEditor content={content} onChange={vi.fn()} />);

    await waitFor(() => expect(container.querySelector('.mind-map-canvas svg')).not.toBeNull());
    expect(screen.queryByRole('alert')).toBeNull();
    await new Promise((resolve) => setTimeout(resolve, 25));

    unmount();
    expect(destroy).toHaveBeenCalledTimes(1);
    destroy.mockRestore();
  });
});
