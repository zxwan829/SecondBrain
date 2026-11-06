import fs from 'node:fs/promises';

const file = new URL('../node_modules/@blocksuite/affine-widget-slash-menu/src/widget.ts', import.meta.url);
let source = await fs.readFile(file, 'utf8');
const importLine = "import { localizeSlashMenuItem } from '../../../../src/slash-locale.js';";
if (!source.includes(importLine)) {
  const anchor = "import { buildSlashMenuItems } from './utils';";
  if (!source.includes(anchor)) throw new Error('Slash widget import anchor missing');
  source = source.replace(anchor, `${anchor}\n${importLine}`);
}
const identity = 'configItemTransform: (item: SlashMenuItem) => SlashMenuItem = item => item;';
if (source.includes(identity)) {
  source = source.replace(identity, 'configItemTransform: (item: SlashMenuItem) => SlashMenuItem = localizeSlashMenuItem;');
} else if (!source.includes('= localizeSlashMenuItem;')) {
  throw new Error('Slash widget transform anchor missing');
}
await fs.writeFile(file, source);
console.log('PATCHED · BlockSuite Slash menu localization hook');
