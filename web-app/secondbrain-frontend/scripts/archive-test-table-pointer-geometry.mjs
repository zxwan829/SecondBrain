import assert from 'node:assert/strict';
import { weightedCellOffset } from '../src/table-pointer-geometry.ts';
import { expandTableAreaToMergeClosure } from '../src/table-commands.ts';

assert.equal(weightedCellOffset(70, 140, [100, 40]), 0);
assert.equal(weightedCellOffset(105, 140, [100, 40]), 1);
assert.equal(weightedCellOffset(150, 140, [100, 40]), 1);
assert.equal(weightedCellOffset(-20, 140, [100, 40]), 0);
assert.equal(weightedCellOffset(199, 320, [120, 200]), 1);
assert.equal(weightedCellOffset(87.5, 175, [100, 40]), 0);
const rows = ['r0','r1','r2'], columns = ['c0','c1','c2'];
const regions = { left: { rowIds:['r0','r1'], columnIds:['c0'] } };
const area = (r0,r1,c0,c1) => ({type:'area',rowStartIndex:r0,rowEndIndex:r1,columnStartIndex:c0,columnEndIndex:c1});
assert.deepEqual(expandTableAreaToMergeClosure(area(0,2,1,1),rows,columns,regions),area(0,2,1,1));
assert.deepEqual(expandTableAreaToMergeClosure(area(0,0,0,2),rows,columns,regions),area(0,1,0,2));
assert.deepEqual(expandTableAreaToMergeClosure(area(1,2,0,1),rows,columns,regions),area(0,2,0,1));
console.log('PASS · rendered merged-cell geometry preserves exact adjacent and intersecting selection ranges');
