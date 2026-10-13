import { mkdir, copyFile, writeFile } from 'node:fs/promises';
await mkdir('dist-hermes-test/dashboard', { recursive: true });
const js = (await import('node:fs/promises')).readdir('dist/assets');
const files = await js;
await copyFile(`dist/assets/${files.find((x) => x.endsWith('.js'))}`, 'dist-hermes-test/dashboard/index-fe-test-v6.js');
await copyFile('src/styles/app.css', 'dist-hermes-test/dashboard/style-fe-test-v6.css');
await writeFile('dist-hermes-test/dashboard/manifest.json', JSON.stringify({
  name: 'secondbrain-fe-test', label: 'SecondBrain FE Test', version: '0.6.0-fe-test',
  description: 'Isolated FE-0.5 runtime compatibility test plugin',
  tab: { path: '/secondbrain-fe-test', position: 'end' },
  entry: 'index-fe-test-v6.js', css: 'style-fe-test-v6.css', api: ''
}, null, 2) + '\n');
console.log('Test plugin package PASS');
