import fs from 'node:fs/promises';

const file = new URL('../node_modules/@blocksuite/affine-block-root/src/configs/toolbar.ts', import.meta.url);
const marker = 'const paragraphAlignmentActionGroup = {';
const group = `${marker}
  id: 'd.paragraph-alignment',
  when: ({ flags }) => flags.isText(),
  actions: [
    { id: 'align-left', icon: TextAlignLeftIcon(), tooltip: '左对齐', run: alignSelectedParagraphs('left') },
    { id: 'align-center', icon: TextAlignCenterIcon(), tooltip: '居中对齐', run: alignSelectedParagraphs('center') },
    { id: 'align-right', icon: TextAlignRightIcon(), tooltip: '右对齐', run: alignSelectedParagraphs('right') },
  ],
} as const satisfies ToolbarActionGroup;

function alignSelectedParagraphs(textAlign: 'left' | 'center' | 'right') {
  return ({ chain, store }: any) => {
    store.captureSync();
    chain
      .pipe(getTextSelectionCommand)
      .pipe(getSelectedBlocksCommand, { types: ['text'], mode: 'highest' })
      .pipe((ctx: any, next: () => void) => {
        const paragraphs = (ctx.selectedBlocks ?? []).filter(
          (block: any) => block.model.flavour === 'affine:paragraph'
        );
        for (const block of paragraphs) store.updateBlock(block.model, { textAlign });
        if (paragraphs.length) next();
      })
      .run();
    store.captureSync();
  };
}
`;

let source = await fs.readFile(file, 'utf8');
source = source.replace(
  "const inlineTextActionGroup = {\n  id: 'b.inline-text',\n  when: ({ chain }) => isFormatSupported(chain).run()[0],",
  "const inlineTextActionGroup = {\n  id: 'b.inline-text',\n  when: ({ flags }) => flags.isText(),"
);
source = source.replace(
  "const highlightActionGroup = {\n  id: 'c.highlight',\n  when: ({ chain }) => isFormatSupported(chain).run()[0],",
  "const highlightActionGroup = {\n  id: 'c.highlight',\n  when: ({ flags }) => flags.isText(),"
);
if (source.includes(marker)) {
  source = source.replace("when: ({ chain }) => isFormatSupported(chain).run()[0],\n  actions: [\n    { id: 'align-left'", "when: ({ flags }) => flags.isText(),\n  actions: [\n    { id: 'align-left'");
} else {
  const iconAnchor = "import {\n  CopyIcon,\n  DatabaseTableViewIcon,";
  const iconReplacement = "import {\n  TextAlignLeftIcon,\n  TextAlignCenterIcon,\n  TextAlignRightIcon,\n  CopyIcon,\n  DatabaseTableViewIcon,";
  if (!source.includes(iconAnchor)) throw new Error(`Icon import anchor not found: ${file.pathname}`);
  source = source.replace(iconAnchor, iconReplacement);
  const declarationAnchor = 'export const builtinToolbarConfig = {';
  if (!source.includes(declarationAnchor)) throw new Error(`Toolbar declaration anchor not found: ${file.pathname}`);
  source = source.replace(declarationAnchor, `${group}\n${declarationAnchor}`);
  const actionsAnchor = '    inlineTextActionGroup,\n    highlightActionGroup,';
  if (!source.includes(actionsAnchor)) throw new Error(`Toolbar actions anchor not found: ${file.pathname}`);
  source = source.replace(actionsAnchor, '    inlineTextActionGroup,\n    paragraphAlignmentActionGroup,\n    highlightActionGroup,');
}

if (!source.includes('paragraphAlignmentActionGroup') || !source.includes('TextAlignLeftIcon')) {
  throw new Error(`Paragraph alignment toolbar patch did not apply: ${file.pathname}`);
}
await fs.writeFile(file, source);
console.log('PATCHED · paragraph alignment actions added to native selection toolbar');
