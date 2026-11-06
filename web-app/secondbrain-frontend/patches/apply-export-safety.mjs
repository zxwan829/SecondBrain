import fs from 'node:fs/promises';

const tableRoot = 'node_modules/@blocksuite/affine-block-table/src/adapters';
const markdownPath = `${tableRoot}/markdown.ts`;
const htmlPath = `${tableRoot}/html.ts`;
const mdMarker = 'sb-merged-table-markdown-fail-closed-v1';
const htmlMarker = 'sb-merged-table-html-spans-v1';

let markdown = await fs.readFile(markdownPath, 'utf8');
if (!markdown.includes(mdMarker)) {
  const anchor = '      const { columns, rows, cells } = o.node\n        .props as unknown as TableBlockPropsSerialized;\n';
  const replacement = `      // ${mdMarker}: pipe tables cannot encode merged geometry safely.\n      const mergeRegions = (o.node.props as { mergeRegions?: Record<string, unknown> }).mergeRegions;\n      if (mergeRegions && Object.keys(mergeRegions).length > 0) {\n        throw new Error('Markdown 导出已停止：此表包含合并单元格，Markdown 表格无法保留合并结构。请改用 HTML 导出。原文档未修改。');\n      }\n      const { columns, rows, cells } = o.node\n        .props as unknown as TableBlockPropsSerialized;\n`;
  if (!markdown.includes(anchor)) throw new Error('Markdown adapter insertion point not found');
  markdown = markdown.replace(anchor, replacement);
  await fs.writeFile(markdownPath, markdown);
}

let html = await fs.readFile(htmlPath, 'utf8');
if (!html.includes(htmlMarker)) {
  const anchor = '      const { columns, rows, cells } = o.node\n        .props as unknown as TableBlockPropsSerialized;\n';
  const replacement = `      // ${htmlMarker}: emit merge spans and retain covered-cell rich-text payloads as explicit metadata.\n      const props = o.node.props as TableBlockPropsSerialized & { mergeRegions?: Record<string, { anchorRowId: string; anchorColumnId: string; rowIds: string[]; columnIds: string[] }> };\n      const { columns, rows, cells } = props;\n`;
  if (!html.includes(anchor)) throw new Error('HTML adapter insertion point not found');
  html = html.replace(anchor, replacement);
  const tableAnchor = '      const table = processTable(columns, rows, cells);\n';
  const tableReplacement = `      const table = processTable(columns, rows, cells);\n      const orderedRows = Object.values(rows).sort((a, b) => a.order.localeCompare(b.order));\n      const orderedColumns = Object.values(columns).sort((a, b) => a.order.localeCompare(b.order));\n      const mergeAt = new Map<string, { rowSpan: number; colSpan: number; covered: unknown[]; region: unknown }>();\n      const covered = new Set<string>();\n      for (const [regionId, region] of Object.entries(props.mergeRegions ?? {})) {\n        const rowIndexes = region.rowIds.map(id => orderedRows.findIndex(row => row.rowId === id));\n        const columnIndexes = region.columnIds.map(id => orderedColumns.findIndex(column => column.columnId === id));\n        const valid = rowIndexes.length > 0 && columnIndexes.length > 0 && rowIndexes.every(index => index >= 0) && columnIndexes.every(index => index >= 0);\n        if (!valid) throw new Error('HTML 导出已停止：合并区域引用了不存在的单元格；原文档未修改。');\n        const minRow = Math.min(...rowIndexes), minColumn = Math.min(...columnIndexes);\n        const sortedRowIndexes = [...rowIndexes].sort((a, b) => a - b);\n        const sortedColumnIndexes = [...columnIndexes].sort((a, b) => a - b);\n        if (sortedRowIndexes.some((value, index) => value !== minRow + index) || sortedColumnIndexes.some((value, index) => value !== minColumn + index) || region.anchorRowId !== orderedRows[minRow]?.rowId || region.anchorColumnId !== orderedColumns[minColumn]?.columnId) {\n          throw new Error('HTML 导出已停止：合并区域不是有效矩形或锚点不匹配；原文档未修改。');\n        }\n        const rowSpan = Math.max(...rowIndexes) - minRow + 1, colSpan = Math.max(...columnIndexes) - minColumn + 1;\n        const anchorKey = orderedRows[minRow]?.rowId + ':' + orderedColumns[minColumn]?.columnId;\n        const coveredPayload: unknown[] = [];\n        for (const rowId of region.rowIds) for (const columnId of region.columnIds) {\n          const key = rowId + ':' + columnId;\n          if (key === anchorKey) continue;\n          covered.add(key);\n          coveredPayload.push({ rowId, columnId, text: cells[key]?.text ?? null });\n        }\n        mergeAt.set(anchorKey, { rowSpan, colSpan, covered: coveredPayload, region: { id: regionId, rowIds: region.rowIds, columnIds: region.columnIds } });\n      }\n`;
  if (!html.includes(tableAnchor)) throw new Error('HTML table insertion point not found');
  html = html.replace(tableAnchor, tableReplacement);
  const rowAnchor = `      const tableBodyAst: Element = {\n        type: 'element',\n        tagName: 'tbody',\n        properties: Object.create(null),\n        children: table.rows.map(v => {\n          return createAstTableRow(\n            v.cells.map(cell => {\n              return createAstTableCell(\n                typeof cell.value === 'string'\n                  ? [{ type: 'text', value: cell.value }]\n                  : deltaConverter.deltaToAST(cell.value.delta)\n              );\n            })\n          );\n        }),\n      };`;
  const rowReplacement = `      let rowIndex = 0;\n      const tableBodyAst: Element = {\n        type: 'element',\n        tagName: 'tbody',\n        properties: Object.create(null),\n        children: table.rows.map(v => {\n          const currentRow = orderedRows[rowIndex++];\n          let columnIndex = 0;\n          return createAstTableRow(\n            v.cells.flatMap(cell => {\n              const currentColumn = orderedColumns[columnIndex++];\n              const key = currentRow?.rowId + ':' + currentColumn?.columnId;\n              if (covered.has(key)) return [];\n              const merge = mergeAt.get(key);\n              const node = createAstTableCell(\n                typeof cell.value === 'string'\n                  ? [{ type: 'text', value: cell.value }]\n                  : deltaConverter.deltaToAST(cell.value.delta)\n              );\n              if (merge) {\n                node.properties = {\n                  rowspan: merge.rowSpan,\n                  colspan: merge.colSpan,\n                  'data-sb-merge-region': JSON.stringify(merge.region),\n                  'data-sb-covered-cell-data': JSON.stringify(merge.covered),\n                };\n              }\n              return [node];\n            })\n          );\n        }),\n      };`;
  if (!html.includes(rowAnchor)) throw new Error('HTML row rendering insertion point not found');
  html = html.replace(rowAnchor, rowReplacement);
  await fs.writeFile(htmlPath, html);
}

console.log('PATCHED · merged tables fail closed in Markdown and preserve HTML spans plus covered-cell rich text metadata');
