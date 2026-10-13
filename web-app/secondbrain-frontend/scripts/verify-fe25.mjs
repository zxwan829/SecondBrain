import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import vm from 'node:vm';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const base = new URL('../', import.meta.url);
const read = (path) => readFile(new URL(path, base), 'utf8');
const fixture = {
  status: 'ok',
  agent: { status: 'online' },
  today: { status: 'empty', items: [] },
  review: { pending_count: 2, items: [
    { title: 'Fixture review alpha', status: 'pending', updated: 1791590400 },
    { title: 'Fixture review beta', status: 'pending' },
  ], status: 'real' },
  projects: { status: 'real', items: [{ title: 'dev-manifest.json' }] },
  knowledge: { status: 'real', items: [{ title: 'Fixture knowledge' }, { title: 'Fixture knowledge two' }] },
};

// Compile the actual adapter to a temporary directory, then execute its JS.
const outputDir = await mkdtemp(join(tmpdir(), 'secondbrain-fe25-'));
const projectDir = fileURLToPath(base);
const tsc = spawnSync('./node_modules/.bin/tsc', ['--ignoreConfig', '--target', 'ES2022', '--module', 'commonjs', '--outDir', outputDir, '--skipLibCheck', 'src/api/home.ts', 'src/api/home-adapter.ts'], { cwd: projectDir, encoding: 'utf8' });
if (tsc.status !== 0) throw new Error(`adapter fixture compilation failed: ${tsc.stderr || tsc.stdout}`);
const adapterModule = { exports: {} };
vm.runInNewContext(await readFile(join(outputDir, 'home-adapter.js'), 'utf8'), { module: adapterModule, exports: adapterModule.exports, require: () => ({}) }, { filename: 'home-adapter.js' });
await rm(outputDir, { recursive: true, force: true });
const adapter = adapterModule.exports;
// Home Adapter REAL / EMPTY / UNKNOWN contract fixture.
const adapted = adapter.adaptHome(fixture);
assert.equal(adapted.pendingCount, 2);
assert.equal(adapted.review.length, 2);
assert.equal(adapted.reviewSource, 'REAL');
assert.equal(adapted.projectSource, 'UNAVAILABLE');
assert.equal(adapted.projectItems.length, 0, 'untyped project-folder files are not presented as business projects');
assert.equal(adapter.adaptHome({ ...fixture, projects: { status: 'real', source_type: 'business-projects', items: [{ title: 'Fixture project' }] } }).projectItems[0].title, 'Fixture project');
assert.equal(adapted.knowledgeItems[0].title, 'Fixture knowledge');
assert.equal(adapted.knowledgeSource, 'REAL');
assert.equal(adapted.agentStatus, null, 'an unproven static online value is unavailable');
assert.equal(adapted.agentSource, 'UNAVAILABLE');
assert.equal(adapted.today.kind, 'empty');
assert.equal(adapted.source, 'REAL');
assert.equal(adapter.adaptHome({ today: { payload: ['unrecognized'] } }).today.kind, 'unknown');
assert.equal(adapter.adaptHome(null).source, 'UNAVAILABLE');

const appSource = await read('src/App.tsx');
const css = await read('src/styles/app.css');
assert.match(appSource, /VITE_CORE_REVIEW_API/);
assert.match(appSource, /VITE_DASHBOARD_ORIGIN/);
assert.doesNotMatch(appSource, /zxwan520\.com|:63012|:63013/, 'local source must not hardcode production endpoints');
assert.match(appSource, /localStorage\.getItem\('secondbrain\.locale'\)/);
assert.match(appSource, /localStorage\.setItem\('secondbrain\.locale', locale\)/);
assert.match(appSource, /localeLabel: '中文'/);
assert.match(appSource, /localeLabel: 'EN'/);
assert.match(appSource, /function ReviewCard\(/);
assert.match(appSource, /function IllustratedEmpty\(/);
assert.match(appSource, /function KpiCard\(/);
assert.match(appSource, /function MiniChart\(/);
assert.match(appSource, /className="agent-crystal" src=\{aiCubeUrl\}/);
assert.match(appSource, /header-agent \$\{view\.agentStatus \? 'is-real' : 'is-unavailable'\}/);
assert.match(appSource, /className="mini-chart-agent" src=\{hermesOrbUrl\}/);
assert.match(appSource, /className="today-background" src=\{todayLandscapeUrl\}/);
assert.match(appSource, /className="kpi-chart-slot"><MiniChart type=\{chart\} \/><\/div>/);
assert.doesNotMatch(appSource, /agent-globe|agent-wave/);
assert.match(appSource, /DEMO_KPI_DELTAS/);
assert.match(appSource, /list-item-status \$\{item\.status \? 'is-real' : 'is-unavailable'\}/);
assert.doesNotMatch(appSource, /\.join\(['"]\s*·/);
assert.match(appSource, /todayDescription: '专注当下，记录并推进你的重要事项'/);
assert.match(appSource, /todayDescription: 'Stay present, capture ideas, and move important things forward\.'/);
assert.match(css, /translateY\(-3px\)/);
assert.match(css, /prefers-reduced-motion: reduce/);
assert.match(css, /grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/);
assert.match(css, /--sb-type-body:\s*13px/);
assert.match(css, /--sb-type-title:\s*15px/);
assert.match(css, /\.review-row strong[^}]*font-size:\s*var\(--sb-type-body\)/);
assert.match(css, /\.list-item-copy strong[^}]*font-size:\s*var\(--sb-type-body\)/);
assert.match(css, /\.today-description[^}]*font-size:\s*var\(--sb-type-caption\)/);
assert.match(css, /\.donut-graphic[^}]*width:\s*88px/);
assert.match(css, /\.kpi-chart-slot \{[^}]*width:\s*50%/);
assert.match(css, /\.tone-teal \.kpi-chart-slot \{ inset-block:\s*30px/);
assert.match(css, /\.tone-teal \.kpi-value-status \{ inset-inline-start:\s*5px; color:\s*var\(--sb-green\) !important; font-size:\s*clamp\(25px, 2vw, 32px\)/);
assert.match(css, /\.tone-teal \.mini-chart-agent \{ transform:\s*translate\(-20px, -30px\)/);
assert.match(css, /@media \(max-width: 760px\)[\s\S]*?\.tone-teal \.mini-chart-agent \{ transform:\s*translate\(0, 5px\)/);
assert.match(css, /\.mini-chart \{[^}]*width:\s*min\(100%, var\(--sb-chart-width\)\)/);
assert.match(css, /--sb-chart-width:\s*156px/);
assert.match(css, /--sb-chart-height:\s*60px/);
assert.match(css, /\.mini-chart-agent \{[^}]*width:\s*100%;[^}]*height:\s*100%/);
assert.match(css, /\.today-card > \.today-background[^}]*object-fit:\s*cover;[^}]*opacity:\s*\.8/);
assert.doesNotMatch(css, /will-change\s*:/, 'all-card compositor promotion is not used');
assert.match(css, /\.module-title h2[^}]*font-size:\s*16px/);
assert.match(css, /\.list-item-status\.is-unavailable/);
assert.match(css, /\.agent-crystal[^}]*width:\s*49%;[^}]*transform:\s*translateX\(-15px\)/);
assert.match(css, /--sb-kpi-number-indent:\s*23px/);
assert.match(css, /--sb-kpi-status-indent:\s*10px/);
assert.doesNotMatch(css, /\.agent-globe|\.agent-wave/);
assert.match(css, /\.sb-app[^}]*overflow:\s*clip/);
assert.match(css, /grid-template-columns:\s*minmax\(0, 1fr\)/);
assert.match(css, /\.dashboard > :not\(\.mobile-topbar\) \{ width: 92%;[^}]*margin-right: 4%; margin-left: 4%/);
assert.match(css, /\.dashboard > :not\(\.mobile-topbar\) \{ width: auto; max-width: none;/);

// Execute the real built plugin entry with the Hermes SDK React mock and render
// its function-component tree using a small test renderer. No second React is loaded.
const manifest = JSON.parse(await read('dist-hermes-test/dashboard/manifest.json'));
const bundle = await read(`dist-hermes-test/dashboard/${manifest.entry}`);
const registrations = [];
const states = [];
const effects = [];
let stateCursor = 0;
let storedLocale = null;
const React = {
  createElement: (type, props, ...children) => ({ type, props: { ...(props ?? {}), children: children.length === 1 ? children[0] : children } }),
  useState: (initial) => {
    const index = stateCursor++;
    if (!(index in states)) states[index] = index === 2 ? fixture : (typeof initial === 'function' ? initial() : initial);
    return [states[index], (next) => { states[index] = typeof next === 'function' ? next(states[index]) : next; }];
  },
  useEffect: (effect) => effects.push(effect),
  useMemo: (factory) => factory(),
};
React.default = React;
const windowMock = { __HERMES_PLUGIN_SDK__: { React, hooks: React }, __HERMES_PLUGINS__: { register: (name, component) => registrations.push({ name, component }) }, location: { pathname: '/secondbrain-fe-test', search: '' }, __SB_IMMERSIVE_TRACE__: undefined };
const documentMock = {
  documentElement: { lang: 'zh-CN' },
  body: { dataset: {}, getAttribute: () => null, setAttribute() {}, removeAttribute() {} },
  head: { appendChild() {} },
  getElementById: () => ({ scrollIntoView() {} }),
  createElement: () => ({ dataset: {}, remove() {} }),
  querySelector: () => null,
};
const context = {
  window: windowMock,
  __HERMES_PLUGIN_SDK__: windowMock.__HERMES_PLUGIN_SDK__,
  __HERMES_PLUGINS__: windowMock.__HERMES_PLUGINS__,
  React,
  document: documentMock,
  location: windowMock.location,
  URLSearchParams,
  localStorage: { getItem: () => storedLocale, setItem: (key, value) => { if (key === 'secondbrain.locale') storedLocale = value; } },
  navigator: { clipboard: { writeText: async () => {} } },
  fetch: async () => ({ ok: true, json: async () => fixture }),
  console,
};
vm.runInNewContext(bundle, context, { filename: manifest.entry });
const registered = registrations.find((item) => item.name === manifest.name);
assert.ok(registered, 'Hermes SDK registration runs');
stateCursor = 0;
const root = registered.component();
function render(node) {
  if (Array.isArray(node)) return node.map(render);
  if (!node || typeof node !== 'object' || !('type' in node)) return node;
  if (typeof node.type === 'function') return render(node.type(node.props));
  return { ...node, renderedChildren: render(node.props?.children) };
}
const rendered = render(root);
const allNodes = [];
function visit(node) {
  if (Array.isArray(node)) { node.forEach(visit); return; }
  if (!node || typeof node !== 'object') return;
  allNodes.push(node);
  visit(node.renderedChildren);
}
visit(rendered);
const classNodes = (name) => allNodes.filter((node) => (node.props?.className ?? '').split(/\s+/).includes(name));
const textContent = (node) => Array.isArray(node) ? node.map(textContent).join('') : node && typeof node === 'object' ? (node.type === undefined ? '' : `${node.props?.children && typeof node.props.children === 'string' ? node.props.children : ''}${textContent(node.renderedChildren)}`) : String(node ?? '');
// Aggregate text from each node in the mounted tree. The small renderer's
// root-level traversal does not flatten nested fragment children consistently.
const visibleText = allNodes.map(textContent).join('');
assert.equal(classNodes('review-row').length, 2, 'review fixture renders separate rows');
assert.equal(classNodes('illustrated-empty').length, 1, 'today empty illustration mounts');
assert.equal(classNodes('today-description').length, 1, 'today supporting description mounts');
assert.equal(classNodes('bar-chart').length, 1, 'KPI bar chart mounts');
assert.equal(classNodes('line-chart').length, 1, 'KPI line chart mounts');
assert.equal(classNodes('kpi-chart-slot').length, 3, 'all three top visuals mount in a dedicated right-side chart region');
assert.equal(classNodes('kpi-value-number').length, 2, 'both numeric KPI values use the approved position');
assert.ok(classNodes('kpi-value-number').some((node) => node.props?.children === '—'), 'unavailable project KPI uses a compact neutral marker');
assert.equal(classNodes('kpi-value-status').length, 1, 'Agent status uses its separate position');
assert.equal(classNodes('unavailable-status-dot').length, 2, 'missing knowledge statuses get neutral indicators');
assert.ok(classNodes('unavailable-status-dot').every((node) => node.props['aria-hidden'] === 'true'), 'decorative indicators do not announce business status');
assert.equal(classNodes('today-background').length, 1, 'user-provided lake background covers the Today card');
assert.match(classNodes('today-background')[0].props.src, /\/dashboard-plugins\/secondbrain-fe-test\/assets\/[\w-]+\.png/);
assert.equal(classNodes('mini-chart-agent').length, 1, 'AI crystal mounts in the agent KPI');
assert.equal(classNodes('agent-crystal').length, 1, 'AI crystal mounts in the Agent card');
assert.match(classNodes('mini-chart-agent')[0].props.src, /\/dashboard-plugins\/secondbrain-fe-test\/assets\/[\w-]+\.png/, 'transparent Hermes planet PNG is emitted as a plugin asset');
assert.match(classNodes('agent-crystal')[0].props.src, /\/dashboard-plugins\/secondbrain-fe-test\/assets\/[\w-]+\.png/, 'transparent AI cube PNG is emitted as a plugin asset');
assert.equal(classNodes('list-item-status').length, 2, 'knowledge status states are explicit');
assert.ok(visibleText.includes('Fixture review alpha'));
assert.ok(visibleText.includes('Home API 当前返回的是项目目录文件，尚非业务项目列表。'));
assert.ok(!visibleText.includes('dev-manifest.json'));
assert.ok(visibleText.includes('Fixture knowledge'));
assert.ok(visibleText.includes('专注当下，记录并推进你的重要事项'), 'Chinese Today description renders');
assert.ok(visibleText.includes('DEMO'));
assert.ok(visibleText.includes('↑ +2 · DEMO') && visibleText.includes('↑ +3 · DEMO'), 'decorative KPI deltas remain explicitly DEMO');
assert.ok(allNodes.some((node) => node.props?.['aria-current'] === 'page'), 'sidebar selected state is accessible');
assert.ok(textContent(classNodes('desktop-locale')[0]) === '中文', 'zh-CN switcher names the active locale');
effects[1]();
assert.equal(storedLocale, 'zh-CN');
classNodes('desktop-locale')[0].props.onClick();
stateCursor = 0; effects.length = 0;
const english = render(registered.component());
const englishStart = allNodes.length; visit(english); // visit appends into the shared node list.
const englishText = allNodes.slice(englishStart).map(textContent).join('');
assert.ok(englishText.includes('Your workspace'), 'English strings render after locale switch');
assert.ok(englishText.includes('Stay present, capture ideas, and move important things forward.'), 'English Today description renders');
assert.ok(textContent(classNodes('desktop-locale').at(-1)) === 'EN', 'English switcher names the active locale');
effects[1]();
assert.equal(storedLocale, 'en', 'locale is persisted under secondbrain.locale');
states.length = 0; stateCursor = 0; effects.length = 0;
const afterReload = render(registered.component());
const reloadStart = allNodes.length; visit(afterReload);
const reloadedText = allNodes.slice(reloadStart).map(textContent).join('');
assert.ok(reloadedText.includes('Your workspace'), 'locale persists for a fresh mount');
assert.ok(textContent(classNodes('desktop-locale').at(-1)) === 'EN', 'fresh mount keeps active-locale label');

// Test route-scoped host resolver/controller against the real DOM shape observed
// in Hermes: role=banner with the plugin title, mobile fixed header/spacer,
// #app-sidebar, and the measured pt-* content wrapper.
class FakeElement {
  constructor(tag, className = '', attrs = {}) {
    this.tagName = tag.toUpperCase(); this.className = className; this.attributes = new Map(Object.entries(attrs));
    this.children = []; this.parentElement = null; this.style = {}; this.dataset = {};
    this.classList = { contains: (name) => this.className.split(/\s+/).includes(name) };
  }
  append(child) { child.parentElement = this; this.children.push(child); return child; }
  contains(target) { return this === target || this.children.some((child) => child.contains(target)); }
  getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  removeAttribute(name) { this.attributes.delete(name); }
  closest(selector) { if (selector === 'header[role="banner"]' && this.tagName === 'HEADER' && this.getAttribute('role') === 'banner') return this; return this.parentElement?.closest(selector) ?? null; }
  querySelectorAll(selector) { return this.rootQueries?.[selector] ?? []; }
  querySelector(selector) { return this.rootSingle?.[selector] ?? null; }
  getBoundingClientRect() { return { top: 0 }; }
  remove() { this.removed = true; }
}
const rootElement = new FakeElement('div');
const hostBanner = new FakeElement('header', '', { role: 'banner' });
const hostTitleElement = hostBanner.append(new FakeElement('h1'));
hostTitleElement.textContent = 'SecondBrain FE Test';
const mobileHeader = new FakeElement('header', 'lg:hidden fixed top-0');
const spacer = new FakeElement('div', 'h-14 lg:hidden', { 'aria-hidden': 'true' });
const sidebar = new FakeElement('aside', '', { id: 'app-sidebar' });
const plugin = new FakeElement('main', 'sb-app');
const pluginHeader = plugin.append(new FakeElement('header', 'workspace-header'));
const contents = new FakeElement('div', 'contents');
const contentArea = new FakeElement('div', 'w-full min-w-0 pb');
const offset = new FakeElement('div', 'relative z-2 flex px-3 sm:px-6 pt-2 sm:pt-4 lg:pt-6');
const hostMain = new FakeElement('main');
rootElement.append(hostBanner); rootElement.append(mobileHeader); rootElement.append(spacer); rootElement.append(sidebar); rootElement.append(hostMain);
hostMain.append(offset).append(contentArea).append(contents).append(plugin);
const hostTitle = hostTitleElement;
rootElement.rootQueries = { h1: [hostTitle], header: [hostBanner, mobileHeader, pluginHeader], '[aria-hidden="true"]': [spacer] };
rootElement.rootSingle = { '.sb-app': plugin, '#app-sidebar': sidebar };
const styleNodes = new Map();
const body = new FakeElement('body', '', { 'data-secondbrain-immersive': 'previous-value' });
const doc = {
  body,
  head: { appendChild: (node) => { styleNodes.set(node.id, node); node.remove = () => styleNodes.delete(node.id); } },
  getElementById: (id) => id === 'root' ? rootElement : styleNodes.get(id) ?? null,
  createElement: (tag) => new FakeElement(tag),
  querySelector: (selector) => selector === '.sb-app .workspace-header' ? pluginHeader : null,
};
const listeners = new Map();
const win = {
  location: { pathname: '/secondbrain-fe-test' },
  __SB_IMMERSIVE_TRACE__: undefined,
  addEventListener: (name, callback) => listeners.set(name, callback),
  removeEventListener: (name) => listeners.delete(name),
  getComputedStyle: (element) => ({ display: element.getAttribute('data-sb-host-banner') || element.getAttribute('data-sb-host-mobile-header') || element.getAttribute('data-sb-host-mobile-spacer') ? 'none' : 'block' }),
};
const immersiveOutput = spawnSync('./node_modules/.bin/tsc', ['--ignoreConfig', '--target', 'ES2022', '--module', 'commonjs', '--outDir', outputDir, '--skipLibCheck', 'src/host-integration/immersive.ts'], { cwd: projectDir, encoding: 'utf8' });
if (immersiveOutput.status !== 0) throw new Error(`host integration compilation failed: ${immersiveOutput.stderr || immersiveOutput.stdout}`);
const immersiveModule = { exports: {} };
vm.runInNewContext(await readFile(join(outputDir, 'immersive.js'), 'utf8'), {
  module: immersiveModule,
  exports: immersiveModule.exports,
  require: () => ({ useEffect() {}, useState: (value) => [typeof value === 'function' ? value() : value, () => {}] }),
  URLSearchParams,
  location: win.location,
  window: win,
}, { filename: 'immersive.js' });
await rm(outputDir, { recursive: true, force: true });
const immersive = immersiveModule.exports;
const resolved = immersive.resolveHostChrome(rootElement);
assert.equal(resolved.banner, hostBanner);
assert.equal(resolved.mobileHeaders.length, 1);
assert.equal(resolved.mobileHeaders[0], mobileHeader);
assert.equal(resolved.spacers.length, 1);
assert.equal(resolved.spacers[0], spacer);
assert.equal(resolved.sidebar, sidebar);
assert.equal(resolved.contentWrapper, offset);
const stop = immersive.createImmersiveController(doc, win).start();
assert.equal(body.getAttribute('data-secondbrain-immersive'), 'true');
assert.ok(styleNodes.has('secondbrain-host-immersive'));
assert.equal(hostBanner.getAttribute('data-sb-host-banner'), 'true');
assert.equal(offset.getAttribute('data-sb-host-content-offset'), 'true');
const hostOverride = [...styleNodes.values()][0].textContent;
assert.match(hostOverride, /padding-inline:\s*0 !important/);
assert.match(hostOverride, /background:\s*var\(--sb-bg, #080810\) !important/);
assert.match(hostOverride, /body\[data-secondbrain-immersive="true"\]/);
for (let cycle = 1; cycle <= 3; cycle += 1) {
  win.location.pathname = '/chat';
  listeners.get('pagehide')();
  assert.equal(body.getAttribute('data-secondbrain-immersive'), 'previous-value', `cycle ${cycle}: body state restored on Chat navigation`);
  assert.equal(styleNodes.size, 0, `cycle ${cycle}: route-scoped style removed`);
  assert.equal(hostBanner.getAttribute('data-sb-host-banner'), null, `cycle ${cycle}: host banner marker restored`);
  assert.equal(offset.getAttribute('data-sb-host-content-offset'), null, `cycle ${cycle}: host wrapper marker restored`);
  assert.equal(sidebar.getAttribute('data-sb-host-sidebar'), null, `cycle ${cycle}: sidebar marker restored`);
  win.location.pathname = '/secondbrain-fe-test';
  listeners.get('pageshow')();
  assert.equal(body.getAttribute('data-secondbrain-immersive'), 'true', `cycle ${cycle}: immersive state reinitialized on return`);
  assert.equal(styleNodes.size, 1, `cycle ${cycle}: exactly one override stylesheet exists`);
  assert.equal(hostBanner.getAttribute('data-sb-host-banner'), 'true');
}
assert.equal(win.__SB_IMMERSIVE_TRACE__.cleanupCallCount, 3);
assert.equal(win.__SB_IMMERSIVE_TRACE__.initCallCount, 4);
win.location.pathname = '/chat';
listeners.get('pagehide')();
win.location.pathname = '/secondbrain';
listeners.get('pageshow')();
assert.equal(body.getAttribute('data-secondbrain-immersive'), 'true', 'production route initializes immersive host mode');
assert.equal(styleNodes.size, 1, 'production route installs one host override');
stop();
assert.equal(body.getAttribute('data-secondbrain-immersive'), 'previous-value');
assert.equal(styleNodes.size, 0);
assert.equal(hostBanner.getAttribute('data-sb-host-banner'), null);
assert.equal(offset.getAttribute('data-sb-host-content-offset'), null);
assert.equal(win.__SB_IMMERSIVE_TRACE__.cleanupCallCount, 5);

console.log('Home REAL/EMPTY/UNKNOWN fixture PASS');
console.log('Hermes SDK component render and UI composition PASS');
console.log('Sidebar / charts / review rows / illustrated empty state PASS');
console.log('Bilingual active-label and locale persistence fixture PASS');
console.log('Host DOM resolver, route cleanup, and return initialization PASS');
console.log('Hover / reduced-motion / responsive CSS contract PASS');
