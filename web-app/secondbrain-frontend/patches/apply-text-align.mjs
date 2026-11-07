// Zod union optional compatibility is supplied by the existing security patch.
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
function patch(pkg, file, edits) {
  const manifestPath = path.join(root, 'node_modules/@blocksuite', pkg, 'package.json');
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  if (manifest.version !== '0.22.4') throw new Error(`${pkg}: expected 0.22.4, got ${manifest.version}`);
  const target = path.join(path.dirname(manifestPath), file);
  let source = fs.readFileSync(target, 'utf8');
  for (const [before, after] of edits) {
    if (source.includes(after)) continue;
    if (!source.includes(before)) {
      if (source.includes(after)) continue;
      // The merge-regions postinstall patch composes merged span dimensions
      // into the tdStyle implementation introduced by this patch. Treat that
      // exact composed form as already aligned when postinstall is replayed.
      const alreadyAlignedTableCellWithMergeRegions =
        pkg === 'affine-block-table' &&
        file === 'src/table-cell.ts' &&
        before.startsWith('  tdStyle() {') &&
        source.includes('sb-merge-span-dimensions-v1') &&
        source.includes("textAlign: this.storedCell?.textAlign ?? 'left'") &&
        source.includes("verticalAlign: this.storedCell?.verticalAlign ?? 'top'") &&
        source.includes('rowMinHeight = mergedHeight ?? this.row?.minHeight');
      const alreadyPersistedRowBoundaryResize =
        pkg === 'affine-block-table' &&
        file === 'src/table-block.ts' &&
        before.startsWith('<tr class=') &&
        source.includes('sb-row-boundary-resize-v') &&
        source.includes('styleMap({ height: row.minHeight ?') &&
        source.includes('this.startRowResize(event, row.rowId');
      if (alreadyAlignedTableCellWithMergeRegions || alreadyPersistedRowBoundaryResize) continue;
      throw new Error(`${pkg}/${file}: patch context missing: ${before.slice(0, 100)}`);
    }
    source = source.replace(before, after);
  }
  fs.writeFileSync(target, source);
}

patch('affine-model', 'src/blocks/paragraph/paragraph-model.ts', [
  ["  type: ParagraphType;\n  text: Text;", "  type: ParagraphType;\n  textAlign?: 'left' | 'center' | 'right';\n  text: Text;"],
  ["    type: 'text',\n    text: internal.Text(),", "    type: 'text',\n    text: internal.Text(),\n    textAlign: undefined,"],
]);
patch('affine-block-paragraph', 'src/paragraph-block.ts', [
  ["            [TOGGLE_BUTTON_PARENT_CLASS]: true,\n          })}\n        >", "            [TOGGLE_BUTTON_PARENT_CLASS]: true,\n          })}\n          style=${styleMap({ textAlign: this.model.props.textAlign ?? 'left' })}\n        >"],
]);

// Zod v4 has the security fix for GHSA-mrhx-c7xc-m3w5, while BlockSuite 0.22.4
// uses the removed Zod v3 function-schema .args().returns() API. These schemas
// validate internal callbacks, so express them with the equivalent v4 API.
patch('store', 'src/model/block/zod.ts', [
  ["      .function()\n      .args(z.custom<InternalPrimitives>())\n      .returns(z.record(z.any()))", "      .function({ input: z.tuple([z.custom<InternalPrimitives>()]), output: z.record(z.string(), z.any()) })"],
  ["z.function().args().returns(z.custom<BlockModel>())", "z.function({ input: z.tuple([]), output: z.custom<BlockModel>() })"],
  ["    .function()\n    .args(z.custom<Map<string, unknown>>())\n    .returns(z.custom<BaseBlockTransformer>())", "    .function({ input: z.tuple([z.custom<Map<string, unknown>>()]), output: z.custom<BaseBlockTransformer>() })"],
]);
// Zod 4 differentiates `.or(z.undefined())` from `.optional()` when an
// object property is absent. The old deep-optional helper uses the former for
// unions, which rejects partial edit-props objects at runtime.
patch('affine-widget-linked-doc', 'src/view.ts', [
  ["      .function()\n      .args(\n        z.string(),\n        z.function().returns(z.void()),\n        z.custom<EditorHost>(),\n        z.custom<AffineInlineEditor>(),\n        z.instanceof(AbortSignal)\n      )\n      .returns(\n        z.union([\n          z.promise(z.array(z.custom<LinkedMenuGroup>())),\n          z.array(z.custom<LinkedMenuGroup>()),\n        ])\n      )", "      .function({ input: z.tuple([z.string(), z.function({ input: z.tuple([]), output: z.void() }), z.custom<EditorHost>(), z.custom<AffineInlineEditor>(), z.instanceof(AbortSignal)]), output: z.union([z.promise(z.array(z.custom<LinkedMenuGroup>())), z.array(z.custom<LinkedMenuGroup>())]) })"],
  ["      .function()\n      .args(\n        z.array(z.custom<LinkedMenuGroup>()),\n        z.string(),\n        z.string().nullable(),\n        z.custom<EditorHost>(),\n        z.custom<AffineInlineEditor>()\n      )\n      .returns(z.string().nullable())", "      .function({ input: z.tuple([z.array(z.custom<LinkedMenuGroup>()), z.string(), z.string().nullable(), z.custom<EditorHost>(), z.custom<AffineInlineEditor>()]), output: z.string().nullable() })"],
  ["z.function().returns(z.number())", "z.function({ input: z.tuple([]), output: z.number() })"],
]);
patch('affine-block-paragraph', 'src/view.ts', [
  ["z.function().args(z.instanceof(ParagraphBlockModel)).returns(z.string())", "z.function({ input: z.tuple([z.instanceof(ParagraphBlockModel)]), output: z.string() })"],
]);
patch('affine-block-database', 'src/view.ts', [
  ["    .function()\n    .args(z.instanceof(DatabaseBlockModel), z.custom<MenuOptions>())\n    .returns(z.custom<MenuOptions>())", "    .function({ input: z.tuple([z.instanceof(DatabaseBlockModel), z.custom<MenuOptions>()]), output: z.custom<MenuOptions>() })"],
]);
patch('affine-model', 'src/blocks/table/table-model.ts', [
  ["export interface TableRow {\n  rowId: string;", "export interface TableRow {\n  minHeight?: number;\n  rowId: string;"],
  ["export type TableCell = {\n  text: Text;", "export type TableCell = {\n  textAlign?: 'left' | 'center' | 'right';\n  verticalAlign?: 'top' | 'middle' | 'bottom';\n  text: Text;"],
]);
patch('affine-block-table', 'src/table-cell.ts', [
  ["  tdStyle() {\n    const columnWidth = this.virtualWidth$.value ?? this.column?.width;\n    const backgroundColor =\n      this.column?.backgroundColor ?? this.row?.backgroundColor ?? undefined;\n    return styleMap({\n      backgroundColor,\n      minWidth: columnWidth ? `${columnWidth}px` : `${DefaultColumnWidth}px`,\n      maxWidth: columnWidth ? `${columnWidth}px` : `${ColumnMaxWidth}px`,\n    });\n  }", "  private get storedCell() {\n    return this.row && this.column\n      ? this.dataManager.getCell(this.row.rowId, this.column.columnId)\n      : undefined;\n  }\n\n  tdStyle() {\n    const columnWidth = this.virtualWidth$.value ?? this.column?.width;\n    const backgroundColor =\n      this.column?.backgroundColor ?? this.row?.backgroundColor ?? undefined;\n    const rowMinHeight = this.row?.minHeight;\n    return styleMap({\n      backgroundColor,\n      minWidth: columnWidth ? `${columnWidth}px` : `${DefaultColumnWidth}px`,\n      maxWidth: columnWidth ? `${columnWidth}px` : `${ColumnMaxWidth}px`,\n      textAlign: this.storedCell?.textAlign ?? 'left',\n      verticalAlign: this.storedCell?.verticalAlign ?? 'top',\n      minHeight: rowMinHeight ? `${rowMinHeight}px` : undefined,\n    });\n  }"] ,
  ["            minHeight: '22px',\n            padding: '8px 12px',", "            minHeight: '22px',\n            height: 'auto',\n            width: '100%',\n            boxSizing: 'border-box',\n            padding: '8px 12px',\n            textAlign: this.storedCell?.textAlign ?? 'left',"],
]);
patch('affine-block-table', 'src/table-block.ts', [
  ["<tr class=${rowStyle} data-row-id=${row.rowId}>", "<tr class=${rowStyle} data-row-id=${row.rowId} style=${styleMap({ height: row.minHeight ? `${row.minHeight}px` : undefined })}>"] ,
]);
console.log('PATCHED · BlockSuite 0.22.4 textAlign + Zod 4 compatibility + Table cell alignment/row minHeight');
