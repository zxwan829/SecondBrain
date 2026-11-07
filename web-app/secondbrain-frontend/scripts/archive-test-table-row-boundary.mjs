import assert from 'node:assert/strict';
import { visibleRowBoundaryIndex } from '../src/table-row-boundary.ts';

// A two-row merge occupies y=100..200. Its former inner line at y=150 is inert.
assert.equal(visibleRowBoundaryIndex(200, 150, 0, 2, 3), null);
assert.equal(visibleRowBoundaryIndex(200, 154, 0, 2, 3), null);
assert.equal(visibleRowBoundaryIndex(200, 200, 0, 2, 3), 1);
assert.equal(visibleRowBoundaryIndex(200, 195, 0, 2, 3), 1);
// An adjacent unmerged cell retains its visible inner-row border.
assert.equal(visibleRowBoundaryIndex(150, 150, 0, 1, 3), 0);
assert.equal(visibleRowBoundaryIndex(150, 157, 0, 1, 3), null);
// Three-row spans, non-first anchors, fractional zoom coordinates, invalid spans.
assert.equal(visibleRowBoundaryIndex(340.5, 340.25, 1, 3, 5), 3);
assert.equal(visibleRowBoundaryIndex(340.5, 250, 1, 3, 5), null);
assert.equal(visibleRowBoundaryIndex(200, 200, 2, 2, 3), null);
assert.equal(visibleRowBoundaryIndex(200, 200, -1, 1, 3), null);
assert.equal(visibleRowBoundaryIndex(200, 200, 0, 0, 3), null);
console.log('PASS · hidden merged-row lines are inert; visible merged edges target the last covered row; adjacent normal edges remain resizable');
