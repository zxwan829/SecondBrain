import type { TableBlockModel } from '@blocksuite/affine-model';

export type TableAlignment =
  | { axis: 'horizontal'; value: 'left' | 'center' | 'right' }
  | { axis: 'vertical'; value: 'top' | 'middle' | 'bottom' };

export type TableArea = {
  type: 'area';
  rowStartIndex: number;
  rowEndIndex: number;
  columnStartIndex: number;
  columnEndIndex: number;
};

export type TableSelectionTarget = TableArea | { type: 'row'; rowId: string } | { type: 'column'; columnId: string };

/** Convert native area/row/column selections into one explicit cell rectangle. */
export function tableSelectionToArea(
  selection: TableSelectionTarget | undefined,
  rowIds: string[],
  columnIds: string[]
): TableArea | undefined {
  if (!selection || !rowIds.length || !columnIds.length) return;
  if (selection.type === 'area') {
    const { rowStartIndex, rowEndIndex, columnStartIndex, columnEndIndex } = selection;
    if (rowStartIndex < 0 || columnStartIndex < 0 || rowEndIndex >= rowIds.length || columnEndIndex >= columnIds.length || rowStartIndex > rowEndIndex || columnStartIndex > columnEndIndex) return;
    return selection;
  }
  if (selection.type === 'row') {
    const index = rowIds.indexOf(selection.rowId);
    if (index < 0) return;
    return { type: 'area', rowStartIndex: index, rowEndIndex: index, columnStartIndex: 0, columnEndIndex: columnIds.length - 1 };
  }
  const index = columnIds.indexOf(selection.columnId);
  if (index < 0) return;
  return { type: 'area', rowStartIndex: 0, rowEndIndex: rowIds.length - 1, columnStartIndex: index, columnEndIndex: index };
}

export type TableMergeRegionRef = {
  rowIds?: unknown;
  columnIds?: unknown;
};

/**
 * Expand a pointer selection only as far as needed to include every merged
 * region it touches. A merged cell is one visual selection target, even though
 * the source table retains all of its underlying cells.
 */
export function expandTableAreaToMergeClosure(
  area: TableArea,
  rowIds: string[],
  columnIds: string[],
  regions: Record<string, TableMergeRegionRef> = {}
): TableArea {
  let rowStartIndex = area.rowStartIndex;
  let rowEndIndex = area.rowEndIndex;
  let columnStartIndex = area.columnStartIndex;
  let columnEndIndex = area.columnEndIndex;
  const indexedRegions = Object.values(regions).flatMap(region => {
    if (!Array.isArray(region.rowIds) || !Array.isArray(region.columnIds)) return [];
    const rows = (region.rowIds as unknown[]).map(id => rowIds.indexOf(String(id)));
    const columns = (region.columnIds as unknown[]).map(id => columnIds.indexOf(String(id)));
    if (!rows.length || !columns.length || (rows.length === 1 && columns.length === 1) || rows.some(index => index < 0) || columns.some(index => index < 0)) return [];
    const sortedRows = [...rows].sort((a, b) => a - b);
    const sortedColumns = [...columns].sort((a, b) => a - b);
    if (sortedRows.some((value, index) => index > 0 && value !== sortedRows[index - 1] + 1) || sortedColumns.some((value, index) => index > 0 && value !== sortedColumns[index - 1] + 1)) return [];
    return [{ rowStart: sortedRows[0], rowEnd: sortedRows.at(-1)!, columnStart: sortedColumns[0], columnEnd: sortedColumns.at(-1)! }];
  });

  // Expanding one merge may touch another adjacent merge, so reach a fixed
  // point. The loop is bounded by the number of table rows/columns.
  for (let pass = 0; pass <= rowIds.length + columnIds.length; pass++) {
    const before = `${rowStartIndex}:${rowEndIndex}:${columnStartIndex}:${columnEndIndex}`;
    for (const region of indexedRegions) {
      const intersects = region.rowStart <= rowEndIndex && region.rowEnd >= rowStartIndex && region.columnStart <= columnEndIndex && region.columnEnd >= columnStartIndex;
      if (!intersects) continue;
      rowStartIndex = Math.min(rowStartIndex, region.rowStart);
      rowEndIndex = Math.max(rowEndIndex, region.rowEnd);
      columnStartIndex = Math.min(columnStartIndex, region.columnStart);
      columnEndIndex = Math.max(columnEndIndex, region.columnEnd);
    }
    if (before === `${rowStartIndex}:${rowEndIndex}:${columnStartIndex}:${columnEndIndex}`) break;
  }
  return { ...area, rowStartIndex, rowEndIndex, columnStartIndex, columnEndIndex };
}

/** Apply alignment to the selected cells of the addressed Table model. */
export function applyTableAlignment(
  store: any,
  table: TableBlockModel,
  area: TableArea,
  alignment: TableAlignment
) {
  const rows = Object.values(table.props.rows).sort((a: any, b: any) =>
    a.order.localeCompare(b.order)
  ) as any[];
  const columns = Object.values(table.props.columns).sort((a: any, b: any) =>
    a.order.localeCompare(b.order)
  ) as any[];
  const selectedRows = rows.slice(area.rowStartIndex, area.rowEndIndex + 1);
  const selectedColumns = columns.slice(
    area.columnStartIndex,
    area.columnEndIndex + 1
  );
  const cells = selectedRows
    .flatMap(row => selectedColumns.map(column =>
      table.props.cells[`${row.rowId}:${column.columnId}`]
    ))
    .filter(Boolean) as any[];
  if (!cells.length) return { ok: false as const, count: 0 };

  const key = alignment.axis === 'horizontal' ? 'textAlign' : 'verticalAlign';
  const defaultValue = alignment.axis === 'horizontal' ? 'left' : 'top';
  store.captureSync();
  store.transact(() => {
    for (const cell of cells) {
      if (alignment.value === defaultValue) delete cell[key];
      else cell[key] = alignment.value;
    }
  });
  store.captureSync();
  return { ok: true as const, count: cells.length };
}
