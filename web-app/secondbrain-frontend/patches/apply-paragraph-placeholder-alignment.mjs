import fs from 'node:fs/promises';

const file = new URL('../node_modules/@blocksuite/affine-block-paragraph/src/styles.ts', import.meta.url);
let source = await fs.readFile(file, 'utf8');
const marker = 'sb-paragraph-placeholder-first-line-alignment-v1';
if (!source.includes(marker)) {
  const before = `  .affine-paragraph-placeholder {
    position: absolute;
    display: none;
    max-width: 100%;
    overflow-x: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    left: 0;
    bottom: 0;`;
  const after = `  /* ${marker}: align placeholder with the active first-line caret box. */
  .affine-paragraph-placeholder {
    position: absolute;
    display: none;
    max-width: 100%;
    overflow-x: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    left: 1px;
    top: 0;
    bottom: auto;`;
  if (!source.includes(before)) throw new Error('Paragraph placeholder style anchor missing');
  source = source.replace(before, after);
  await fs.writeFile(file, source);
}
console.log('PATCHED · first-line placeholder alignment');
