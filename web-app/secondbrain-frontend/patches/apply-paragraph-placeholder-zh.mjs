import fs from 'node:fs/promises';

const file = new URL('../node_modules/@blocksuite/affine-block-paragraph/src/view.ts', import.meta.url);
const replacements = new Map([
  ["text: \"Type '/' for commands\"", "text: \"输入“/”打开命令菜单\""],
  ["h1: 'Heading 1'", "h1: '一级标题'"],
  ["h2: 'Heading 2'", "h2: '二级标题'"],
  ["h3: 'Heading 3'", "h3: '三级标题'"],
  ["h4: 'Heading 4'", "h4: '四级标题'"],
  ["h5: 'Heading 5'", "h5: '五级标题'"],
  ["h6: 'Heading 6'", "h6: '六级标题'"],
]);

let source = await fs.readFile(file, 'utf8');
for (const [before, after] of replacements) {
  if (source.includes(before)) {
    source = source.replace(before, after);
  } else if (!source.includes(after)) {
    throw new Error(`Unable to apply paragraph placeholder localization: ${before}`);
  }
}
await fs.writeFile(file, source);
console.log('PATCHED · localized empty paragraph placeholders');
