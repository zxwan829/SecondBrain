import fs from 'node:fs/promises';

const file = new URL('../node_modules/@blocksuite/affine-components/src/toggle-button/toggle-button.ts', import.meta.url);
let source = await fs.readFile(file, 'utf8');
const marker = 'sb-heading-toggle-32px-v1';
if (!source.includes(marker)) {
  const anchor = `      width: 16px;\n      height: 16px;\n      top: calc((1em - 16px) / 2 + 5px);`;
  if (!source.includes(anchor)) throw new Error('Heading toggle size anchor missing');
  source = source.replace(anchor, `      /* ${marker}: doubled hierarchy toggle target and glyph. */\n      width: 32px;\n      height: 32px;\n      top: calc((1em - 32px) / 2 + 5px);`);
  source = source.replaceAll("width: '16px',\n          height: '16px',", "width: '32px',\n          height: '32px',");
  if (source.includes("width: '16px',\n          height: '16px',")) throw new Error('Heading toggle SVG sizing anchor missing');
  await fs.writeFile(file, source);
}
console.log('PATCHED · hierarchy toggle is 32px and centered on the same text line');
