import fs from 'node:fs/promises';

const viewportFile = new URL('../node_modules/@blocksuite/std/src/gfx/viewport.ts', import.meta.url);
let viewport = await fs.readFile(viewportFile, 'utf8');
if (!viewport.includes('getBoundingClientRect().left ?? this._left')) {
  if (!viewport.includes('  get left() {\n    return this._left;')) throw new Error('Viewport.left patch anchor missing');
  if (!viewport.includes('  get top() {\n    return this._top;')) throw new Error('Viewport.top patch anchor missing');
  viewport = viewport
    .replace('  get left() {\n    return this._left;\n  }', '  get left() {\n    // Page scrolling moves the shell without resizing it, so ResizeObserver can leave this cached offset stale.\n    return this._shell?.getBoundingClientRect().left ?? this._left;\n  }')
    .replace('  get top() {\n    return this._top;\n  }', '  get top() {\n    // Use the live client-space shell origin for hit testing after page or container scroll.\n    return this._shell?.getBoundingClientRect().top ?? this._top;\n  }');
  await fs.writeFile(viewportFile, viewport);
}

// The integrated editors already mount via append(root); no standalone App mutation.
console.log('Applied live viewport-hit-test fix; standalone duplicate mount is not imported');
