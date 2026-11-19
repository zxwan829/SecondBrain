import fs from 'node:fs';
import path from 'node:path';

const target = path.resolve('node_modules/@blocksuite/affine-block-list/src/markdown.ts');
const source = fs.readFileSync(target, 'utf8');
const original = '      if (!matchModels(model, [ParagraphBlockModel])) return;';
const guarded = '      // Markdown list prefixes should only transform plain paragraphs.\n      // Headings, quotes, and other paragraph styles must keep their block type.\n      if (!matchModels(model, [ParagraphBlockModel]) || model.props.type !== \'text\') return;';
if (source.includes(guarded)) {
  console.log('heading list prefix guard already applied');
} else if (source.includes(original)) {
  fs.writeFileSync(target, source.replace(original, guarded));
  console.log('applied heading list prefix guard');
} else {
  throw new Error(`Could not apply heading list prefix guard to ${target}`);
}
