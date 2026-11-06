import fs from 'node:fs/promises';

const file = new URL('../node_modules/@blocksuite/affine-block-table/src/table-cell.ts', import.meta.url);
let source = await fs.readFile(file, 'utf8');
const selectionImport = "import { expandTableAreaToMergeClosure } from '../../../../src/table-commands.ts';";
if (!source.includes('expandTableAreaToMergeClosure')) source = selectionImport + '\n' + source;
const alignmentImport = "import { tableSelectionToArea } from '../../../../src/table-commands.ts';";
if (!source.includes('tableSelectionToArea')) source = alignmentImport + '\n' + source;
const iconImportAnchor = '  PasteIcon,\n} from \'@blocksuite/icons/lit\';';
if (!source.includes('  TextAlignLeftIcon,')) {
  if (!source.includes(iconImportAnchor)) throw new Error('Table icon import anchor missing');
  source = source.replace(iconImportAnchor, `  PasteIcon,
  GridIcon,
  HeaderColumnIcon,
  HeaderRowIcon,
  SplitViewIcon,
  TextAlignBottomIcon,
  TextAlignCenterIcon,
  TextAlignLeftIcon,
  TextAlignMediumIcon,
  TextAlignRightIcon,
  TextAlignTopIcon,
} from '@blocksuite/icons/lit';`);
}
if (!source.includes('  TextColorIcon,')) source = source.replace('  TextAlignTopIcon,', '  TextAlignTopIcon,\n  TextColorIcon,');
const marker = 'sb-table-unified-context-menu-v11';
if (!source.includes('html, nothing, svg')) {
  source = source.replace("import { html, nothing } from 'lit';", "import { html, nothing, svg } from 'lit';");
}
const legacyMarker = '  // sb-table-unified-context-menu-v1:';
const currentMarker = '  // sb-table-unified-context-menu-v2:';
const legacyStart = source.indexOf(legacyMarker);
const currentStart = source.indexOf(currentMarker, legacyStart + 1);
if (legacyStart >= 0 && currentStart > legacyStart) {
  source = source.slice(0, legacyStart) + source.slice(currentStart);
}
const previousMenuStarts = [source.indexOf(currentMarker), ...Array.from({ length: 10 }, (_, index) => source.indexOf(`  // sb-table-unified-context-menu-v${index + 3}:`))].filter(index => index >= 0);
const previousMenuStart = previousMenuStarts.length ? Math.min(...previousMenuStarts) : -1;
if (previousMenuStart >= 0 && !source.includes(marker)) {
  const previousMenuEnd = source.indexOf('  createColorPickerMenu(', previousMenuStart);
  if (previousMenuEnd < 0) throw new Error('Previous TableCell menu patch end anchor missing');
  source = source.slice(0, previousMenuStart) + source.slice(previousMenuEnd);
}
if (!source.includes(marker)) {
  let start = source.indexOf('  openColumnOptions(');
  let end = source.indexOf('  createColorPickerMenu(', start);
  if (start < 0) {
    start = source.indexOf('  createColorPickerMenu(');
    end = start;
  }
  if (start < 0 || end < 0) throw new Error('TableCell option methods anchor missing');
  const common = `  // ${marker}: one action menu for cell context and row/column handles.
  openUnifiedOptions(target: PopupTarget, selection: any, row?: TableRow, rowIndex?: number, column?: TableColumn, columnIndex?: number) {
    const rows = this.dataManager.rows$.value;
    const columns = this.dataManager.columns$.value;
    const store = this.dataManager.model.store;
    const isArea = selection?.type === 'area';
    const alignmentArea = tableSelectionToArea(selection, rows.map((item: any) => item.rowId), columns.map((item: any) => item.columnId));
    const selectedRows = alignmentArea ? rows.slice(alignmentArea.rowStartIndex, alignmentArea.rowEndIndex + 1) : [];
    const selectedColumns = alignmentArea ? columns.slice(alignmentArea.columnStartIndex, alignmentArea.columnEndIndex + 1) : [];
    const align = (key: 'textAlign' | 'verticalAlign', value: string, fallback: string) => {
      if (!alignmentArea) return;
      store.captureSync();
      store.transact(() => selectedRows.forEach(r => selectedColumns.forEach(c => {
        const cell = this.dataManager.getCell(r.rowId, c.columnId) as any;
        if (!cell) return;
        if (value === fallback) delete cell[key]; else cell[key] = value;
      })));
      store.captureSync();
    };
    const cells = selectedRows.flatMap(r => selectedColumns.map(c => ({ r, c })));
    const canMerge = isArea && this.dataManager.canMerge(selection);
    const splitTarget = cells.find(({ r, c }) => this.dataManager.canSplitCell(r.rowId, c.columnId));
    const sameValue = (key: 'textAlign' | 'verticalAlign', value: string, fallback: string) => cells.length > 0 && cells.every(({ r, c }) => {
      const cell = this.dataManager.getCell(r.rowId, c.columnId) as any;
      return (cell?.[key] ?? fallback) === value;
    });
    const icon = (name: string, svg: any, selected: boolean) => html\`<span role="button" aria-pressed="\${selected}" title="\${name}" aria-label="\${name}" style="display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px">\${svg}</span>\`;
    const linearIcon = (kind: 'merge' | 'split' | 'background' | 'row' | 'column') => {
      const shapes: Record<typeof kind, any> = {
        merge: svg\`<path d="M3 3h14v14H3zM10 3v4m0 6v4M3 10h4m6 0h4M7 7l3 3 3-3"/>\`,
        split: svg\`<path d="M3 3h14v14H3zM10 3v4m0 6v4M3 10h4m6 0h4M10 10 7 7m3 3 3-3m-3 3-3 3m3-3 3 3"/>\`,
        background: svg\`<path d="m5 14 7-7 4 4-7 7H5zM11 8l3 3M4 19h12M13 6l2-2 4 4-2 2"/>\`,
        row: svg\`<path d="M3 3h14v14H3zM3 8h14M3 12h14"/>\`,
        column: svg\`<path d="M3 3h14v14H3zM8 3v14M12 3v14"/>\`,
      };
      return html\`<svg viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">\${shapes[kind]}</svg>\`;
    };
    const alignActions = (currentMenu: any, axis: 'horizontal' | 'vertical', key: 'textAlign' | 'verticalAlign', values: readonly [string, string, any][]) =>
      currentMenu.renderItems(values.map(([name, value, glyph]) => menu.action({
        name,
        label: () => icon(name, glyph({ width: 18, height: 18 }), sameValue(key, value, axis === 'horizontal' ? 'left' : 'top')),
        // Native isSelected appends a 20px checkmark: a compact icon button uses
        // its pressed styling instead, so one button always contains one glyph.
        class: { 'sb-table-align-button': true, 'selected-item': sameValue(key, value, axis === 'horizontal' ? 'left' : 'top') },
        select: () => { align(key, value, axis === 'horizontal' ? 'left' : 'top'); },
      })));
    const alignmentPanel = (currentMenu: any) => html\`<style>
      .sb-table-align-panel{display:flex;flex-direction:column;gap:6px;padding:2px 4px}
      .sb-table-align-line{display:flex;align-items:center;gap:8px;min-height:30px}
      .sb-table-align-title{width:58px;flex:0 0 58px;display:flex;align-items:center;gap:4px;font-size:12px;color:var(--affine-text-secondary-color)}
      .sb-table-align-grid{display:grid;grid-template-columns:repeat(3,30px);gap:3px}
      .sb-table-align-grid affine-menu-button{width:30px;height:30px}
      .sb-table-align-grid .affine-menu-button{box-sizing:border-box;width:30px;height:30px;justify-content:center;padding:3px}
      .sb-table-align-grid .affine-menu-action-text{flex:0 0 auto;font-size:0;line-height:0;color:transparent}
      .sb-table-align-grid .affine-menu-action-text span{color:var(--affine-icon-color)}
      .sb-table-align-button.selected-item{background:var(--affine-hover-color);outline:1px solid var(--affine-primary-color)}
      .sb-table-context-disabled{opacity:.42;cursor:not-allowed}
      .sb-table-context-disabled .affine-menu-button{cursor:not-allowed}
    </style><div class="sb-table-align-panel">
      <div class="sb-table-align-line"><span class="sb-table-align-title">\${TextAlignLeftIcon({width:16,height:16})}水平</span><div class="sb-table-align-grid">\${alignActions(currentMenu,'horizontal','textAlign',[['左对齐','left',TextAlignLeftIcon],['居中','center',TextAlignCenterIcon],['右对齐','right',TextAlignRightIcon]] as const)}</div></div>
      <div class="sb-table-align-line"><span class="sb-table-align-title">\${TextAlignTopIcon({width:16,height:16})}垂直</span><div class="sb-table-align-grid">\${alignActions(currentMenu,'vertical','verticalAlign',[['顶部对齐','top',TextAlignTopIcon],['垂直居中','middle',TextAlignMediumIcon],['底部对齐','bottom',TextAlignBottomIcon]] as const)}</div></div>
    </div>\`;
    const areaActions = alignmentArea ? [
      menu.group({ items: [
        menu.action({ name: '复制', prefix: CopyIcon(), select: () => this.selectionController.doCopyOrCut(alignmentArea, false) }),
        menu.action({ name: '粘贴', prefix: PasteIcon(), select: () => { void navigator.clipboard.readText().then(text => this.selectionController.doPaste(text, alignmentArea)); } }),
        menu.action({ name: '清空所选单元格', prefix: CloseIcon(), select: () => this.dataManager.clearCellsBySelection(alignmentArea) }),
      ] }),
      alignmentPanel,
      menu.group({ items: [
        menu.action({ name: '合并单元格', prefix: linearIcon('merge'), class: { 'sb-table-context-disabled': !canMerge }, label: () => html\`<span title="\${canMerge ? '合并所选单元格' : '需选择至少两个可合并的相邻单元格'}">合并单元格</span>\`, select: () => { if (!canMerge) return false; this.dataManager.mergeCells(selection); } }),
        menu.action({ name: '拆分单元格', prefix: linearIcon('split'), class: { 'sb-table-context-disabled': !splitTarget }, label: () => html\`<span title="\${splitTarget ? '拆分所选合并单元格' : '所选范围不包含合并单元格'}">拆分单元格</span>\`, select: () => { if (!splitTarget) return false; this.dataManager.splitCell(splitTarget.r.rowId, splitTarget.c.columnId); } }),
      ] }),
    ] : [];
    const rowActions = row && rowIndex !== undefined ? [
      menu.subMenu({ name: '行操作', prefix: linearIcon('row'), options: { items: [
        menu.action({ name: '上方插入行', prefix: InsertAboveIcon(), select: () => this.dataManager.insertRow(rowIndex > 0 ? rowIndex - 1 : undefined) }),
        menu.action({ name: '下方插入行', prefix: InsertBelowIcon(), select: () => this.dataManager.insertRow(rowIndex) }),
        menu.action({ name: '复制行', prefix: DuplicateIcon(), select: () => this.dataManager.duplicateRow(rowIndex) }),
        menu.action({ name: '清空行内容', prefix: CloseIcon(), select: () => this.dataManager.clearRow(row.rowId) }),
        menu.action({ name: '删除行', class: { 'delete-item': true }, prefix: DeleteIcon(), select: () => this.dataManager.deleteRow(row.rowId) }),
      ] } }),
    ] : [];
    const columnActions = column && columnIndex !== undefined ? [
      menu.subMenu({ name: '列操作', prefix: linearIcon('column'), options: { items: [
        menu.action({ name: '左侧插入列', prefix: InsertLeftIcon(), select: () => this.dataManager.insertColumn(columnIndex > 0 ? columnIndex - 1 : undefined) }),
        menu.action({ name: '右侧插入列', prefix: InsertRightIcon(), select: () => this.dataManager.insertColumn(columnIndex) }),
        menu.action({ name: '复制列', prefix: DuplicateIcon(), select: () => this.dataManager.duplicateColumn(columnIndex) }),
        menu.action({ name: '清空列内容', prefix: CloseIcon(), select: () => this.dataManager.clearColumn(column.columnId) }),
        menu.action({ name: '删除列', class: { 'delete-item': true }, prefix: DeleteIcon(), select: () => this.dataManager.deleteColumn(column.columnId) }),
      ] } }),
    ] : [];
    const backgroundAction = row
      ? this.createColorPickerMenu(row.backgroundColor, color => this.dataManager.setRowBackgroundColor(row.rowId, color))
      : column
        ? this.createColorPickerMenu(column.backgroundColor, color => this.dataManager.setColumnBackgroundColor(column.columnId, color))
        : selectedRows.length
          ? this.createColorPickerMenu(selectedRows[0].backgroundColor, color => selectedRows.forEach(r => this.dataManager.setRowBackgroundColor(r.rowId, color)))
          : undefined;
    let outsidePointer: ((event: PointerEvent) => void) | undefined;
    let escapeKey: ((event: KeyboardEvent) => void) | undefined;
    const popup = popMenu(target, { options: { onComplete: () => { cleanup(); }, onClose: () => { cleanup(); }, items: [
      ...areaActions,
      ...(backgroundAction ? [menu.group({items:[backgroundAction]})] : []),
      ...(rowActions.length ? [menu.group({ items: rowActions })] : []),
      ...(columnActions.length ? [menu.group({ items: columnActions })] : []),
    ] } });
    const cleanup = () => {
      if (outsidePointer) document.removeEventListener('pointerdown', outsidePointer, true);
      if (escapeKey) document.removeEventListener('keydown', escapeKey, true);
      outsidePointer = undefined; escapeKey = undefined;
    };
    popup.menu.menuElement.style.width = '252px';
    popup.menu.menuElement.style.maxWidth = 'min(252px, calc(100vw - 16px))';
    outsidePointer = event => {
      const inside = event.composedPath().some(node => node instanceof Element && (node.closest('affine-menu, mobile-menu') || node.matches('affine-menu, mobile-menu')));
      if (!inside) popup.close();
    };
    escapeKey = event => {
      if (event.key !== 'Escape') return;
      const nested = popup.menu.menuElement.parentElement?.querySelectorAll('affine-menu, mobile-menu').length ?? 0;
      event.preventDefault(); event.stopImmediatePropagation();
      if (nested > 1) popup.menu.closeSubMenu(); else popup.close();
    };
    document.addEventListener('pointerdown', outsidePointer, true);
    document.addEventListener('keydown', escapeKey, true);
  }

  openSelectedTextColorOptions(target: PopupTarget) {
    const inlineEditor = this.inlineEditor;
    const range = inlineEditor?.getInlineRange();
    const selectedText = window.getSelection()?.toString();
    if (!inlineEditor || !range || range.length < 1 || !selectedText) return false;
    const colors = [
      ['默认文字颜色', null], ['红色', 'var(--affine-text-highlight-foreground-red)'],
      ['橙色', 'var(--affine-text-highlight-foreground-orange)'], ['黄色', 'var(--affine-text-highlight-foreground-yellow)'],
      ['绿色', 'var(--affine-text-highlight-foreground-green)'], ['青色', 'var(--affine-text-highlight-foreground-teal)'],
      ['蓝色', 'var(--affine-text-highlight-foreground-blue)'], ['紫色', 'var(--affine-text-highlight-foreground-purple)'],
      ['灰色', 'var(--affine-text-highlight-foreground-grey)'],
    ] as const;
    popMenu(target, { options: { items: [menu.subMenu({ name: '文字颜色', prefix: TextColorIcon(), options: { items: colors.map(([name, color]) => menu.action({ name, select: () => {
      const store = this.dataManager.model.store;
      store.captureSync();
      inlineEditor.formatText(range, { color });
      store.captureSync();
    } })) } })] } });
    return true;
  }

  // A handle and a right-click open the same menu with a real cell area.
  handleArea(rowIndex: number, columnIndex: number) {
    const rows = this.dataManager.rows$.value, columns = this.dataManager.columns$.value;
    const current = this.selectionController.selected$.value;
    const preservesArea = current?.type === 'area' && rowIndex >= current.rowStartIndex && rowIndex <= current.rowEndIndex && columnIndex >= current.columnStartIndex && columnIndex <= current.columnEndIndex;
    const area = preservesArea ? current : { type: 'area' as const, rowStartIndex: rowIndex, rowEndIndex: rowIndex, columnStartIndex: columnIndex, columnEndIndex: columnIndex };
    return expandTableAreaToMergeClosure(area, rows.map(row => row.rowId), columns.map(column => column.columnId), (this.dataManager.model.props as any).mergeRegions ?? {});
  }

  openColumnOptions(target: PopupTarget, column: TableColumn, columnIndex: number) {
    const rowIndex = this.row ? this.dataManager.rows$.value.findIndex(row => row.rowId === this.row!.rowId) : -1;
    const selection = rowIndex >= 0 ? this.handleArea(rowIndex, columnIndex) : { type: 'column' as const, columnId: column.columnId };
    this.selectionController.setSelected(selection);
    this.openUnifiedOptions(target, selection, this.row, rowIndex >= 0 ? rowIndex : undefined, column, columnIndex);
  }

  openRowOptions(target: PopupTarget, row: TableRow, rowIndex: number) {
    const columnIndex = this.column ? this.dataManager.columns$.value.findIndex(column => column.columnId === this.column!.columnId) : -1;
    const selection = columnIndex >= 0 ? this.handleArea(rowIndex, columnIndex) : { type: 'row' as const, rowId: row.rowId };
    this.selectionController.setSelected(selection);
    this.openUnifiedOptions(target, selection, row, rowIndex, this.column, columnIndex >= 0 ? columnIndex : undefined);
  }


`;
  source = source.slice(0, start) + common + source.slice(end);

  const contextStart = source.indexOf('  onContextMenu(e: Event) {');
  const contextEnd = source.indexOf('  renderColumnOptions(', contextStart);
  if (contextStart < 0 || contextEnd < 0) throw new Error('TableCell context menu anchor missing');
  const context = `  onContextMenu(e: Event) {
    e.preventDefault();
    e.stopPropagation();
    const textRange = this.inlineEditor?.getInlineRange();
    if (textRange?.length && window.getSelection()?.toString()) {
      this.openSelectedTextColorOptions(popupTargetFromElement(e.currentTarget as HTMLElement));
      return;
    }
    const rows = this.dataManager.rows$.value;
    const columns = this.dataManager.columns$.value;
    const rowIndex = this.row ? rows.findIndex(item => item.rowId === this.row!.rowId) : -1;
    const columnIndex = this.column ? columns.findIndex(item => item.columnId === this.column!.columnId) : -1;
    const current = this.selectionController.selected$.value;
    const preservesArea = current?.type === 'area' && rowIndex >= current.rowStartIndex && rowIndex <= current.rowEndIndex && columnIndex >= current.columnStartIndex && columnIndex <= current.columnEndIndex;
    const preservesWholeRow = current?.type === 'row' && current.rowId === this.row?.rowId;
    const preservesWholeColumn = current?.type === 'column' && current.columnId === this.column?.columnId;
    const selection = preservesArea || preservesWholeRow || preservesWholeColumn ? current : (rowIndex >= 0 && columnIndex >= 0 ? {
      type: 'area', rowStartIndex: rowIndex, rowEndIndex: rowIndex,
      columnStartIndex: columnIndex, columnEndIndex: columnIndex,
    } : undefined);
    if (!selection || !(e.currentTarget instanceof HTMLElement)) return;
    if (!preservesArea && !preservesWholeRow && !preservesWholeColumn) this.selectionController.setSelected(selection);
    const target = popupTargetFromElement(e.currentTarget);
    this.openUnifiedOptions(target, selection, this.row, rowIndex >= 0 ? rowIndex : undefined, this.column, columnIndex >= 0 ? columnIndex : undefined);
  }

`;
  source = source.slice(0, contextStart) + context + source.slice(contextEnd);
  await fs.writeFile(file, source);
}
console.log('PATCHED · unified compact table context menu');
