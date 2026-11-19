import fs from 'node:fs/promises';

const targets = [
  '../node_modules/@blocksuite/affine-block-root/src/configs/toolbar.ts',
  '../node_modules/@blocksuite/affine-block-root/src/edgeless/configs/toolbar/more.ts',
];
const replacements = [
  ["label: 'Copy'", "label: '复制'"],
  ["label: 'Duplicate'", "label: '创建副本'"],
  ["label: 'Delete'", "label: '删除'"],
];

for (const relativePath of targets) {
  const file = new URL(relativePath, import.meta.url);
  let source = await fs.readFile(file, 'utf8');
  const untranslated = replacements.filter(([from]) => source.includes(from));
  for (const [from, to] of untranslated) source = source.replaceAll(from, to);
  const leftovers = replacements.filter(([from]) => source.includes(from));
  if (leftovers.length) throw new Error(`Toolbar labels remain untranslated in ${file.pathname}`);
  await fs.writeFile(file, source);
}

console.log('RECONSTRUCTED_ADAPTATION · localized selection toolbar actions');
