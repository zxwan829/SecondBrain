import { readFile } from 'node:fs/promises';
const manifest = JSON.parse(await readFile(new URL('../manifest.json', import.meta.url), 'utf8'));
for (const key of ['name','version','entry','css']) if (typeof manifest[key] !== 'string') throw new Error(`invalid ${key}`);
console.log('Manifest PASS', manifest.name, manifest.version);
