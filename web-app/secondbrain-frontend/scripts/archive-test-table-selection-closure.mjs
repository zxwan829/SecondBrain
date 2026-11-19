import assert from 'node:assert/strict';
import { expandTableAreaToMergeClosure } from '../src/table-commands.ts';

const rows = ['r0', 'r1', 'r2', 'r3'];
const columns = ['c0', 'c1', 'c2', 'c3', 'c4'];
const area = (rowStartIndex, rowEndIndex, columnStartIndex, columnEndIndex) => ({
  type: 'area', rowStartIndex, rowEndIndex, columnStartIndex, columnEndIndex,
});
const merged = { first: { rowIds: ['r0', 'r1'], columnIds: ['c0', 'c1'] } };

// Selecting the merged 2x2 region and its two right neighbors stays exact.
assert.deepEqual(
  expandTableAreaToMergeClosure(area(0, 1, 0, 3), rows, columns, merged),
  area(0, 1, 0, 3)
);
// A range starting from a covered slot expands only to the merged region's edge.
assert.deepEqual(
  expandTableAreaToMergeClosure(area(1, 1, 1, 3), rows, columns, merged),
  area(0, 1, 0, 3)
);
// Reverse drag direction receives the same closed range.
assert.deepEqual(
  expandTableAreaToMergeClosure(area(0, 0, 0, 3), rows, columns, merged),
  area(0, 1, 0, 3)
);
// A merge immediately outside the closed region is not pulled in.
assert.deepEqual(
  expandTableAreaToMergeClosure(area(0, 0, 0, 0), rows, columns, {
    ...merged,
    adjacent: { rowIds: ['r0', 'r1'], columnIds: ['c2', 'c3'] },
  }),
  area(0, 1, 0, 1)
);
// Unrelated regions and malformed/stale IDs do not inflate the range.
assert.deepEqual(
  expandTableAreaToMergeClosure(area(3, 3, 4, 4), rows, columns, {
    ...merged,
    stale: { rowIds: ['missing', 'r2'], columnIds: ['c3', 'c4'] },
  }),
  area(3, 3, 4, 4)
);

console.log('PASS · merged-area selection closure remains exact in both drag directions and excludes unrelated/stale regions');
