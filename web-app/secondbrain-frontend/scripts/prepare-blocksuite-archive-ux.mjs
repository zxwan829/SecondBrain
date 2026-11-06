// Explicit preparation only. Never enabled by npm postinstall: Markdown fidelity
// for text alignment/merged tables still requires the WP5 product decision.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';

if (!process.argv.includes('--prepare-only')) throw new Error('Use the explicit prepare:archive-ux command; this is not deployment approval');
const root = process.cwd();
const readJson = file => JSON.parse(fs.readFileSync(file, 'utf8'));
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const manifest = readJson(path.join(root, 'patches/archive-manifest.json'));
const overlayRoot = path.join(root, 'patches/blocksuite-archive-data-view');
const overlay = readJson(path.join(overlayRoot, 'manifest.json'));
// Every dependency touched by the archive is pinned to the same upstream release.
for (const entry of fs.readdirSync(path.join(root, 'node_modules/@blocksuite'))) {
  const file = path.join(root, 'node_modules/@blocksuite', entry, 'package.json');
  if (!fs.existsSync(file)) continue;
  const pkg = readJson(file);
  if (pkg.version !== '0.22.4') throw new Error(`Unsupported BlockSuite package version: ${pkg.name}@${pkg.version}`);
}
execFileSync(process.execPath, ['scripts/apply-blocksuite-zod4-compat.mjs'], { cwd: root, stdio: 'inherit' });
const writes = [];
for (const entry of overlay.files) {
  if (!entry.path.startsWith('src/') || entry.path.split('/').includes('..')) throw new Error('Unsafe overlay path');
  const target = path.join(root, 'node_modules/@blocksuite/data-view', entry.path);
  const payload = fs.readFileSync(path.join(overlayRoot, entry.path));
  if (sha(payload) !== entry.after) throw new Error(`Archive payload changed: ${entry.path}`);
  const current = fs.existsSync(target) ? sha(fs.readFileSync(target)) : null;
  if (![entry.before, entry.after, entry.final].includes(current)) throw new Error(`Unexpected data-view source: ${entry.path}`);
  if (current === entry.before) writes.push([target, payload]);
}
for (const entry of manifest.scripts) {
  if (sha(fs.readFileSync(path.join(root, entry.script))) !== entry.adaptedSha256) throw new Error(`Archive patch changed: ${entry.script}`);
}
for (const [target, payload] of writes) {
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, payload);
}
for (const entry of manifest.scripts) execFileSync(process.execPath, [entry.script], { cwd: root, stdio: 'inherit' });
console.log('ARCHIVE_UX_PREPARED_NOT_RELEASED: all 22 patches applied; Markdown fidelity decision and full browser parity gate remain required');
