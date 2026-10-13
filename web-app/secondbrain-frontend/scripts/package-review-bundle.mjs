import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const dashboard = resolve(fileURLToPath(new URL('../../secondbrain-plugin/dashboard', import.meta.url)));
const priorBundlePath = resolve(dashboard, 'index-20261013-fe4-review.js');
const addonPath = resolve(dashboard, 'review-addon.js');
const outputPath = resolve(dashboard, 'index-20261014-fe4-review.js');
const marker = Buffer.from('/* Additive Review view for the existing FE-4 plugin. Promote stays disabled. */');
const acceptedBaseBytes = 78_453;
const acceptedBaseSha256 = '6cf72d312adac4c7f4b483f777618c6c040fa9a0f140c5d8f459758add5642fe';

const prior = await readFile(priorBundlePath);
const markerAt = prior.indexOf(marker);
if (markerAt !== acceptedBaseBytes + 1 || prior[markerAt - 1] !== 0x0a) {
  throw new Error('Prior bundle does not contain the expected FE-4 baseline boundary');
}
const acceptedBase = prior.subarray(0, markerAt - 1);
const baseSha256 = createHash('sha256').update(acceptedBase).digest('hex');
if (acceptedBase.length !== acceptedBaseBytes || baseSha256 !== acceptedBaseSha256) {
  throw new Error(`Accepted FE-4 baseline mismatch: ${acceptedBase.length} bytes, ${baseSha256}`);
}

const addon = await readFile(addonPath);
if (!addon.subarray(0, marker.length).equals(marker)) throw new Error('D071 Review source marker is missing');
const output = Buffer.concat([acceptedBase, Buffer.from('\n'), addon]);
await writeFile(outputPath, output);
console.log(`Review bundle PASS ${outputPath}`);
console.log(`FE-4 baseline ${acceptedBase.length} bytes SHA-256 ${baseSha256}`);
console.log(`Review bundle SHA-256 ${createHash('sha256').update(output).digest('hex')}`);
