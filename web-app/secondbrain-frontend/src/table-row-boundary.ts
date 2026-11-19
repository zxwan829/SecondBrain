/** Only the visible bottom edge of a cell is a resize handle. */
export function visibleRowBoundaryIndex(
  cellBottom: number, pointerY: number, anchorRowIndex: number,
  rowSpan: number, rowCount: number, tolerance = 6
): number | null {
  if (![cellBottom, pointerY, anchorRowIndex, rowSpan, rowCount].every(Number.isFinite) ||
    !Number.isInteger(anchorRowIndex) || !Number.isInteger(rowSpan) ||
    anchorRowIndex < 0 || rowSpan < 1 || Math.abs(cellBottom - pointerY) > tolerance) return null;
  const boundary = anchorRowIndex + rowSpan - 1;
  return boundary < rowCount ? boundary : null;
}

export function getVisibleTableRowResizeTarget(
  table: HTMLElement, cell: HTMLTableCellElement | undefined, pointerY: number
): HTMLTableRowElement | undefined {
  if (!cell || !table.contains(cell)) return;
  const rows = Array.from(table.querySelectorAll<HTMLTableRowElement>('tr[data-row-id]'));
  const anchor = rows.findIndex(row => row.dataset.rowId === cell.dataset.rowId);
  const boundary = visibleRowBoundaryIndex(cell.getBoundingClientRect().bottom, pointerY,
    anchor, Math.max(1, cell.rowSpan), rows.length);
  return boundary === null ? undefined : rows[boundary];
}
