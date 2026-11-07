import fs from 'node:fs/promises';

const path = new URL('../node_modules/@blocksuite/affine-block-table/src/table-block.ts', import.meta.url);
let source = await fs.readFile(path, 'utf8');
const marker = 'sb-row-boundary-resize-v3';
const boundaryImport = "import { getVisibleTableRowResizeTarget } from '../../../../src/table-row-boundary.ts';";
if (!source.includes('table-row-boundary.ts')) source = boundaryImport + '\n' + source;
const oldStarts = ['  // sb-row-boundary-resize-v1:', '  // sb-row-boundary-resize-v2:'].map(marker => source.indexOf(marker)).filter(index => index >= 0);
const oldStart = oldStarts.length ? Math.min(...oldStarts) : -1;
if (oldStart >= 0) {
  const oldEnd = source.indexOf('  override renderBlock() {', oldStart);
  if (oldEnd < 0) throw new Error('Old row resize method boundary missing');
  source = source.slice(0, oldStart) + source.slice(oldEnd);
}

if (!source.includes(marker)) {
  const methodAnchor = '  override renderBlock() {';
  if (!source.includes(methodAnchor)) throw new Error('TableBlock renderBlock anchor missing');
  const methods = `  // ${marker}: persist row minHeight in the existing Table/Yjs model.
  private visibleRowResizeTarget(event: PointerEvent) {
    if (event.composedPath().some(node => node instanceof Element && node.matches('[data-testid="drag-row-handle"],[data-testid="drag-column-handle"]'))) return;
    const cell = event.composedPath().find((node): node is HTMLTableCellElement =>
      node instanceof HTMLTableCellElement && node.matches('td[data-row-id][data-column-id]'));
    return getVisibleTableRowResizeTarget(this, cell, event.clientY);
  }

  private updateRowResizeCursor(event: PointerEvent, row: HTMLTableRowElement) {
    row.style.cursor = event.pointerType !== 'touch' && this.visibleRowResizeTarget(event) ? 'row-resize' : '';
  }

  private startRowResize(event: PointerEvent, _rowId: string, _row: HTMLTableRowElement) {
    if (event.button !== 0 || this.dataManager.readonly$.value || event.pointerType === 'touch') return;
    const row = this.visibleRowResizeTarget(event);
    const rowId = row?.dataset.rowId;
    if (!row || !rowId) return;
    const rect = row.getBoundingClientRect();

    event.preventDefault();
    event.stopPropagation();
    const scale = this.getScale() || 1;
    const startY = event.clientY;
    const startHeight = rect.height / scale;
    let nextHeight = startHeight;
    row.style.cursor = 'row-resize';

    const move = (nextEvent: PointerEvent) => {
      if (nextEvent.pointerId !== event.pointerId) return;
      nextHeight = Math.max(38, startHeight + (nextEvent.clientY - startY) / scale);
      row.style.height = String(nextHeight) + 'px';
    };
    const finish = (commit: boolean) => {
      document.removeEventListener('pointermove', move, true);
      document.removeEventListener('pointerup', onUp, true);
      document.removeEventListener('pointercancel', onCancel, true);
      row.style.height = '';
      row.style.cursor = '';
      if (!commit || Math.abs(nextHeight - startHeight) < 1) return;
      const store = this.model.store;
      store.captureSync();
      store.transact(() => {
        const modelRow = this.model.props.rows[rowId];
        if (modelRow) modelRow.minHeight = Math.round(nextHeight);
      });
      store.captureSync();
    };
    const onUp = (nextEvent: PointerEvent) => {
      if (nextEvent.pointerId === event.pointerId) finish(true);
    };
    const onCancel = (nextEvent: PointerEvent) => {
      if (nextEvent.pointerId === event.pointerId) finish(false);
    };
    document.addEventListener('pointermove', move, true);
    document.addEventListener('pointerup', onUp, true);
    document.addEventListener('pointercancel', onCancel, true);
  }

`;
  source = source.replace(methodAnchor, methods + methodAnchor);
  const interpolation = '$' + '{';
  const tick = String.fromCharCode(96);
  const rowAnchor = '<tr class=' + interpolation + 'rowStyle} data-row-id=' + interpolation + 'row.rowId} style=' + interpolation + 'styleMap({ height: row.minHeight ? ' + tick + interpolation + 'row.minHeight}px' + tick + ' : undefined })}>';
  if (!source.includes(rowAnchor) && !source.includes('this.updateRowResizeCursor(event, event.currentTarget as HTMLTableRowElement)')) throw new Error('TableBlock row render anchor missing');
  const rowReplacement = '<tr class=' + interpolation + 'rowStyle} data-row-id=' + interpolation + 'row.rowId} style=' + interpolation + 'styleMap({ height: row.minHeight ? ' + tick + interpolation + 'row.minHeight}px' + tick + ' : undefined })} @pointermove=' + interpolation + '(event: PointerEvent) => this.updateRowResizeCursor(event, event.currentTarget as HTMLTableRowElement)} @pointerleave=' + interpolation + '(event: PointerEvent) => ((event.currentTarget as HTMLTableRowElement).style.cursor = \'\')} @pointerdown=' + interpolation + '(event: PointerEvent) => this.startRowResize(event, row.rowId, event.currentTarget as HTMLTableRowElement)}>';
  source = source.replace(rowAnchor, rowReplacement);
}

await fs.writeFile(path, source);
console.log('PATCHED · pointer row-boundary resize persists minHeight to Table/Yjs model');
