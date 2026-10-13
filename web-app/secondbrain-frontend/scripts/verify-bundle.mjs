import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const manifest = JSON.parse(await readFile('dist-hermes-test/dashboard/manifest.json', 'utf8'));
const bundle = await readFile(`dist-hermes-test/dashboard/${manifest.entry}`, 'utf8');
for (const pattern of [/jsxRuntime/, /\bjsxs\b/, /react-vendor/, /createRoot/]) {
  if (pattern.test(bundle)) throw new Error(`forbidden bundle reference: ${pattern}`);
}
if (!bundle.includes('createElement')) throw new Error('classic JSX React binding missing');
const registrations = [];
const React = {
  createElement: (type, props, ...children) => ({ type, props: { ...(props ?? {}), children } }),
  useState: (value) => [typeof value === 'function' ? value() : value, () => {}],
  useEffect: (effect) => { effect(); },
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
