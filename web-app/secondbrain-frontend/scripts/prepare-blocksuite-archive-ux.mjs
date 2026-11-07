// Pinned install preparation. The plain-Markdown editor has a separate
// fail-closed loss guard; enabling the native UX does not enable Markdown
// projection for formats it cannot represent.
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
// Validate direct and nested lock entries. Archive modules import internal
// BlockSuite packages, so a transitive icons copy is part of this pin too.
const lock = readJson(path.join(root, 'package-lock.json'));
const packagePath = /(?:^|\/)node_modules\/@blocksuite\/[^/]+$/;
let zodLockSeen = false;
for (const [relative, entry] of Object.entries(lock.packages ?? {})) {
  if (/(?:^|\/)node_modules\/zod$/.test(relative)) {
    zodLockSeen = true;
    const installed = path.join(root, relative, 'package.json');
    if (entry.version !== '4.6.6' || !fs.existsSync(installed) || readJson(installed).version !== '4.6.6') {
      throw new Error(`Unsupported Zod lock/install: ${entry.version}`);
    }
  }
  if (!packagePath.test(relative)) continue;
  const packageName = relative.slice(relative.lastIndexOf('node_modules/@blocksuite/') + 'node_modules/'.length);
  const expectedVersion = packageName === '@blocksuite/icons' ? '2.2.12' : '0.22.4';
  if (entry.version !== expectedVersion) throw new Error(`Unsupported locked BlockSuite package: ${packageName}@${entry.version}`);
  const installed = path.join(root, relative, 'package.json');
  if (!fs.existsSync(installed) || readJson(installed).version !== expectedVersion) {
    throw new Error(`Installed BlockSuite package differs from lock: ${packageName}`);
  }
}
if (!zodLockSeen || readJson(path.join(root, 'package.json')).overrides?.zod !== '4.6.6') {
  throw new Error('Zod 4.6.6 override is missing from the lock or manifest');
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
console.log('ARCHIVE_UX_PREPARED: all 22 pinned patches applied; release still requires full browser and security gates');
