import fs from 'node:fs/promises';
import path from 'node:path';

const root = path.resolve('.');
const replacements = [
  ['node_modules/@blocksuite/affine-block-database/src/configs/slash-menu.ts', "name: 'Table View'", "name: '表格视图'"],
  ['node_modules/@blocksuite/affine-block-database/src/configs/slash-menu.ts', "description: 'Display items in a table format.'", "description: '以表格方式展示记录。'"],
  ['node_modules/@blocksuite/affine-block-database/src/configs/slash-menu.ts', "caption: 'Table View'", "caption: '表格视图'"],
  ['node_modules/@blocksuite/affine-block-database/src/configs/slash-menu.ts', "name: 'Kanban View'", "name: '看板视图'"],
  ['node_modules/@blocksuite/affine-block-database/src/configs/slash-menu.ts', "description: 'Visualize data in a dashboard.'", "description: '以看板方式展示和管理记录。'"],
  ['node_modules/@blocksuite/affine-block-database/src/configs/slash-menu.ts', "caption: 'Kanban View'", "caption: '看板视图'"],
  ['node_modules/@blocksuite/affine-block-database/src/database-block.ts', "placeholder: 'Database title'", "placeholder: '数据库名称'"],
  ['node_modules/@blocksuite/affine-block-database/src/database-block.ts', "name: 'Copy'", "name: '复制'"],
  ['node_modules/@blocksuite/affine-block-database/src/database-block.ts', "toast(this.host, 'Copied to clipboard')", "toast(this.host, '已复制到剪贴板')"],
  ['node_modules/@blocksuite/affine-block-database/src/database-block.ts', "name: 'Delete Database'", "name: '删除数据库'"],
  ['node_modules/@blocksuite/data-view/src/view-presets/kanban/define.ts', "defaultName: 'Kanban View'", "defaultName: '看板视图'"],
  ['node_modules/@blocksuite/data-view/src/widget-presets/views-bar/views-view.ts', "name: `Create ${v.model.defaultName}`", "name: `创建${v.model.defaultName}`"],
  ['node_modules/@blocksuite/data-view/src/core/group-by/renderer/string-group.ts', '<div>Ungroups</div>', '<div>未分组</div>'],
  ['node_modules/@blocksuite/data-view/src/core/group-by/renderer/number-group.ts', '<div>Ungroups</div>', '<div>未分组</div>'],
  ['node_modules/@blocksuite/data-view/src/core/group-by/renderer/select-group.ts', '\n        Ungroups\n', '\n        未分组\n'],
];

for (const [relative, from, to] of replacements) {
  const file = path.join(root, relative);
  let source = await fs.readFile(file, 'utf8');
  if (source.includes(to)) continue;
  if (!source.includes(from)) throw new Error(`Database UX localization anchor missing: ${relative}: ${from}`);
  source = source.replaceAll(from, to);
  await fs.writeFile(file, source);
}

const viewBar = path.join(root, 'node_modules/@blocksuite/data-view/src/widget-presets/views-bar/views-view.ts');
let source = await fs.readFile(viewBar, 'utf8');
const helper = `const localizedDatabaseViewName = (name: string | undefined) => {
  if (name === 'Kanban View') return '看板视图';
  if (name === 'Table View') return '表格视图';
  return name ?? '';
};
`;
if (!source.includes('const localizedDatabaseViewName =')) {
  const anchor = "import { WidgetBase } from '../../core/widget/widget-base.js';\n";
  if (!source.includes(anchor)) throw new Error('Database view name localization import anchor missing');
  source = source.replace(anchor, `${anchor}\n${helper}`);
}
source = source.replace("name: view.name$.value ?? '',", "name: localizedDatabaseViewName(view.name$.value),");
source = source.replace("label: () => html`${view.name$.value}`,", "label: () => html`${localizedDatabaseViewName(view.name$.value)}`," );
source = source.replace('<div class="name">${view?.name}</div>', '<div class="name">${localizedDatabaseViewName(view?.name)}</div>');
await fs.writeFile(viewBar, source);

const toolbarRoot = path.join(root, 'node_modules/@blocksuite/data-view/src/widget-presets/tools/presets');
const tooltips = [
  ['filter/filter.ts', '${FilterIcon()}\n    </div>', '${FilterIcon()}\n      <affine-tooltip>筛选当前视图中的记录</affine-tooltip>\n    </div>'],
  ['sort/sort.ts', '${SortIcon()}\n    </div>', '${SortIcon()}\n      <affine-tooltip>排序当前视图中的记录</affine-tooltip>\n    </div>'],
  ['search/search.ts', '<div class="affine-database-search-input-icon">${SearchIcon()}</div>', '<div class="affine-database-search-input-icon">${SearchIcon()}<affine-tooltip>搜索当前数据库视图中的记录</affine-tooltip></div>'],
  ['view-options/view-options.ts', '${MoreHorizontalIcon()}\n    </div>', '${MoreHorizontalIcon()}\n      <affine-tooltip>数据库视图选项</affine-tooltip>\n    </div>'],
];
for (const [relative, from, to] of tooltips) {
  const file = path.join(toolbarRoot, relative);
  let text = await fs.readFile(file, 'utf8');
  if (!text.includes(to)) {
    if (!text.includes(from)) throw new Error(`Database tooltip anchor missing: ${relative}`);
    text = text.replace(from, to);
    await fs.writeFile(file, text);
  }
}

console.log('PATCHED · localized Kanban and database menus, groups, view names, and toolbar hover hints');
