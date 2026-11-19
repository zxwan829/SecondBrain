import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const edits = [
  ['@blocksuite/store', 'dist/model/block/zod.js', [
    ['.function()\n            .args(z.custom())\n            .returns(z.record(z.any()))', '.function({ input: z.tuple([z.custom()]), output: z.record(z.string(), z.any()) })'],
    ['z.function().args().returns(z.custom()).optional()', 'z.function({ input: z.tuple([]), output: z.custom() }).optional()'],
    ['.function()\n        .args(z.custom())\n        .returns(z.custom())', '.function({ input: z.tuple([z.custom()]), output: z.custom() })'],
  ]],
  ['@blocksuite/store', 'src/model/block/zod.ts', [
    ['.function()\n      .args(z.custom<InternalPrimitives>())\n      .returns(z.record(z.any()))', '.function({ input: z.tuple([z.custom<InternalPrimitives>()]), output: z.record(z.string(), z.any()) })'],
    ['z.function().args().returns(z.custom<BlockModel>()).optional()', 'z.function({ input: z.tuple([]), output: z.custom<BlockModel>() }).optional()'],
    ['.function()\n    .args(z.custom<Map<string, unknown>>())\n    .returns(z.custom<BaseBlockTransformer>())', '.function({ input: z.tuple([z.custom<Map<string, unknown>>()]), output: z.custom<BaseBlockTransformer>() })'],
  ]],
  ['@blocksuite/affine-shared', 'dist/utils/zod-schema.js', [
    ['else if (schema instanceof ZodUnion) {\n        return schema.or(z.undefined());', 'else if (schema instanceof ZodUnion) {\n        return schema.optional();'],
  ]],
  ['@blocksuite/affine-shared', 'src/utils/zod-schema.ts', [
    ['    return schema.or(z.undefined());', '    return schema.optional();'],
    ['export function makeDeepOptional(schema: ZodTypeAny): ZodTypeAny {', 'export function makeDeepOptional(schema: any): any {'],
  ]],
  ['@blocksuite/affine-block-paragraph', 'dist/view.js', [
    ['z.function().args(z.instanceof(ParagraphBlockModel)).returns(z.string())', 'z.function({ input: z.tuple([z.instanceof(ParagraphBlockModel)]), output: z.string() })'],
  ]],
  ['@blocksuite/affine-block-paragraph', 'src/view.ts', [
    ['z.function().args(z.instanceof(ParagraphBlockModel)).returns(z.string())', 'z.function({ input: z.tuple([z.instanceof(ParagraphBlockModel)]), output: z.string() })'],
  ]],
  ['@blocksuite/affine-block-database', 'dist/view.js', [
    ['.function()\n        .args(z.instanceof(DatabaseBlockModel), z.custom())\n        .returns(z.custom())', '.function({ input: z.tuple([z.instanceof(DatabaseBlockModel), z.custom()]), output: z.custom() })'],
  ]],
  ['@blocksuite/affine-block-database', 'src/view.ts', [
    ['.function()\n    .args(z.instanceof(DatabaseBlockModel), z.custom<MenuOptions>())\n    .returns(z.custom<MenuOptions>())', '.function({ input: z.tuple([z.instanceof(DatabaseBlockModel), z.custom<MenuOptions>()]), output: z.custom<MenuOptions>() })'],
  ]],
];

for (const [pkg, file, replacements] of edits) {
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'node_modules', pkg, 'package.json'), 'utf8'));
  if (manifest.version !== '0.22.4') throw new Error(`${pkg} version drift: ${manifest.version}`);
  const target = path.join(root, 'node_modules', pkg, file.replace(/^dist\//, 'dist/'));
  let source = fs.readFileSync(target, 'utf8');
  for (const [before, after] of replacements) {
    if (source.includes(after)) continue;
    if (!source.includes(before)) throw new Error(`Patch context missing in ${pkg}/${file}`);
    source = source.replace(before, after);
  }
  fs.writeFileSync(target, source);
}
