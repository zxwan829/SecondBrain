import assert from 'node:assert/strict';
import { canMergeTableRectangle, reconcileTableMergeRegions } from '../src/table-merge-invariants.ts';

const region = (rowIds, columnIds) => ({
  version: 1,
  id: 'm1',
  anchorRowId: rowIds[0],
  anchorColumnId: columnIds[0],
  rowIds,
  columnIds,
});
const area = (rowStartIndex, rowEndIndex, columnStartIndex, columnEndIndex) => ({
  type: 'area', rowStartIndex, rowEndIndex, columnStartIndex, columnEndIndex,
});
const rows3 = ['r0', 'r1', 'r2'];
const cols3 = ['c0', 'c1', 'c2'];

// The user-reported case: delete a row from an ordinary grid, then merge a new legal rectangle.
assert.equal(canMergeTableRectangle(['r0', 'r2'], cols3, area(0, 1, 0, 1), {}), true);

// A merge spanning the deleted row shrinks to the remaining adjacent rows and reanchors.
const afterMiddleRowDelete = reconcileTableMergeRegions(
  { m1: region(rows3, ['c0', 'c1']) },
  ['r0', 'r2'],
  cols3
);
assert.deepEqual(afterMiddleRowDelete.m1, region(['r0', 'r2'], ['c0', 'c1']));
assert.equal(canMergeTableRectangle(['r0', 'r2'], cols3, area(0, 1, 0, 1), afterMiddleRowDelete), true);

// Deleting the anchor row/column promotes the next surviving IDs. A one-cell remainder dissolves.
assert.deepEqual(
  reconcileTableMergeRegions({ m1: region(['r0', 'r1'], ['c0', 'c1']) }, ['r1'], ['c0', 'c1']),
  { m1: region(['r1'], ['c0', 'c1']) }
);
assert.deepEqual(
  reconcileTableMergeRegions({ m1: region(['r0', 'r1'], ['c0', 'c1']) }, ['r0'], ['c0']),
  {}
);

// Inserting between merged members extends that region; appending outside does not.
assert.deepEqual(
  reconcileTableMergeRegions({ m1: region(['r0', 'r2'], ['c0', 'c1']) }, ['r0', 'r1', 'r2'], cols3, { insertedRowId: 'r1' }).m1.rowIds,
  ['r0', 'r1', 'r2']
);
assert.deepEqual(
  reconcileTableMergeRegions({ m1: region(['r0', 'r1'], ['c0', 'c1']) }, ['r0', 'r1', 'r2'], cols3, { insertedRowId: 'r2' }).m1.rowIds,
  ['r0', 'r1']
);

// Row/column reorder that breaks rectangular contiguity dissolves only metadata, not cell payloads.
assert.deepEqual(
  reconcileTableMergeRegions({ m1: region(['r0', 'r1'], ['c0', 'c1']) }, ['r0', 'r2', 'r1'], cols3),
  {}
);

// Malformed/stale IDs do not block a disjoint merge; malformed and overlapping records remain fail-closed.
const stale = { stale: region(['gone', 'r0'], ['c0', 'c1']) };
assert.equal(canMergeTableRectangle(rows3, cols3, area(1, 2, 1, 2), stale), true);
assert.equal(canMergeTableRectangle(rows3, cols3, area(0, 1, 0, 0), { m1: region(['r0', 'r1'], ['c0', 'c1']) }), false);
assert.equal(canMergeTableRectangle(rows3, cols3, area(0, 1, 0, 2), { m1: region(['r0', 'r1'], ['c0', 'c1']) }), true);
assert.deepEqual(reconcileTableMergeRegions({ duplicate: region(['r0', 'r0'], ['c0', 'c1']) }, rows3, cols3), {});

console.log('PASS · structural merge lifecycle: delete/reanchor/dissolve, insert expansion, reorder normalization, stale region isolation, and legal merge availability');
