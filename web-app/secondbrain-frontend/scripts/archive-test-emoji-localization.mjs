import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { transform } from 'esbuild';
import emojiMart from 'emoji-mart';

const requireFromEditor = createRequire(new URL('../package.json', import.meta.url));
const sourcePath = new URL('../src/emoji-localization.ts', import.meta.url);
const source = await readFile(sourcePath, 'utf8');
const { code } = await transform(source, { format: 'cjs', loader: 'ts' });
const module = { exports: {} };
new Function('require', 'module', 'exports', code)(createRequire(sourcePath), module, module.exports);

const data = requireFromEditor('@emoji-mart/data');
const chineseData = module.exports.withChineseEmojiKeywords(data);
assert.equal(chineseData.emojis.cat.keywords.includes('猫'), true);
assert.equal(chineseData.emojis.cat.keywords.includes('kitten'), true, 'existing English terms stay searchable');

await emojiMart.init({ data: chineseData, locale: 'zh', i18n: requireFromEditor('@emoji-mart/data/i18n/zh.json') });
const chineseResults = await emojiMart.SearchIndex.search('猫');
const englishResults = await emojiMart.SearchIndex.search('cat');
assert.ok(chineseResults.some(emoji => emoji.id === 'cat'), 'Chinese query returns cat');
assert.ok(englishResults.some(emoji => emoji.id === 'cat'), 'English query still returns cat');
console.log('PASS: Chinese and English emoji searches return the native cat entry.');
