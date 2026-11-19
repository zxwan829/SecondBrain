import fs from 'node:fs/promises';

const marker = 'sb-select-cell-close-reentrancy-guard-v1';
const files = [
  'node_modules/@blocksuite/data-view/src/property-presets/select/cell-renderer.ts',
  'node_modules/@blocksuite/data-view/src/property-presets/multi-select/cell-renderer.ts',
];

for (const file of files) {
  let source = await fs.readFile(file, 'utf8');
  if (source.includes(marker)) continue;
  if (!source.includes('  _editComplete = () => {\n    this.selectCurrentCell(false);\n  };')) {
    throw new Error(`Unsupported BlockSuite 0.22.4 cell-close source: ${file}`);
  }
  source = source.replace(
    /  closePopup\?: \(\) => void;\n  private readonly popTagSelect = \(\) => \{/,
    `  closePopup?: () => void;\n  private completing = false; // ${marker}\n  private readonly popTagSelect = () => {`
  );
  source = source.replace(
    '  _editComplete = () => {\n    this.selectCurrentCell(false);\n  };',
    `  _editComplete = () => {\n    if (this.completing) return;\n    this.completing = true;\n    // Clear before changing selection: beforeExitEditingMode closes the popover,\n    // whose onComplete callback can otherwise re-enter this method recursively.\n    this.closePopup = undefined;\n    this.selectCurrentCell(false);\n  };`
  );
  source = source.replace(
    '  override afterEnterEditingMode() {\n    if (!this.closePopup) {',
    '  override afterEnterEditingMode() {\n    this.completing = false;\n    if (!this.closePopup) {'
  );
  const closeStart = source.indexOf('  override beforeExitEditingMode() {');
  const closeEnd = source.indexOf('\n  }', closeStart) + 4;
  if (closeStart < 0 || closeEnd < 4) throw new Error(`Missing beforeExitEditingMode: ${file}`);
  source = source.slice(0, closeStart) + `  override beforeExitEditingMode() {\n    const closePopup = this.closePopup;\n    this.closePopup = undefined;\n    closePopup?.();\n  }` + source.slice(closeEnd);
  await fs.writeFile(file, source);
}

console.log('Applied native Select/Multi-select popover close reentrancy guard.');
