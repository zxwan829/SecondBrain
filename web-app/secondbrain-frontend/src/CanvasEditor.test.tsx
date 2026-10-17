import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const fake = vi.hoisted(() => ({ initialData: null as unknown, change: null as null | ((elements: unknown[], appState: unknown, files: unknown) => void) }));
vi.mock('@excalidraw/excalidraw', () => ({
  Excalidraw: ({ initialData, onChange }: { initialData: unknown; onChange: (elements: unknown[], appState: unknown, files: unknown) => void }) => {
    fake.initialData = initialData; fake.change = onChange;
    return <button onClick={() => onChange([{ type: 'arrow', id: 'a1' }, { type: 'text', id: 't1', text: 'Diagram' }], { viewBackgroundColor: '#fff' }, {})}>合成场景编辑</button>;
  },
  serializeAsJSON: (elements: unknown[], appState: unknown, files: unknown, type: string) => JSON.stringify({ type: 'excalidraw', elements, appState, files, exportType: type }),
}));
import { CanvasEditor } from './CanvasEditor';

afterEach(() => { cleanup(); fake.change = null; fake.initialData = null; });

describe('CanvasEditor', () => {
  it('restores saved scene data and serializes editable arrows and text', () => {
    const source = JSON.stringify({ type: 'excalidraw', elements: [{ type: 'rectangle', id: 'saved' }], appState: { viewBackgroundColor: '#fff' } });
    const onChange = vi.fn();
    render(<CanvasEditor content={source} onChange={onChange} />);
    expect(fake.initialData).toEqual(JSON.parse(source));
    fireEvent.click(screen.getByRole('button', { name: '合成场景编辑' }));
    expect(JSON.parse(onChange.mock.calls[0][0])).toMatchObject({ type: 'excalidraw', elements: [{ type: 'arrow' }, { type: 'text', text: 'Diagram' }], exportType: 'database' });
  });
});
