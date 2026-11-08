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

const rangeMarker = '// wp5-native-slash-sync-range-v1';
const rangeAnchor = `      const inlineRange = inlineEditor.getInlineRange();
      if (!inlineRange) return;`;
if (!source.includes(rangeMarker)) {
  if (!source.includes(rangeAnchor)) throw new Error('Slash widget inline range anchor missing');
  source = source.replace(rangeAnchor, `${rangeAnchor}
      ${rangeMarker}
      inlineEditor.syncInlineRange(inlineRange);`);
}

const layerMarker = '// wp5-native-slash-modal-layer-v1';
const portalAnchor = '    container.append(slashMenu);';
if (!source.includes(layerMarker)) {
  if (!source.includes(portalAnchor)) throw new Error('Slash widget portal anchor missing');
  source = source.replace(portalAnchor, `    ${layerMarker}
    let layerSearch: Node | null = context.std.host;
    while (layerSearch) {
      if (layerSearch instanceof HTMLElement && layerSearch.matches('.blocksuite-resource-backdrop')) {
        const backdropLayer = Number.parseInt(getComputedStyle(layerSearch).zIndex, 10);
        if (Number.isFinite(backdropLayer)) slashMenu.style.setProperty('--affine-z-index-popover', String(backdropLayer + 1));
        break;
      }
      layerSearch = layerSearch.parentNode ?? (layerSearch instanceof ShadowRoot ? layerSearch.host : null);
    }
    container.append(slashMenu);`);
}
await fs.writeFile(file, source);
console.log('PATCHED · BlockSuite Slash menu localization, native range and modal layer');
