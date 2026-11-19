import type { TableArea } from './table-commands';

export type StableMergeRegion = {
  version: 1;
  id: string;
  anchorRowId: string;
  anchorColumnId: string;
  rowIds: string[];
  columnIds: string[];
};

type ReconcileOptions = { insertedRowId?: string; insertedColumnId?: string };

function isContiguous(ids: string[], axis: string[]) {
  if (!ids.length || new Set(ids).size !== ids.length) return false;
  const indices = ids.map(id => axis.indexOf(id));
  return indices.every(index => index >= 0) && indices.every((index, i) => i === 0 || index === indices[i - 1] + 1);
}

function orderedMembers(input: unknown, axis: string[]) {
  if (!Array.isArray(input) || input.some(id => typeof id !== 'string')) return [];
  if (new Set(input as string[]).size !== input.length) return [];
  const members = new Set(input as string[]);
  return axis.filter(id => members.has(id));
}

/**
 * Reconcile merge metadata against stable live row/column IDs after a table
 * structural edit. Invalid/non-rectangular metadata is dropped, which reveals
 * the original per-cell payloads instead of hiding or deleting them.
 */
export function reconcileTableMergeRegions(
  regions: Record<string, unknown>,
  rowIds: string[],
  columnIds: string[],
  options: ReconcileOptions = {}
): Record<string, StableMergeRegion> {
  if (new Set(rowIds).size !== rowIds.length || new Set(columnIds).size !== columnIds.length) return {};
  const result: Record<string, StableMergeRegion> = {};
  for (const [key, value] of Object.entries(regions)) {
    if (!value || typeof value !== 'object') continue;
    const region = value as Partial<StableMergeRegion>;
    let rows = orderedMembers(region.rowIds, rowIds);
    let columns = orderedMembers(region.columnIds, columnIds);

    if (options.insertedRowId && rowIds.includes(options.insertedRowId)) {
      const index = rowIds.indexOf(options.insertedRowId);
      if (index > 0 && index < rowIds.length - 1 && rows.includes(rowIds[index - 1]!) && rows.includes(rowIds[index + 1]!)) {
        rows = orderedMembers([...rows, options.insertedRowId], rowIds);
      }
    }
    if (options.insertedColumnId && columnIds.includes(options.insertedColumnId)) {
      const index = columnIds.indexOf(options.insertedColumnId);
      if (index > 0 && index < columnIds.length - 1 && columns.includes(columnIds[index - 1]!) && columns.includes(columnIds[index + 1]!)) {
        columns = orderedMembers([...columns, options.insertedColumnId], columnIds);
      }
    }

    if (rows.length * columns.length < 2 || !isContiguous(rows, rowIds) || !isContiguous(columns, columnIds)) continue;
    const id = typeof region.id === 'string' ? region.id : key;
    result[key] = { version: 1, id, rowIds: rows, columnIds: columns, anchorRowId: rows[0]!, anchorColumnId: columns[0]! };
  }
  return result;
}

/** Validate mergeability without allowing a stale unrelated region to poison the whole table. */
export function canMergeTableRectangle(
  rowIds: string[],
  columnIds: string[],
  area: TableArea,
  regions: Record<string, unknown>
) {
  const { rowStartIndex: r0, rowEndIndex: r1, columnStartIndex: c0, columnEndIndex: c1 } = area;
  if (![r0, r1, c0, c1].every(Number.isInteger) || r0 < 0 || c0 < 0 || r1 >= rowIds.length || c1 >= columnIds.length || r0 > r1 || c0 > c1 || (r0 === r1 && c0 === c1)) return false;
  const selected = new Set<string>();
  for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) selected.add(`${rowIds[r]}:${columnIds[c]}`);
  const valid = reconcileTableMergeRegions(regions, rowIds, columnIds);
  for (const region of Object.values(valid)) {
    const cells = region.rowIds.flatMap(row => region.columnIds.map(column => `${row}:${column}`));
    const overlap = cells.filter(cell => selected.has(cell)).length;
    if (overlap > 0 && overlap !== cells.length) return false;
  }
  return true;
}
