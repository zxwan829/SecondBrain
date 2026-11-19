import fs from 'node:fs/promises';

const replacements = [
  ['node_modules/@blocksuite/affine-inline-preset/src/command/config.ts', {
    "name: 'Bold'": "name: '加粗'", "name: 'Italic'": "name: '斜体'",
    "name: 'Underline'": "name: '下划线'", "name: 'Strikethrough'": "name: '删除线'",
    "name: 'Code'": "name: '行内代码'", "name: 'Link'": "name: '链接'",
  }],
  ['node_modules/@blocksuite/affine-rich-text/src/conversion.ts', {
    "name: 'Text'": "name: '正文'", "name: 'Heading 1'": "name: '一级标题'",
    "name: 'Heading 2'": "name: '二级标题'", "name: 'Heading 3'": "name: '三级标题'",
    "name: 'Heading 4'": "name: '四级标题'", "name: 'Heading 5'": "name: '五级标题'",
    "name: 'Heading 6'": "name: '六级标题'", "name: 'Bulleted List'": "name: '项目符号列表'",
    "name: 'Numbered List'": "name: '编号列表'", "name: 'To-do List'": "name: '待办事项'",
    "name: 'Code Block'": "name: '代码块'", "name: 'Quote'": "name: '引用'",
    "name: 'Divider'": "name: '分隔线'",
  }],
  ['node_modules/@blocksuite/affine-block-root/src/configs/toolbar.ts', {
    'aria-label="Conversions"': 'aria-label="格式转换"',
    "'Turn into'": "'转换为'", "tooltip: 'Create Table'": "tooltip: '创建表格'",
    "tooltip: 'Create Linked Doc'": "tooltip: '创建关联文档'",
  }],
];

for (const [relativePath, map] of replacements) {
  const file = new URL(`../${relativePath}`, import.meta.url);
  let source = await fs.readFile(file, 'utf8');
  for (const [from, to] of Object.entries(map)) source = source.replaceAll(from, to);
  await fs.writeFile(file, source);
}
console.log('PATCHED · localized BlockSuite inline-format and conversion toolbars');
