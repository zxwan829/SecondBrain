import { mkdir, copyFile, writeFile, readdir, rm } from 'node:fs/promises';
await mkdir('dist-hermes-test/dashboard', { recursive: true });
const files = await readdir('dist/assets');
await copyFile(`dist/assets/${files.find((x) => x.endsWith('.js'))}`, 'dist-hermes-test/dashboard/index-fe-test.js');
await copyFile('src/styles/app.css', 'dist-hermes-test/dashboard/style-fe-test.css');
const packagedAssets = 'dist-hermes-test/dashboard/assets';
await rm(packagedAssets, { recursive: true, force: true });
await mkdir(packagedAssets, { recursive: true });
for (const file of files.filter((name) => name.endsWith('.png'))) {
  await copyFile(`dist/assets/${file}`, `${packagedAssets}/${file}`);
}
await writeFile('dist-hermes-test/dashboard/manifest.json', JSON.stringify({
  name: 'secondbrain-fe-test', label: 'SecondBrain FE Test', version: '0.8.0-fe-dev',
  description: 'Isolated FE-0.5 runtime compatibility test plugin',
  tab: { path: '/secondbrain-fe-test', position: 'end' },
  entry: 'index-fe-test.js', css: 'style-fe-test.css', api: ''
}, null, 2) + '\n');
console.log('Test plugin package PASS');
