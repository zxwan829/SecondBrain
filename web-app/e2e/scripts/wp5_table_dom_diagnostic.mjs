import { spawn } from 'node:child_process';
import { mkdtemp, mkdir, chmod, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:net';
import { chromium } from '@playwright/test';

const root = join(fileURLToPath(new URL('../../../', import.meta.url)));
const frontend = join(root, 'web-app/secondbrain-frontend');
const coreDir = join(root, 'web-app/secondbrain-core');
const temp = await mkdtemp(join(tmpdir(), 'wp5-table-dom-'));
await chmod(temp, 0o700);
const dirs = Object.fromEntries(['raw', 'review', 'state', 'knowledge', 'journal', 'task', 'projects', 'briefs', 'notes']
  .map(name => [name, join(temp, name)]));
for (const path of Object.values(dirs)) { await mkdir(path, { mode: 0o700 }); }
const passwordPath = join(temp, 'app-password');
await writeFile(passwordPath, 'synthetic-wp5-dom-diagnostic-only\n', { mode: 0o600 });

async function freePort() {
  const server = createServer();
  await new Promise((resolve, reject) => server.listen(0, '127.0.0.1', resolve).once('error', reject));
  const { port } = server.address();
  await new Promise(resolve => server.close(resolve));
  return port;
}
const corePort = await freePort();
let webPort = await freePort();
while (webPort === corePort) webPort = await freePort();
const coreUrl = `http://127.0.0.1:${corePort}`;
const webUrl = `http://127.0.0.1:${webPort}`;
const env = {
  ...process.env,
  SB_REVIEW_ROOT: dirs.review,
  SB_KNOWLEDGE_ROOT: dirs.knowledge,
  SB_PROMOTE_STATE_ROOT: dirs.state,
  SB_CAPTURE_RAW_ROOT: dirs.raw,
  SB_JOURNAL_ROOT: dirs.journal,
  SB_TASK_ROOT: dirs.task,
  SB_PROJECTS_INDEX_ROOT: dirs.projects,
  SB_DAILY_BRIEF_STORE_ROOT: dirs.briefs,
  SB_NOTES_DRAFTS_ROOT: dirs.notes,
  SB_APP_PASSWORD_FILE: passwordPath,
  SB_DASHBOARD_ORIGINS: webUrl,
  SB_CORE_ALLOWED_HOSTS: '127.0.0.1,localhost',
  SB_PROMOTE_ENABLED: 'false',
  SB_HERMES_API_URL: '',
  SB_PERSONAL_MEMORY_ENABLED: 'false',
  SB_PERSONAL_LEARNING_ENABLED: 'false',
  VITE_ENABLE_NOTES: 'true',
  SB_CORE_PROXY_TARGET: coreUrl,
  SB_E2E_BASE_URL: webUrl,
};
const children = [];
function start(command, args, cwd) {
  const child = spawn(command, args, { cwd, env, stdio: 'inherit' });
  children.push(child);
  return child;
}
async function waitReady(url, child) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`service exited before ready: ${url}`);
    try { const response = await fetch(url); if (response.ok) return; } catch {}
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  throw new Error(`service readiness timeout: ${url}`);
}
let browser;
try {
  const python = process.env.PYTHON ?? 'python';
  const core = start(python, ['-m', 'uvicorn', 'secondbrain_core.app:create_app', '--factory', '--host', '127.0.0.1', '--port', String(corePort)], coreDir);
  await waitReady(`${coreUrl}/health`, core);
  const web = process.env.SB_E2E_PRODUCTION_BUILD === 'true'
    ? start('npx', ['--no-install', 'vite', 'preview', '--host', '127.0.0.1', '--port', String(webPort), '--strictPort'], frontend)
    : start('npm', ['run', 'dev', '--', '--host', '127.0.0.1', '--port', String(webPort), '--strictPort'], frontend);
  await waitReady(`${webUrl}/chat/blank`, web);

  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await page.goto(`${webUrl}/chat/blank`);
  await page.getByLabel('SecondBrain 登录口令').fill('synthetic-wp5-dom-diagnostic-only');
  await page.getByRole('button', { name: '登录' }).click();
  await page.getByRole('heading', { name: '空白验收' }).waitFor();
  await page.locator('.sidebar nav').getByRole('button', { name: '笔记', exact: true }).click();
  await page.getByRole('button', { name: '新建富 Page', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'BlockSuite 富 Page 资源' });
  await dialog.waitFor();
  const host = dialog.locator('.blocksuite-resource-host.sb-archive-surface');
  await host.locator('.affine-page-viewport').waitFor();
  const richText = 'Synthetic rich page round trip';
  const initialBody = host.locator('affine-paragraph').filter({ hasText: '在这里开始编辑完整富格式内容。' });
  await initialBody.click();
  await page.keyboard.press('End');
  await page.keyboard.insertText(` ${richText}`);
  const initialResourceSave = page.waitForResponse(response => response.request().method() === 'PUT'
    && new URL(response.url()).pathname.includes('/blocksuite/resources/'));
  const initialMarkdownSave = page.waitForResponse(response => response.request().method() === 'PUT'
    && /\/api\/notes\/drafts\//.test(new URL(response.url()).pathname));
  await dialog.getByRole('button', { name: '保存资源', exact: true }).click();
  const saveResponses = await Promise.all([initialResourceSave, initialMarkdownSave]);
  if (saveResponses.some(response => response.status() !== 200)) throw new Error('Initial Rich Page save failed');
  await dialog.getByRole('button', { name: '关闭富 Page', exact: true }).click();
  await dialog.waitFor({ state: 'detached' });
  const reference = page.locator('.blocksuite-notes-canvas a').filter({ hasText: '富 Page 原生资源' }).last();
  await reference.click();
  await dialog.waitFor();
  await host.locator('.affine-page-viewport').waitFor();
  await dialog.getByText('属性', { exact: true }).click();
  const modeGroup = dialog.getByRole('group', { name: '文档模式' });
  await modeGroup.getByRole('button', { name: '画布', exact: true }).click();
  await host.locator('.affine-edgeless-viewport').waitFor();
  const propertiesPanel = dialog.locator('details.sb-properties-info');
  if (!await propertiesPanel.evaluate(details => details.open)) await propertiesPanel.locator('summary').click();
  await dialog.getByRole('group', { name: '文档模式' }).getByRole('button', { name: '页面', exact: true }).click();
  await host.locator('.affine-page-viewport').waitFor();
  await dialog.getByText(richText, { exact: false }).waitFor();
  const bodyParagraph = host.locator('affine-paragraph').filter({ hasText: richText });
  // Reproduce the archive UX steps that precede the failing table input:
  // split a paragraph, add/reorder a paragraph, then format it with toolbars.
  await bodyParagraph.locator('rich-text .inline-editor').click();
  await page.keyboard.press('End');
  await page.keyboard.press('Enter');
  await page.keyboard.insertText('Archive reorder target');
  const targetParagraph = host.locator('affine-paragraph').filter({ hasText: 'Archive reorder target' });
  await targetParagraph.waitFor();
  const plus = dialog.locator('sb-desktop-page-plus-widget button[data-kind="plus"]');
  const grip = dialog.locator('sb-desktop-page-plus-widget button[data-kind="grip"]');
  await targetParagraph.hover();
  await plus.click();
  await page.getByTestId('一级标题').click();
  await targetParagraph.click();
  await page.keyboard.press('End');
  await page.keyboard.press('Shift+Home');
  await dialog.getByRole('button', { name: '加粗', exact: true }).click();
  await targetParagraph.click();
  await page.keyboard.press('End');
  await page.keyboard.press('Shift+Home');
  await dialog.getByRole('button', { name: '居中对齐', exact: true }).click();
  await targetParagraph.hover();
  const dragGeometry = await Promise.all([grip, bodyParagraph].map(locator => locator.boundingBox()));
  const blockOrder = await host.locator('.affine-page-viewport').evaluate(viewport => {
    const store = viewport.closest('.blocksuite-resource-host')?.__sbBlockSuiteStore;
    return (store?.getBlocksByFlavour('affine:paragraph') ?? []).map(({ model }) => {
      const parent = store.getParent(model);
      return { id: model.id, text: model.props.text?.toString?.() ?? '', parent: parent?.id ?? null,
        order: parent?.children?.findIndex(child => child.id === model.id) ?? -1 };
    });
  });
  const source = blockOrder.find(block => block.text.includes('Archive reorder target'));
  const destination = blockOrder.find(block => block.text.includes(richText));
  if (!source || !destination || source.parent !== destination.parent || !dragGeometry[0] || !dragGeometry[1]) {
    throw new Error('Archive drag precondition did not match the formal journey');
  }
  const sourceBeforeTarget = source.order < destination.order;
  await page.mouse.move(dragGeometry[0].x + dragGeometry[0].width / 2, dragGeometry[0].y + dragGeometry[0].height / 2);
  await page.mouse.down();
  const dropY = sourceBeforeTarget ? dragGeometry[1].y + dragGeometry[1].height - 1 : dragGeometry[1].y + 1;
  await page.mouse.move(dragGeometry[1].x + dragGeometry[1].width / 3, dropY, { steps: 5 });
  await page.mouse.up();
  await page.waitForTimeout(300);
  await page.evaluate(() => {
    window.__wp5CellEvents = [];
    for (const name of ['pointerdown', 'click', 'focusin', 'focusout']) {
      document.addEventListener(name, event => {
        const path = event.composedPath().slice(0, 8).map(node => node instanceof Element
          ? `${node.tagName.toLowerCase()}${node.id ? `#${node.id}` : ''}${node.className && typeof node.className === 'string' ? `.${node.className.trim().replace(/\s+/g, '.')}` : ''}`
          : node.constructor?.name ?? String(node));
        window.__wp5CellEvents.push({ type: name, target: event.target instanceof Element ? event.target.tagName : String(event.target), path,
          active: document.activeElement?.tagName ?? null });
      }, true);
    }
  });
  await targetParagraph.hover();
  await dialog.locator('sb-desktop-page-plus-widget button[data-kind="plus"]').click();
  await page.getByTestId('普通表格').click();
  const table = host.locator('affine-table').last();
  await table.waitFor();
  const cells = table.locator('td[data-row-id][data-column-id]');
  await page.waitForFunction(() => document.querySelectorAll('affine-table td[data-row-id][data-column-id]').length >= 4);
  const cellIds = [];
  for (let index = 0; index < 2; index += 1) {
    const cell = cells.nth(index);
    cellIds.push({ row: await cell.getAttribute('data-row-id'), column: await cell.getAttribute('data-column-id') });
  }
  const firstCellEditor = cells.nth(0).locator('rich-text .inline-editor');
  const editableAtCheckpoint = await cells.nth(0).evaluate(targetCell => Boolean(targetCell.querySelector('rich-text .inline-editor[contenteditable="true"]')));
  console.log('WP5_TABLE_DOM_AT_CHECKPOINT_038', JSON.stringify({ cellIds, editableAtCheckpoint }));
  const waitForCellFocus = async (cell, label) => {
    try {
      await page.waitForFunction(target => {
        const td = document.querySelector(`td[data-row-id="${target.row}"][data-column-id="${target.column}"]`);
        const editor = td?.querySelector('rich-text .inline-editor[contenteditable="true"]');
        return Boolean(editor && document.activeElement === editor);
      }, cell, { timeout: 1200 });
      console.log('WP5_TABLE_DOM_FOCUS_READY', JSON.stringify({ label, focused: true }));
    } catch {
      const state = await cells.nth(label === 'first' ? 0 : 1).evaluate(targetCell => {
        const editor = targetCell.querySelector('rich-text .inline-editor[contenteditable="true"]');
        return { activeTag: document.activeElement?.tagName ?? null,
          activeClass: document.activeElement?.getAttribute('class') ?? null,
          activeInsideCell: Boolean(editor && editor === document.activeElement),
          contenteditable: editor?.getAttribute('contenteditable') ?? null };
      });
      console.log('WP5_TABLE_DOM_FOCUS_MISSED', JSON.stringify({ label, state, events: await page.evaluate(() => window.__wp5CellEvents) }));
    }
  };
  await firstCellEditor.click();
  await waitForCellFocus(cellIds[0], 'first');
  await page.keyboard.insertText('WP5-DOM-DIAGNOSTIC-CELL-EDIT');
  await page.waitForTimeout(500);
  const afterEdit = await table.evaluate((element, ids) => ids.map(({ row, column }) => {
    const td = element.querySelector(`td[data-row-id="${row}"][data-column-id="${column}"]`);
    const richText = td?.querySelector('rich-text');
    let editor = null;
    const walk = root => { for (const node of root.querySelectorAll('*')) { if (node.matches('.inline-editor')) return node; if (node.shadowRoot) { const found = walk(node.shadowRoot); if (found) return found; } } return null; };
    editor = richText ? walk(richText) : null;
    const cell = element.dataManager?.getCell?.(row, column);
    let active = document.activeElement;
    while (active?.shadowRoot?.activeElement) active = active.shadowRoot.activeElement;
    const selection = window.getSelection();
    return { tdHtml: td?.innerHTML ?? null, contenteditable: editor?.getAttribute('contenteditable') ?? null,
      activeTag: active?.tagName ?? null, activeClass: active?.getAttribute('class') ?? null,
      activeInsideCell: Boolean(td && active && td.contains(active)),
      selectionCollapsed: selection?.isCollapsed ?? null,
      selectionAnchorInsideCell: Boolean(selection?.anchorNode && td?.contains(selection.anchorNode)),
      yText: cell?.text?.toString?.() ?? null, yLength: cell?.text?.length ?? null };
  }), cellIds);
  console.log('WP5_TABLE_DOM_AFTER_EDIT', JSON.stringify({ state: afterEdit, events: await page.evaluate(() => window.__wp5CellEvents) }));
  if (!afterEdit[0]?.yText?.includes('WP5-DOM-DIAGNOSTIC-CELL-EDIT')) {
    throw new Error('The first table cell did not receive the diagnostic text in its Yjs text model');
  }
  await cells.nth(1).locator('rich-text .inline-editor').click();
  await waitForCellFocus(cellIds[1], 'second');
  await page.waitForTimeout(150);
  await page.keyboard.insertText('WP5-DOM-DIAGNOSTIC-DELAYED-EDIT');
  await page.waitForTimeout(300);
  const delayedEdit = await table.evaluate((element, id) => {
    const cell = element.dataManager?.getCell?.(id.row, id.column);
    const td = element.querySelector(`td[data-row-id="${id.row}"][data-column-id="${id.column}"]`);
    const editor = td?.querySelector('rich-text .inline-editor');
    return { yText: cell?.text?.toString?.() ?? null, yLength: cell?.text?.length ?? null,
      contenteditable: editor?.getAttribute('contenteditable') ?? null,
      activeTag: document.activeElement?.tagName ?? null,
      activeInsideCell: Boolean(td?.contains(document.activeElement)) };
  }, cellIds[1]);
  console.log('WP5_TABLE_DOM_DELAYED_INPUT', JSON.stringify({ state: delayedEdit, events: await page.evaluate(() => window.__wp5CellEvents) }));
} finally {
  if (browser) await browser.close();
  for (const child of children.reverse()) child.kill('SIGTERM');
  await rm(temp, { recursive: true, force: true });
}
