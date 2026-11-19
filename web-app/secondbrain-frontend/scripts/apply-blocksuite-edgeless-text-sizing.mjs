import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const pkg = path.join(root, 'node_modules/@blocksuite/affine-block-edgeless-text');
const manifest = JSON.parse(fs.readFileSync(path.join(pkg, 'package.json'), 'utf8'));
if (manifest.version !== '0.22.4') throw new Error(`Unsupported Edgeless Text version: ${manifest.version}`);

const edits = [
  ['src/edgeless-text-block.ts', `  private _updateH() {
    const bound = Bound.deserialize(this.model.xywh);
    const rect = this._textContainer.getBoundingClientRect();
    bound.h = rect.height / this.gfx.viewport.zoom;

    this.store.updateBlock(this.model, {
      xywh: bound.serialize(),
    });
  }`, `  private _updateH() {
    const bound = Bound.deserialize(this.model.xywh);
    const style = getComputedStyle(this._textContainer);
    const verticalInsets = Number.parseFloat(style.borderTopWidth) + Number.parseFloat(style.borderBottomWidth)
      + Number.parseFloat(style.paddingTop) + Number.parseFloat(style.paddingBottom);
    const rect = this.childrenContainer.getBoundingClientRect();
    const nextHeight = (rect.height + verticalInsets) / this.gfx.viewport.zoom;
    if (Math.abs(nextHeight - bound.h) < 0.01) return;
    bound.h = nextHeight;

    this.store.updateBlock(this.model, {
      xywh: bound.serialize(),
    });
  }`],
  ['dist/edgeless-text-block.js', `        _updateH() {
            const bound = Bound.deserialize(this.model.xywh);
            const rect = this._textContainer.getBoundingClientRect();
            bound.h = rect.height / this.gfx.viewport.zoom;
            this.store.updateBlock(this.model, {
                xywh: bound.serialize(),
            });
        }`, `        _updateH() {
            const bound = Bound.deserialize(this.model.xywh);
            const style = getComputedStyle(this._textContainer);
            const verticalInsets = Number.parseFloat(style.borderTopWidth) + Number.parseFloat(style.borderBottomWidth) + Number.parseFloat(style.paddingTop) + Number.parseFloat(style.paddingBottom);
            const rect = this.childrenContainer.getBoundingClientRect();
            const nextHeight = (rect.height + verticalInsets) / this.gfx.viewport.zoom;
            if (Math.abs(nextHeight - bound.h) < 0.01) return;
            bound.h = nextHeight;
            this.store.updateBlock(this.model, {
                xywh: bound.serialize(),
            });
        }`],
];

const styleAnchor = `      text-align: var(--edgeless-text-text-align);
    }
  `;
const styleReplacement = `      text-align: var(--edgeless-text-text-align);
    }

    .edgeless-text-block-container .affine-block-children-container rich-text,
    .edgeless-text-block-container .affine-block-children-container .inline-editor {
      height: auto;
    }
  `;

for (const [relative, before, after] of edits) {
  const target = path.join(pkg, relative);
  let source = fs.readFileSync(target, 'utf8');
  if (source.includes(after)) continue;
  if (!source.includes(before)) throw new Error(`Edgeless Text sizing patch context missing: ${relative}`);
  source = source.replace(before, after);
  fs.writeFileSync(target, source);
}

for (const relative of ['src/edgeless-text-block.ts', 'dist/edgeless-text-block.js']) {
  const target = path.join(pkg, relative);
  let source = fs.readFileSync(target, 'utf8');
  if (source.includes(styleReplacement)) continue;
  if (!source.includes(styleAnchor)) throw new Error(`Edgeless Text intrinsic-height style anchor missing: ${relative}`);
  source = source.replace(styleAnchor, styleReplacement);
  fs.writeFileSync(target, source);
}
