import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const root = new URL('../', import.meta.url);
const source = await readFile(new URL('src/desktop-page-plus.ts', root), 'utf8');
const main = await readFile(new URL('src/archive-rich-page-runtime.ts', root), 'utf8');

assert.match(main, /CanvasRefSlashExtension, CanvasRefPlusExtension, DesktopPageLeadingPlusExtension/,
  'Page view must register the shared Slash and desktop row controls');
assert.match(source, /this\.std\.get\(SlashMenuExtension\)\.config/,
  'Desktop plus must read the same SlashMenuExtension registry');
assert.match(source, /this\.openSlashMenu\(\);[\s\S]*?private openSlashMenu\(\)/,
  'Pointer and keyboard activation must use one menu-opening path');
assert.match(source, /inlineEditor\.setInlineRange\(menuRange\);[\s\S]*?inlineEditor\.syncInlineRange\(menuRange\)/,
  'The logical caret must be synchronized into a native DOM range before mounting the native menu');
assert.match(source, /new SlashMenu\(inlineEditor, controller\)[\s\S]*?document\.body\.append\(menu\)/,
  'The native BlockSuite Slash menu renderer must remain in use');
assert.match(source, /this\.store\.moveBlocks\(\[sourceModel\], sourceParent, targetModel, target\.before\)/,
  'The row grip must reorder actual Store models');
assert.match(source, /sourceParent\.id !== targetParent\?\.id/,
  'Reordering must stay within a single parent');
assert.match(source, /pointercancel[\s\S]*?onPointerCancel/,
  'Canceled pointer drags must release their transient state');

console.log('PASS · desktop plus shares Slash registry, restores native selection, and preserves model-backed drag guards');
