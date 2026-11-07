import fs from 'node:fs/promises';

const file = new URL('../node_modules/@blocksuite/affine-gfx-shape/src/text/edgeless-shape-text-editor.ts', import.meta.url);
const source = await fs.readFile(file, 'utf8');
const marker = 'const id = mindmap.addNode(this.element.id);';
if (source.includes(marker)) {
  console.log('MindMap editing Tab patch already applied');
  process.exit(0);
}

const before = `        case 'Esc':
        case 'Tab': {
          evt.stopPropagation();
          (this.ownerDocument.activeElement as HTMLElement).blur();
          selection.set({
            elements: [this.element.id],
            editing: false,
          });
          break;
        }`;
const after = `        case 'Tab': {
          if (evt.isComposing || evt.keyCode === 229) return;
          evt.preventDefault();
          evt.stopPropagation();

          const mindmap = this.element.group;
          if (!(mindmap instanceof MindmapElementModel) || mindmap.isLocked()) {
            return;
          }

          const id = mindmap.addNode(this.element.id);
          const target = this.crud.getElementById(id);
          const rootId = this.std.store.root?.id;
          const edgeless = rootId ? this.std.view.getBlock(rootId) : null;
          (this.ownerDocument.activeElement as HTMLElement | null)?.blur();

          if (target instanceof ShapeElementModel && edgeless) {
            requestAnimationFrame(() => mountShapeTextEditor(target, edgeless));
          }
          break;
        }
        case 'Esc': {
          evt.stopPropagation();
          (this.ownerDocument.activeElement as HTMLElement).blur();
          selection.set({
            elements: [this.element.id],
            editing: false,
          });
          break;
        }`;

if (!source.includes(before)) throw new Error(`MindMap Tab patch anchor missing in ${file.pathname}`);
await fs.writeFile(file, source.replace(before, after));
console.log('Applied MindMap editing Tab branch-creation patch');
