import fs from 'node:fs/promises';

const replacements = {
  "name: 'Background color'": "name: '背景颜色'",
  "name: 'Default'": "name: '默认'",
  "name: 'Clear column style'": "name: '清除列样式'",
  "name: 'Insert Left'": "name: '左侧插入列'",
  "name: 'Insert Right'": "name: '右侧插入列'",
  "name: 'Move Left'": "name: '左移列'",
  "name: 'Move Right'": "name: '右移列'",
  "name: 'Duplicate'": "name: '复制'",
  "name: 'Clear column contents'": "name: '清空列内容'",
  "name: 'Clear row style'": "name: '清除行样式'",
  "name: 'Insert Above'": "name: '上方插入行'",
  "name: 'Insert Below'": "name: '下方插入行'",
  "name: 'Move Up'": "name: '上移行'",
  "name: 'Move Down'": "name: '下移行'",
  "name: 'Clear row contents'": "name: '清空行内容'",
  "name: 'Copy'": "name: '复制'",
  "name: 'Paste'": "name: '粘贴'",
  "name: 'Clear contents'": "name: '清空所选单元格'",
  "name: 'Delete'": "name: '删除'",
};

const menuFile = new URL('../node_modules/@blocksuite/affine-block-table/src/table-cell.ts', import.meta.url);
let menu = await fs.readFile(menuFile, 'utf8');
for (const [from, to] of Object.entries(replacements)) {
  if (menu.includes(from)) menu = menu.replaceAll(from, to);
}
const leftovers = Object.keys(replacements).filter(key => menu.includes(key));
if (leftovers.length) throw new Error(`Untranslated table menu labels remain: ${leftovers.join(', ')}`);
await fs.writeFile(menuFile, menu);

const colorFile = new URL('../node_modules/@blocksuite/affine-block-table/src/color.ts', import.meta.url);
let colors = await fs.readFile(colorFile, 'utf8');
for (const [from, to] of Object.entries({ Blue: '蓝色', Green: '绿色', Grey: '灰色', Orange: '橙色', Purple: '紫色', Red: '红色', Teal: '青色', Yellow: '黄色' })) {
  colors = colors.replaceAll(`name: '${from}'`, `name: '${to}'`);
}
await fs.writeFile(colorFile, colors);
console.log('Applied local Chinese labels to BlockSuite 0.22.4 table context menus and color choices');
