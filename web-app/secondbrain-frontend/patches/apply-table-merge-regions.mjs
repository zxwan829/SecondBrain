import fs from 'node:fs/promises';

const managerPath = new URL('../node_modules/@blocksuite/affine-block-table/src/table-data-manager.ts', import.meta.url);
const cellPath = new URL('../node_modules/@blocksuite/affine-block-table/src/table-cell.ts', import.meta.url);
const tableBlockPath = new URL('../node_modules/@blocksuite/affine-block-table/src/table-block.ts', import.meta.url);
const schemaPath = new URL('../node_modules/@blocksuite/affine-model/src/blocks/table/table-model.ts', import.meta.url);
let manager = await fs.readFile(managerPath, 'utf8');
let cell = await fs.readFile(cellPath, 'utf8');
let tableBlock = await fs.readFile(tableBlockPath, 'utf8');
let schema = await fs.readFile(schemaPath, 'utf8');

const structuralImport = "import { reconcileTableMergeRegions, canMergeTableRectangle } from '../../../../src/table-merge-invariants.ts';";
if (!manager.includes('table-merge-invariants.ts')) manager = `${structuralImport}\n${manager}`;

const schemaMarker = 'sb-table-merge-region-schema-v1';
if (!schema.includes(schemaMarker)) {
  const propsAnchor = 'export interface TableBlockProps extends BlockMeta {';
  if (!schema.includes(propsAnchor)) throw new Error('TableBlockProps schema anchor missing');
  schema = schema.replace(propsAnchor, `// ${schemaMarker}: declared so Yjs sync and Store history track merge geometry.\nexport interface TableMergeRegion {\n  version: 1;\n  id: string;\n  anchorRowId: string;\n  anchorColumnId: string;\n  rowIds: string[];\n  columnIds: string[];\n}\n\n${propsAnchor}`);
  schema = schema.replace('  cells: Record<string, TableCell>;\n}', '  cells: Record<string, TableCell>;\n  mergeRegions: Record<string, TableMergeRegion>;\n}');
  schema = schema.replace('    cells: {},\n    \'meta:createdAt\': undefined,', '    cells: {},\n    mergeRegions: {},\n    \'meta:createdAt\': undefined,');
}

const managerMarker = 'sb-versioned-merge-regions-v1';
if (!manager.includes(managerMarker)) {
  manager = manager.replace(
    'constructor(private readonly model: TableBlockModel) {}',
    'constructor(readonly model: TableBlockModel) {}\n  readonly mergeRevision$ = signal(0);'
  );
  const anchor = '  getCell(rowId: string, columnId: string): TableCell | undefined {';
  if (!manager.includes(anchor)) throw new Error('TableDataManager getCell anchor missing');
  const methods = `  // ${managerMarker}: stable row/column identity, non-destructive Yjs records.
  private get mergeRegions(): Record<string, any> {
    const props = this.model.props as any;
    // Subscribe to the Yjs-backed signal so undo/redo and remote updates redraw spans.
    return props.mergeRegions$?.value ?? props.mergeRegions ?? {};
  }

  private regionCells(region: any): Set<string> | null {
    if (region?.version !== 1 || !Array.isArray(region.rowIds) || !Array.isArray(region.columnIds) || !region.rowIds.length || !region.columnIds.length) return null;
    if (region.anchorRowId !== region.rowIds[0] || region.anchorColumnId !== region.columnIds[0]) return null;
    const rows = this.rows$.value, columns = this.columns$.value;
    const rowStart = rows.findIndex(row => row.rowId === region.rowIds[0]);
    const columnStart = columns.findIndex(column => column.columnId === region.columnIds[0]);
    if (rowStart < 0 || columnStart < 0) return null;
    if (JSON.stringify(rows.slice(rowStart, rowStart + region.rowIds.length).map(row => row.rowId)) !== JSON.stringify(region.rowIds)) return null;
    if (JSON.stringify(columns.slice(columnStart, columnStart + region.columnIds.length).map(column => column.columnId)) !== JSON.stringify(region.columnIds)) return null;
    const keys = new Set<string>();
    for (const rowId of region.rowIds) for (const columnId of region.columnIds) {
      const key = rowId + ':' + columnId;
      if (!this.getCell(rowId, columnId)) return null;
      keys.add(key);
    }
    return keys;
  }

  private get mergeRegionState() {
    const records = Object.entries(this.mergeRegions).map(([id, region]: [string, any]) => ({ id, region, cells: this.regionCells(region) }));
    const conflicts = new Set<string>();
    for (let i = 0; i < records.length; i++) for (let j = i + 1; j < records.length; j++) {
      const a = records[i], b = records[j];
      if (a.cells && b.cells && [...a.cells].some(key => b.cells!.has(key))) {
        conflicts.add(a.id); conflicts.add(b.id);
      }
    }
    return { records, conflicts };
  }

  get hasMergeRegions(): boolean {
    return Object.keys(this.mergeRegions).length > 0;
  }

  canMerge(selection: TableAreaSelection | undefined): boolean {
    if (this.readonly$.value || selection?.type !== 'area') return false;
    const rows = this.rows$.value, columns = this.columns$.value;
    if (rows.some(row => row.rowId === undefined) || columns.some(column => column.columnId === undefined)) return false;
    const rowIds = rows.map(row => row.rowId), columnIds = columns.map(column => column.columnId);
    const canMerge = canMergeTableRectangle(rowIds, columnIds, selection, this.mergeRegions);
    if (!canMerge) return false;
    for (let r = selection.rowStartIndex; r <= selection.rowEndIndex; r++) for (let c = selection.columnStartIndex; c <= selection.columnEndIndex; c++) {
      if (!this.getCell(rowIds[r]!, columnIds[c]!)) return false;
    }
    return true;
  }

  mergeCells(selection: TableAreaSelection | undefined): boolean {
    if (!this.canMerge(selection)) return false;
    const rows = this.rows$.value, columns = this.columns$.value;
    const regionId = nanoid();
    const rowIds = rows.slice(selection!.rowStartIndex, selection!.rowEndIndex + 1).map(row => row.rowId);
    const columnIds = columns.slice(selection!.columnStartIndex, selection!.columnEndIndex + 1).map(column => column.columnId);
    const region = { version: 1, id: regionId, anchorRowId: rowIds[0], anchorColumnId: columnIds[0], rowIds, columnIds };
    const store = this.model.store;
    store.captureSync();
    store.transact(() => {
      const selected = new Set<string>();
      for (const rowId of rowIds) for (const columnId of columnIds) selected.add(rowId + ':' + columnId);
      const mergeRegions = Object.fromEntries(Object.entries(this.mergeRegions).filter(([, existing]: [string, any]) => {
        const cells = this.regionCells(existing);
        return Boolean(cells) && ![...cells].every(key => selected.has(key));
      }));
      mergeRegions[regionId] = region;
      (this.model.props as any).mergeRegions = mergeRegions;
    });
    store.captureSync();
    this.mergeRevision$.value++;
    return true;
  }

  canSplitCell(rowId: string, columnId: string): boolean {
    if (this.readonly$.value) return false;
    const key = rowId + ':' + columnId;
    return this.mergeRegionState.records.some(record => record.cells?.has(key));
  }

  splitCell(rowId: string, columnId: string): boolean {
    if (!this.canSplitCell(rowId, columnId)) return false;
    const key = rowId + ':' + columnId;
    const ids = this.mergeRegionState.records.filter(record => record.cells?.has(key)).map(record => record.id);
    const next = { ...this.mergeRegions };
    ids.forEach(id => delete next[id]);
    const store = this.model.store;
    store.captureSync();
    store.transact(() => { (this.model.props as any).mergeRegions = next; });
    store.captureSync();
    this.mergeRevision$.value++;
    return true;
  }

  getMergeRenderInfo(rowId?: string, columnId?: string) {
    this.mergeRevision$.value;
    if (!rowId || !columnId) return undefined;
    const key = rowId + ':' + columnId;
    const { records, conflicts } = this.mergeRegionState;
    for (const record of records) {
      if (!record.cells?.has(key)) continue;
      if (conflicts.has(record.id)) return { conflict: true, covered: false, rowSpan: 1, columnSpan: 1 };
      const anchor = record.region.anchorRowId + ':' + record.region.anchorColumnId;
      if (key !== anchor) return { conflict: false, covered: true, rowSpan: 1, columnSpan: 1 };
      return { conflict: false, covered: false, rowSpan: record.region.rowIds.length, columnSpan: record.region.columnIds.length };
    }
    return undefined;
  }

`;
  manager = manager.replace(anchor, methods + anchor);
}

if (!manager.includes('readonly mergeRevision$ = signal(0)')) {
  manager = manager.replace('export class TableDataManager {', 'export class TableDataManager {\n  readonly mergeRevision$ = signal(0);');
  manager = manager.replace('    store.captureSync();\n    return true;\n  }\n\n  canSplitCell', '    store.captureSync();\n    this.mergeRevision$.value++;\n    return true;\n  }\n\n  canSplitCell');
  manager = manager.replace('    store.captureSync();\n    return true;\n  }\n\n  getMergeRenderInfo', '    store.captureSync();\n    this.mergeRevision$.value++;\n    return true;\n  }\n\n  getMergeRenderInfo');
  manager = manager.replace('  getMergeRenderInfo(rowId?: string, columnId?: string) {', '  getMergeRenderInfo(rowId?: string, columnId?: string) {\n    this.mergeRevision$.value;');
}

// Existing installations may already have the versioned merge patch but lack
// the reactive dependency needed to redraw after Store undo/redo or remote updates.
const reactiveMergeRegionsMarker = 'sb-reactive-merge-regions-v1';
if (!manager.includes(reactiveMergeRegionsMarker)) {
  const oldGetter = `  private get mergeRegions(): Record<string, any> {
    return (this.model.props as any).mergeRegions ?? {};
  }`;
  if (manager.includes(oldGetter)) {
    manager = manager.replace(oldGetter, `  // ${reactiveMergeRegionsMarker}: observe the model signal during rendering.
  private get mergeRegions(): Record<string, any> {
    const props = this.model.props as any;
    return props.mergeRegions$?.value ?? props.mergeRegions ?? {};
  }`);
  }
}

// Structural edits must keep stable-ID merge records rectangular and local.
const structuralMergeMarker = 'sb-table-structural-merge-reconcile-v1';
if (!manager.includes(structuralMergeMarker)) {
  const helper = `  // ${structuralMergeMarker}: structural edits preserve valid spans and reveal cells on invalid geometry.
  private reconcileStructuralMerges(options: { insertedRowId?: string; insertedColumnId?: string } = {}) {
    const rows = Object.values(this.model.props.rows).sort((a: any, b: any) => a.order.localeCompare(b.order));
    const columns = Object.values(this.model.props.columns).sort((a: any, b: any) => a.order.localeCompare(b.order));
    const current = this.mergeRegions;
    const next = reconcileTableMergeRegions(current, rows.map((row: any) => row.rowId), columns.map((column: any) => column.columnId), options);
    if (JSON.stringify(current) !== JSON.stringify(next)) (this.model.props as any).mergeRegions = next;
    this.mergeRevision$.value++;
  }

`;
  const anchors = [
    '  getCell(rowId: string, columnId: string): TableCell | undefined {',
    '  addRow(after?: number) {',
    '  addColumn(after?: number) {',
    '  deleteRow(rowId: string) {',
    '  deleteColumn(columnId: string) {',
  ];
  for (const anchor of anchors) if (!manager.includes(anchor)) throw new Error(`Structural merge patch anchor missing: ${anchor}`);
  manager = manager.replace(anchors[0], helper + anchors[0]);

  const replaceMethod = (signature, nextSource, nextSignature) => {
    const start = manager.indexOf(signature);
    const end = manager.indexOf(nextSignature, start + signature.length);
    if (start < 0 || end < 0) throw new Error(`Structural merge method boundary missing: ${signature}`);
    manager = manager.slice(0, start) + nextSource + manager.slice(end);
  };
  replaceMethod(
    '  addRow(after?: number) {',
    `  addRow(after?: number) {
    const order = this.getOrder(this.rows$.value, after);
    const rowId = nanoid();
    this.model.store.transact(() => {
      this.model.props.rows[rowId] = { rowId, order };
      this.columns$.value.forEach(column => {
        this.model.props.cells[String(rowId) + ':' + column.columnId] = { text: new Text() };
      });
      this.reconcileStructuralMerges({ insertedRowId: rowId });
    });
    return rowId;
  }
`,
    '  addNRow(count: number) {'
  );
  replaceMethod(
    '  addColumn(after?: number) {',
    `  addColumn(after?: number) {
    const order = this.getOrder(this.columns$.value, after);
    const columnId = nanoid();
    this.model.store.transact(() => {
      this.model.props.columns[columnId] = { columnId, order };
      this.rows$.value.forEach(row => {
        this.model.props.cells[String(row.rowId) + ':' + columnId] = { text: new Text() };
      });
      this.reconcileStructuralMerges({ insertedColumnId: columnId });
    });
    return columnId;
  }
`,
    '  deleteRow(rowId: string) {'
  );
  replaceMethod(
    '  deleteRow(rowId: string) {',
    `  deleteRow(rowId: string) {
    this.model.store.transact(() => {
      delete this.model.props.rows[rowId];
      for (const key of Object.keys(this.model.props.cells)) {
        if (key.startsWith(String(rowId) + ':')) delete this.model.props.cells[key];
      }
      this.reconcileStructuralMerges();
    });
  }
`,
    '  deleteColumn(columnId: string) {'
  );
  replaceMethod(
    '  deleteColumn(columnId: string) {',
    `  deleteColumn(columnId: string) {
    this.model.store.transact(() => {
      delete this.model.props.columns[columnId];
      for (const key of Object.keys(this.model.props.cells)) {
        if (key.endsWith(':' + String(columnId))) delete this.model.props.cells[key];
      }
      this.reconcileStructuralMerges();
    });
  }
`,
    '  updateRowOrder(rowId: string, newOrder: string) {'
  );

  for (const [signature, nextSignature] of [
    ['  updateRowOrder(rowId: string, newOrder: string) {', '  updateColumnOrder(columnId: string, newOrder: string) {'],
    ['  updateColumnOrder(columnId: string, newOrder: string) {', '  setRowBackgroundColor(rowId: string, color?: string) {'],
    ['  moveColumn(from: number, after?: number) {', '  moveRow(from: number, after?: number) {'],
    ['  moveRow(from: number, after?: number) {', '  duplicateColumn(index: number) {'],
  ]) {
    const start = manager.indexOf(signature);
    const end = manager.indexOf(nextSignature, start + signature.length);
    if (start < 0 || end < 0) throw new Error(`Structural merge ordering anchor missing: ${signature}`);
    const method = manager.slice(start, end);
    if (!method.includes('this.reconcileStructuralMerges()')) {
      const close = method.lastIndexOf('    });');
      if (close < 0) throw new Error(`Structural merge transaction missing: ${signature}`);
      manager = manager.slice(0, start + close) + '      this.reconcileStructuralMerges();\n' + manager.slice(start + close);
    }
  }

}

const duplicateMergeMarker = 'sb-table-duplicate-merge-reconcile-v1';
if (!manager.includes(duplicateMergeMarker)) {
  for (const [signature, nextSignature, options] of [
    ['  duplicateColumn(index: number) {', '  duplicateRow(index: number) {', 'insertedColumnId: newColumnId'],
    ['  duplicateRow(index: number) {', '\n}', 'insertedRowId: newRowId'],
  ]) {
    const start = manager.indexOf(signature);
    const end = manager.indexOf(nextSignature, start + signature.length);
    if (start < 0 || end < 0) throw new Error(`Structural merge duplicate anchor missing: ${signature}`);
    const method = manager.slice(start, end);
    const close = method.lastIndexOf('    });');
    if (close < 0) throw new Error(`Structural merge duplicate transaction missing: ${signature}`);
    manager = manager.slice(0, start + close) + `      this.reconcileStructuralMerges({ ${options} });\n` + manager.slice(start + close);
  }
  manager = manager.replace('  duplicateColumn(index: number) {', `  // ${duplicateMergeMarker}: duplicate insertions also reconcile merged geometry.\n  duplicateColumn(index: number) {`);
}

const tableLayoutMarker = 'sb-native-table-layout-for-spans-v1';
if (!tableBlock.includes(tableLayoutMarker)) {
  const tableAnchor = '<table class=\u0024{tableWrapper} \u0024{ref(this.table$)}>';
  if (!tableBlock.includes(tableAnchor)) throw new Error('TableBlock table wrapper anchor missing');
  tableBlock = tableBlock.replace(tableAnchor, `<table class=\u0024{tableWrapper} style="display:table;border-collapse:collapse;width:max-content;" data-${tableLayoutMarker}="true" \u0024{ref(this.table$)}>`);
}

// The native implementation indexes physical <td> elements as if they were
// model columns. Once a rowspan/colspan hides covered cells, those indexes no
// longer match the stable rowId/columnId model and the selection overlay jumps
// into adjacent cells. Compute the rectangle from visible anchors and spans.
const areaRectMarker = 'sb-table-area-rect-by-model-ids-v1';
if (!tableBlock.includes(areaRectMarker)) {
  const oldMethod = `  private readonly getAreaRect = (
    rowStartIndex: number,
    rowEndIndex: number,
    columnStartIndex: number,
    columnEndIndex: number
  ) => {
    const rootRect = this.getRootRect();
    const rows = this.querySelectorAll('tr');
    const startRow = rows.item(rowStartIndex);
    const endRow = rows.item(rowEndIndex);
    if (!startRow || !endRow || !rootRect) return;

    const startCells = startRow.querySelectorAll('td');
    const endCells = endRow.querySelectorAll('td');
    const startCell = startCells.item(columnStartIndex);
    const endCell = endCells.item(columnEndIndex);
    if (!startCell || !endCell) return;

    const startRect = startCell.getBoundingClientRect();
    const endRect = endCell.getBoundingClientRect();
    const scale = this.getScale();

    return {
      top: (startRect.top - rootRect.top) / scale,
      left: (startRect.left - rootRect.left) / scale,
      width: (endRect.right - startRect.left) / scale,
      height: (endRect.bottom - startRect.top) / scale,
    };
  };`;
  if (!tableBlock.includes(oldMethod)) throw new Error('TableBlock getAreaRect source anchor missing');
  const newMethod = `  // ${areaRectMarker}: map rendered spans back to stable model coordinates.
  private readonly getAreaRect = (
    rowStartIndex: number,
    rowEndIndex: number,
    columnStartIndex: number,
    columnEndIndex: number
  ) => {
    const rootRect = this.getRootRect();
    const rows = this.dataManager.rows$.value;
    const columns = this.dataManager.columns$.value;
    if (!rootRect || rowStartIndex < 0 || columnStartIndex < 0 || rowEndIndex >= rows.length || columnEndIndex >= columns.length) return;

    const rowIndices = new Map(rows.map((row, index) => [row.rowId, index]));
    const columnIndices = new Map(columns.map((column, index) => [column.columnId, index]));
    const rects = Array.from(this.querySelectorAll<HTMLTableCellElement>('td[data-row-id][data-column-id]'))
      .filter(cell => {
        const row = rowIndices.get(cell.dataset.rowId ?? '');
        const column = columnIndices.get(cell.dataset.columnId ?? '');
        if (row === undefined || column === undefined) return false;
        const rowEnd = row + Math.max(1, cell.rowSpan || 1) - 1;
        const columnEnd = column + Math.max(1, cell.colSpan || 1) - 1;
        return row <= rowEndIndex && rowEnd >= rowStartIndex && column <= columnEndIndex && columnEnd >= columnStartIndex;
      })
      .map(cell => cell.getBoundingClientRect());
    if (!rects.length) return;
    const left = Math.min(...rects.map(rect => rect.left));
    const top = Math.min(...rects.map(rect => rect.top));
    const right = Math.max(...rects.map(rect => rect.right));
    const bottom = Math.max(...rects.map(rect => rect.bottom));
    const scale = this.getScale();
    return {
      top: (top - rootRect.top) / scale,
      left: (left - rootRect.left) / scale,
      width: (right - left) / scale,
      height: (bottom - top) / scale,
    };
  };`;
  tableBlock = tableBlock.replace(oldMethod, newMethod);
}

const cellMarker = 'sb-versioned-merge-regions-render-v1';
if (!cell.includes(cellMarker)) {
  const renderAnchor = '  override render() {\n    if (!this.text) {';
  if (!cell.includes(renderAnchor)) throw new Error('TableCell render anchor missing');
  cell = cell.replace(renderAnchor, `  override render() {
    // ${cellMarker}: hidden cells retain their original Y.Text in the model.
    const merge = this.dataManager.getMergeRenderInfo(this.row?.rowId, this.column?.columnId);
    if (merge?.covered) return nothing;
    if (!this.text) {`);
  cell = cell.replace(
    '<td class=\u0024{cellContainerStyle} style=\u0024{this.tdStyle()}>',
    '<td data-row-id=\u0024{this.row?.rowId} data-column-id=\u0024{this.column?.columnId} colspan=\u0024{merge?.columnSpan ?? 1} rowspan=\u0024{merge?.rowSpan ?? 1} class=\u0024{cellContainerStyle} style=\u0024{this.tdStyle()}>'
  );
  const regularCell = '<td\n        data-row-id=\u0024{this.row?.rowId}\n        data-column-id=\u0024{this.column?.columnId}';
  if (!cell.includes(regularCell)) throw new Error('TableCell regular td anchor missing');
  cell = cell.replace(regularCell, '<td\n        data-row-id=\u0024{this.row?.rowId}\n        data-column-id=\u0024{this.column?.columnId}\n        colspan=\u0024{merge?.columnSpan ?? 1}\n        rowspan=\u0024{merge?.rowSpan ?? 1}');
}

if (!cell.includes('sb-merge-span-dimensions-v1')) {
  const tdStyleAnchor = '  tdStyle() {\n    const columnWidth = this.virtualWidth$.value ?? this.column?.width;';
  if (!cell.includes(tdStyleAnchor)) throw new Error('TableCell tdStyle anchor missing');
  cell = cell.replace(tdStyleAnchor, `  // sb-merge-span-dimensions-v1
  tdStyle(merge?: { columnSpan: number; rowSpan: number }) {
    const mergedWidth = merge && merge.columnSpan > 1
      ? this.dataManager.columns$.value.slice(this.columnIndex, this.columnIndex + merge.columnSpan).reduce((sum, column) => sum + (column.width ?? DefaultColumnWidth), 0)
      : undefined;
    const mergedHeight = merge && merge.rowSpan > 1
      ? this.dataManager.rows$.value.slice(this.rowIndex, this.rowIndex + merge.rowSpan).reduce((sum, row) => sum + (row.minHeight ?? 38), 0)
      : undefined;
    const columnWidth = mergedWidth ?? this.virtualWidth$.value ?? this.column?.width;`);
  cell = cell.replace('const rowMinHeight = this.row?.minHeight;', 'const rowMinHeight = mergedHeight ?? this.row?.minHeight;');
  cell = cell.replace('      minHeight: rowMinHeight ? `${rowMinHeight}px` : undefined,', '      minHeight: rowMinHeight ? `${rowMinHeight}px` : undefined,\n      height: mergedHeight ? `${mergedHeight}px` : undefined,');
  cell = cell.replaceAll('this.tdStyle()', 'this.tdStyle(merge)');
}
if (!cell.includes('height: mergedHeight')) {
  cell = cell.replace('      minHeight: rowMinHeight ? `${rowMinHeight}px` : undefined,', '      minHeight: rowMinHeight ? `${rowMinHeight}px` : undefined,\n      height: mergedHeight ? `${mergedHeight}px` : undefined,');
}

// Existing installs may already have the v1 marker but an older command body.
// Upgrade by the method contract as well as the initial-install marker.
const canMergeStart = manager.indexOf('  canMerge(selection: TableAreaSelection | undefined): boolean {');
const canMergeEnd = manager.indexOf('  mergeCells(', canMergeStart);
if (canMergeStart < 0 || canMergeEnd < 0) throw new Error('Merge command upgrade anchors missing');
if (!manager.slice(canMergeStart, canMergeEnd).includes('canMergeTableRectangle(')) {
  manager = manager.slice(0, canMergeStart) + `  canMerge(selection: TableAreaSelection | undefined): boolean {
    if (this.readonly$.value || selection?.type !== 'area') return false;
    const rows = this.rows$.value, columns = this.columns$.value;
    if (rows.some(row => row.rowId === undefined) || columns.some(column => column.columnId === undefined)) return false;
    const rowIds = rows.map(row => row.rowId), columnIds = columns.map(column => column.columnId);
    if (!canMergeTableRectangle(rowIds, columnIds, selection, this.mergeRegions)) return false;
    for (let r = selection.rowStartIndex; r <= selection.rowEndIndex; r++) for (let c = selection.columnStartIndex; c <= selection.columnEndIndex; c++) {
      if (!this.getCell(rowIds[r]!, columnIds[c]!)) return false;
    }
    return true;
  }

` + manager.slice(canMergeEnd);
}
manager = manager.replace('if (!a.cells || !b.cells || [...a.cells].some(key => b.cells!.has(key)))', 'if (a.cells && b.cells && [...a.cells].some(key => b.cells!.has(key)))');
manager = manager.replace('return !cells || ![...cells].every(key => selected.has(key));', 'return Boolean(cells) && ![...cells].every(key => selected.has(key));');

await fs.writeFile(managerPath, manager);
await fs.writeFile(cellPath, cell);
await fs.writeFile(tableBlockPath, tableBlock);
await fs.writeFile(schemaPath, schema);
console.log('PATCHED · stable mergeRegions v1 model commands + non-destructive table rendering');
