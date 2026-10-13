import assert from 'node:assert/strict';
import { readFile, readdir, stat } from 'node:fs/promises';
import vm from 'node:vm';

const root = 'dist-fe4/dashboard';
const entry = 'index-20261010-v3.js';
const bundle = await readFile(`${root}/${entry}`, 'utf8');
const css = await readFile(`${root}/style-20261010-v3.css`, 'utf8');
for (const pattern of [/createRoot/, /react-vendor/, /jsxRuntime/]) assert.doesNotMatch(bundle, pattern);
assert.match(bundle, /\.register\(`secondbrain`,/);
assert.match(css, /\.sb-app/);
const assetRefs = [...bundle.matchAll(/\/dashboard-plugins\/secondbrain\/assets\/([A-Za-z0-9_-]+\.png)/g)].map((match) => match[1]);
assert.equal(new Set(assetRefs).size, 3, 'planet, cube and Today background resources are referenced');
const packagedAssets = await readdir(`${root}/assets`);
for (const asset of new Set(assetRefs)) {
  assert.ok(packagedAssets.includes(asset), `referenced asset exists: ${asset}`);
  assert.ok((await stat(`${root}/assets/${asset}`)).size > 1024, `asset is non-empty: ${asset}`);
}

const registrations = [];
const React = {
  createElement: (type, props, ...children) => ({ type, props: { ...(props ?? {}), children } }),
  useState: (value) => [typeof value === 'function' ? value() : value, () => {}],
  useEffect: () => {},
  useMemo: (factory) => factory(),
};
React.default = React;
const document = { documentElement: { lang: 'zh-CN' }, body: { dataset: {} }, querySelector: () => null, getElementById: () => ({}), createElement: () => ({ set textContent(_) {}, appendChild() {}, remove() {} }), head: { appendChild() {} } };
const sdk = { React, hooks: React };
vm.runInNewContext(bundle, {
  window: { __HERMES_PLUGIN_SDK__: sdk, __HERMES_PLUGINS__: { register: (name, component) => registrations.push({ name, component }) } },
  __HERMES_PLUGIN_SDK__: sdk,
  document,
  location: { pathname: '/secondbrain', search: '' },
  URLSearchParams,
  localStorage: { getItem: () => null, setItem: () => {} },
  navigator: { clipboard: { writeText: async () => {} } },
  console,
  fetch: async () => ({ ok: true, json: async () => ({}) }),
}, { filename: entry });
const registration = registrations.find((item) => item.name === 'secondbrain');
assert.ok(registration, 'formal plugin ID registers against host supplied React');
assert.equal(registration.component().type, 'main', 'React component renders under the Hermes SDK mock');
console.log('Production bundle identity / React SDK render PASS');
console.log(`Production assets PASS (${new Set(assetRefs).size} referenced PNGs)`);
