import assert from 'node:assert/strict';
import { tableSelectionToArea } from '../src/table-commands.ts';

const rows = ['r1', 'r2', 'r3'];
const columns = ['c1', 'c2', 'c3', 'c4'];
assert.deepEqual(tableSelectionToArea({ type: 'row', rowId: 'r2' }, rows, columns), {
  type: 'area', rowStartIndex: 1, rowEndIndex: 1, columnStartIndex: 0, columnEndIndex: 3,
});
assert.deepEqual(tableSelectionToArea({ type: 'column', columnId: 'c3' }, rows, columns), {
  type: 'area', rowStartIndex: 0, rowEndIndex: 2, columnStartIndex: 2, columnEndIndex: 2,
});
assert.deepEqual(tableSelectionToArea({ type: 'area', rowStartIndex: 1, rowEndIndex: 2, columnStartIndex: 1, columnEndIndex: 3 }, rows, columns), {
  type: 'area', rowStartIndex: 1, rowEndIndex: 2, columnStartIndex: 1, columnEndIndex: 3,
});
assert.equal(tableSelectionToArea({ type: 'row', rowId: 'removed' }, rows, columns), undefined);
assert.equal(tableSelectionToArea({ type: 'area', rowStartIndex: 0, rowEndIndex: 5, columnStartIndex: 0, columnEndIndex: 1 }, rows, columns), undefined);
console.log('PASS: row, column, area, stale ID, and out-of-bounds selection normalization');
