import { copyFile, mkdir, readdir, stat } from 'node:fs/promises';

const output = 'dist-fe4/dashboard';
await mkdir(`${output}/assets`, { recursive: true });
const files = await readdir('dist-fe4/assets');
const jsFiles = files.filter((name) => name.endsWith('.js'));
if (jsFiles.length !== 1) throw new Error(`expected one production bundle, found ${jsFiles.length}`);
await copyFile(`dist-fe4/assets/${jsFiles[0]}`, `${output}/index-20261010-v3.js`);
await copyFile('src/styles/app.css', `${output}/style-20261010-v3.css`);
const pngFiles = files.filter((name) => name.endsWith('.png'));
if (pngFiles.length !== 3) throw new Error(`expected 3 visual assets, found ${pngFiles.length}`);
for (const file of pngFiles) await copyFile(`dist-fe4/assets/${file}`, `${output}/assets/${file}`);
for (const file of [
  `${output}/index-20261010-v3.js`,
  `${output}/style-20261010-v3.css`,
  ...pngFiles.map((name) => `${output}/assets/${name}`),
]) {
  if ((await stat(file)).size === 0) throw new Error(`empty package file: ${file}`);
}
console.log(`Production package PASS secondbrain fixed entry, ${pngFiles.length} assets`);
