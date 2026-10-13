import { readFile, readdir, stat } from 'node:fs/promises';
import vm from 'node:vm';

const manifest = JSON.parse(await readFile('dist-hermes-test/dashboard/manifest.json', 'utf8'));
const bundle = await readFile(`dist-hermes-test/dashboard/${manifest.entry}`, 'utf8');
for (const pattern of [/jsxRuntime/, /\bjsxs\b/, /react-vendor/, /createRoot/]) {
  if (pattern.test(bundle)) throw new Error(`forbidden bundle reference: ${pattern}`);
}
if (!bundle.includes('createElement')) throw new Error('classic JSX React binding missing');
const assetRefs = [...bundle.matchAll(/\/dashboard-plugins\/secondbrain-fe-test\/assets\/([A-Za-z0-9_-]+\.png)/g)].map((match) => match[1]);
if (new Set(assetRefs).size < 3) throw new Error('fixed JS bundle must reference the planet, cube, and Today PNG assets');
const packagedAssets = await readdir('dist-hermes-test/dashboard/assets');
for (const asset of new Set(assetRefs)) {
  if (!packagedAssets.includes(asset) || (await stat(`dist-hermes-test/dashboard/assets/${asset}`)).size < 1024) {
    throw new Error(`referenced PNG is missing or unexpectedly small: ${asset}`);
  }
}
const registrations = [];
const React = {
  createElement: (type, props, ...children) => ({ type, props: { ...(props ?? {}), children } }),
  useState: (value) => [typeof value === 'function' ? value() : value, () => {}],
  // Effects belong to the browser lifecycle and are exercised by verify:fe25.
  useEffect: () => {},
  useMemo: (factory) => factory(),
};
React.default = React;
const document = { documentElement: { lang: 'en' }, body: { dataset: {} }, querySelector: () => null, getElementById: () => ({ }), createElement: () => ({ set textContent(_) {}, appendChild() {}, remove() {} }), head: { appendChild() {} } };
const context = { window: { __HERMES_PLUGIN_SDK__: { React, hooks: React }, __HERMES_PLUGINS__: { register: (name, component) => registrations.push({ name, component }) } }, __HERMES_PLUGIN_SDK__: { React, hooks: React }, document, location: { pathname: '/secondbrain-fe-test', search: '' }, URLSearchParams, localStorage: { getItem: () => null, setItem: () => {} }, navigator: { clipboard: { writeText: async () => {} } }, console, fetch: async () => ({ ok: true, json: async () => ({}) }) };
vm.runInNewContext(bundle, context, { filename: manifest.entry });
const registration = registrations.find((item) => item.name === manifest.name);
if (!registration) throw new Error('plugin did not register');
const rendered = registration.component();
if (!rendered || rendered.type !== 'main') throw new Error('component did not render');
console.log('Bundle execution PASS');
console.log('Component render PASS');
console.log(`PNG resource packaging PASS (${new Set(assetRefs).size} referenced assets)`);
