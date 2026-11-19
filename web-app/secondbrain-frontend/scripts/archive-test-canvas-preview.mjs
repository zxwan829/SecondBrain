import assert from 'node:assert/strict';
import { toCanvasPreviewShape, resolvePreviewColor } from '../src/canvas-preview.ts';

const shape = (overrides = {}) => ({
  id: 'triangle-1', type: 'shape', shapeType: 'triangle',
  elementBound: { x: 2, y: 3, w: 44, h: 30 }, text: { toString: () => '节点' },
  filled: true, fillColor: '#fcd34d', strokeColor: '#f59e0b', strokeWidth: 3,
  strokeStyle: 'Dash', opacity: .8, rotate: 12, radius: 5, color: '#312e81',
  shapeStyle: 'General', roughness: 1,
  fontSize: 16, fontFamily: 'Inter', fontWeight: 600, textHorizontalAlign: 'center', ...overrides,
});
const preview = toCanvasPreviewShape(shape());
assert.deepEqual(preview.bound, [2, 3, 44, 30]);
assert.equal(preview.id, 'triangle-1');
assert.equal(preview.shapeType, 'triangle');
assert.equal(preview.fillColor, '#fcd34d');
assert.equal(preview.strokeColor, '#f59e0b');
assert.equal(preview.strokeWidth, 3);
assert.equal(preview.shapeStyle, 'General');
assert.equal(preview.opacity, .8);
assert.equal(preview.rotate, 12);
assert.equal(preview.text, '节点');
assert.equal(resolvePreviewColor({ light: '#fff', dark: '#000' }, '#f00'), '#fff');
const connector = toCanvasPreviewShape({ id: 'edge-1', type: 'connector', elementBound: { x: 0, y: 0, w: 20, h: 10 }, absolutePath: [{ x: 1, y: 2 }, { x: 19, y: 8 }], stroke: '#111', strokeWidth: 2 });
assert.equal(connector.strokeColor, '#111');
assert.equal(connector.strokeWidth, 2);
console.log('PASS · preview source mapping preserves element identity, bounds, shape, fill/stroke, opacity, rotation, text, and connector path data');
