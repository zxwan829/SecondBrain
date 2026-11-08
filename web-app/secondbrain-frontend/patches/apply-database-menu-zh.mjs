import fs from 'node:fs/promises';

const replacements = [
  ['../node_modules/@blocksuite/data-view/src/core/filter/add-filter.ts', "text: 'New filter'", "text: '新建筛选'"],
  ['../node_modules/@blocksuite/data-view/src/core/filter/add-filter.ts', "name: 'Add filter group'", "name: '添加筛选分组'"],
  ['../node_modules/@blocksuite/data-view/src/core/sort/add-sort.ts', "text: 'New sort'", "text: '新建排序'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/quick-setting-bar/filter/group-panel-view.ts', "name: 'Add filter'", "name: '添加筛选'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/quick-setting-bar/filter/group-panel-view.ts', "name: 'Add filter group'", "name: '添加筛选分组'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/quick-setting-bar/filter/group-panel-view.ts', "name: 'And'", "name: '并且'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/quick-setting-bar/filter/group-panel-view.ts', "name: 'Or'", "name: '或者'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/quick-setting-bar/filter/group-panel-view.ts', "text: 'Filter group'", "text: '筛选分组'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/quick-setting-bar/filter/group-panel-view.ts', "name: 'Duplicate'", "name: '复制'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/quick-setting-bar/filter/group-panel-view.ts', "name: 'Delete'", "name: '删除'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/quick-setting-bar/filter/root-panel-view.ts', "text: 'Filters'", "text: '筛选条件'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/quick-setting-bar/filter/root-panel-view.ts', "name: 'Duplicate'", "name: '复制'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/quick-setting-bar/filter/root-panel-view.ts', "name: 'Delete'", "name: '删除'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/quick-setting-bar/filter/condition-view.ts', "name: 'Delete'", "name: '删除'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/quick-setting-bar/sort/root-panel.ts', "'Descending'", "'降序'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/quick-setting-bar/sort/root-panel.ts', "'Ascending'", "'升序'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/quick-setting-bar/sort/root-panel.ts', "name: 'Add sort'", "name: '添加排序'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/quick-setting-bar/sort/root-panel.ts', "name: 'Delete'", "name: '删除'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/quick-setting-bar/sort/root-panel.ts', 'This rule is invalid, click to delete', '此排序条件无效，点击删除'],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/tools/presets/view-options/view-options.ts', "name: 'Properties'", "name: '属性'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/tools/presets/view-options/view-options.ts', "name: 'Filter'", "name: '筛选'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/tools/presets/view-options/view-options.ts', "name: 'Sort'", "name: '排序'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/tools/presets/view-options/view-options.ts', "text: 'Sort'", "text: '排序'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/tools/presets/view-options/view-options.ts', "name: 'Group'", "name: '分组'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/tools/presets/view-options/view-options.ts', "placeholder: 'View name'", "placeholder: '视图名称'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/tools/presets/view-options/view-options.ts', "name: 'Layout'", "name: '布局'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/tools/presets/view-options/view-options.ts', "text: 'Layout'", "text: '布局'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/tools/presets/view-options/view-options.ts', "name: 'Duplicate'", "name: '复制'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/tools/presets/view-options/view-options.ts', "name: 'Delete'", "name: '删除'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/tools/presets/view-options/view-options.ts', "text: 'View settings'", "text: '视图设置'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/tools/presets/view-options/view-options.ts', '${view.type}', "${view.type === 'table' ? '表格' : view.type === 'kanban' ? '看板' : view.type}"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/views-bar/views-view.ts', "placeholder: 'View name'", "placeholder: '视图名称'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/views-bar/views-view.ts', "name: 'Edit View'", "name: '编辑视图'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/views-bar/views-view.ts', "name: 'Move Left'", "name: '左移'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/views-bar/views-view.ts', "name: 'Move Right'", "name: '右移'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/views-bar/views-view.ts', "name: 'Duplicate'", "name: '复制'"],
  ['../node_modules/@blocksuite/data-view/src/widget-presets/views-bar/views-view.ts', "name: 'Delete'", "name: '删除'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/kanban/pc/menu.ts', "name: 'Expand Card'", "name: '展开卡片'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/kanban/pc/menu.ts', "name: 'Move To'", "name: '移动到'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/kanban/pc/menu.ts', "name: 'Insert Before'", "name: '在前方插入'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/kanban/pc/menu.ts', "name: 'Insert After'", "name: '在后方插入'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/kanban/pc/menu.ts', "name: 'Delete Card'", "name: '删除卡片'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/kanban/pc/group.ts', "name: 'Ungroup'", "name: '取消分组'"],
  ['../node_modules/@blocksuite/data-view/src/view-presets/kanban/pc/group.ts', "name: 'Delete Cards'", "name: '删除卡片'"],
];

for (const [relative, from, to] of replacements) {
  const file = new URL(relative, import.meta.url);
  let source = await fs.readFile(file, 'utf8');
  if (source.includes(from)) source = source.replaceAll(from, to);
  else if (!source.includes(to)) throw new Error(`Database menu localization anchor missing in ${file.pathname}: ${from}`);
  await fs.writeFile(file, source);
}

console.log(`PATCHED · localized ${replacements.length} frequent Database menu labels`);
