import fs from 'node:fs/promises';

const root = new URL('../node_modules/@blocksuite/data-view/src/widget-presets/tools/presets/', import.meta.url);
const replacements = [
  ['search/search.ts', '<label class="${searchToolClassMap}" @click="${this._clickSearch}">', '<label class="${searchToolClassMap}" title="搜索当前数据库视图中的记录" aria-label="搜索当前数据库视图中的记录" @click="${this._clickSearch}">'],
  ['search/search.ts', 'placeholder="Search..."', 'placeholder="搜索当前视图"'],
  ['filter/filter.ts', '<div\n      @click="${this.clickFilter}"', '<div role="button" tabindex="0" title="筛选当前视图中的记录" aria-label="筛选当前视图中的记录"\n      @click="${this.clickFilter}"'],
  ['sort/sort.ts', '<div\n      @click="${this.clickSort}"', '<div role="button" tabindex="0" title="排序当前视图中的记录" aria-label="排序当前视图中的记录"\n      @click="${this.clickSort}"'],
  ['view-options/view-options.ts', 'class="affine-database-toolbar-item more-action"\n      @click=', 'class="affine-database-toolbar-item more-action" title="数据库视图选项" aria-label="数据库视图选项"\n      @click='],
];
for (const [path, from, to] of replacements) {
  const file = new URL(path, root);
  let source = await fs.readFile(file, 'utf8');
  if (source.includes(from)) source = source.replace(from, to);
  else if (!source.includes(to)) throw new Error(`Database toolbar tooltip anchor missing: ${path}: ${from}`);
  await fs.writeFile(file, source);
}
const addRowFile = new URL('table-add-row/add-row.ts', root);
const addRowSource = await fs.readFile(addRowFile, 'utf8');
const normalizedAddRowSource = addRowSource.replace(
  /class="affine-database-toolbar-item new-record"(?:(?:\s+title="[^"]*")|(?:\s+aria-label="[^"]*"))*/g,
  'class="affine-database-toolbar-item new-record" title="在当前数据库视图中新建记录" aria-label="新建记录"'
);
if (normalizedAddRowSource !== addRowSource) {
  await fs.writeFile(addRowFile, normalizedAddRowSource);
}
console.log('PATCHED · localized, accessible Database toolbar tooltips');
