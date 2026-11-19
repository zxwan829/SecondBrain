import fs from 'node:fs/promises';

const replacements = [
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/define.ts', "defaultName: 'Table View'", "defaultName: '表格视图'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/tools/presets/table-add-row/add-row.ts', 'New Record', '新建记录'],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc/group.ts', 'New Record', '新建记录'],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/mobile/group.ts', 'New Record', '新建记录'],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc-virtual/group/bottom/group-footer.ts', 'New Record', '新建记录'],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/stats/column-stats-column.ts', 'Calculate', '计算'],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc-virtual/group/bottom/stats/column-stats-column.ts', 'Calculate', '计算'],
  ['../node_modules/@blocksuite/affine-block-database/src/properties/title/define.ts', "name: 'Title'", "name: '标题'"],
  ['../node_modules/@blocksuite/affine-block-database/src/components/title/index.ts', "content: 'Untitled'", "content: '未命名数据库'"],
  ['../node_modules/@blocksuite/affine-block-database/src/components/title/index.ts', '>Untitled</div>', '>未命名数据库</div>'],
  ['../node_modules/@blocksuite/affine-block-database/src/detail-panel/block-renderer.ts', "content: 'Untitled'", "content: '未命名数据库'"],
  ['../node_modules/@blocksuite/affine-block-database/src/properties/link/cell-renderer.ts', "title || 'Untitled'", "title || '未命名记录'"],
  ['../node_modules/@blocksuite/affine-block-data-view/src/data-view-block.ts', "placeholder: 'Untitled'", "placeholder: '未命名数据库'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc/header/database-header-column.ts', "name: 'Number Format'", "name: '数字格式'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc/header/database-header-column.ts', "name: 'Hide In View'", "name: '在此视图中隐藏'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc/header/database-header-column.ts', "name: 'Filter'", "name: '筛选'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc/header/database-header-column.ts', "name: 'Sort Ascending'", "name: '升序排序'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc/header/database-header-column.ts', "name: 'Sort Descending'", "name: '降序排序'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc/header/database-header-column.ts', "name: 'Insert Left Column'", "name: '在左侧插入列'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc/header/database-header-column.ts', "name: 'Insert Right Column'", "name: '在右侧插入列'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc/header/database-header-column.ts', "name: 'Move Left'", "name: '左移'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc/header/database-header-column.ts', "name: 'Move Right'", "name: '右移'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc/header/database-header-column.ts', "name: 'Duplicate'", "name: '复制'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc/header/database-header-column.ts', "name: 'Delete'", "name: '删除'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc/menu.ts', "name: 'Copy'", "name: '复制'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc/menu.ts', "name: 'Delete Rows'", "name: '删除记录'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc/menu.ts', "name: 'Expand Row'", "name: '展开记录'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc/menu.ts', "name: 'Insert Before'", "name: '在前方插入'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc/menu.ts', "name: 'Insert After'", "name: '在后方插入'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/table/pc/menu.ts', "name: 'Delete Row'", "name: '删除记录'"],
];

for (const [relative, from, to] of replacements) {
  const file = new URL(relative, import.meta.url);
  let source = await fs.readFile(file, 'utf8');
  if (source.includes(from)) source = source.replaceAll(from, to);
  else if (!source.includes(to)) throw new Error(`Database localization anchor missing in ${file.pathname}: ${from}`);
  await fs.writeFile(file, source);
}

console.log('PATCHED · localized common Database labels, view title, record action, and calculations');
