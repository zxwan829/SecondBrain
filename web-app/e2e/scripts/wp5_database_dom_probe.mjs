import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright';

const baseURL = process.env.SB_WP5_DOM_PROBE_URL;
const passwordPath = process.env.SB_E2E_PASSWORD_FILE;
if (!baseURL || !passwordPath) throw new Error('diagnostic environment is incomplete');
const password = (await readFile(passwordPath, 'utf8')).trim();
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
const emit = (stage, state) => console.log(`WP5_DATABASE_DOM ${JSON.stringify({ stage, ...state })}`);

async function inspect(host) {
  return host.evaluate(resourceHost => {
    const walk = (root, output = []) => {
      for (const element of root.children ?? []) {
        output.push(element);
        if (element.shadowRoot) walk(element.shadowRoot, output);
        walk(element, output);
      }
      return output;
    };
    const elements = walk(resourceHost);
    const database = elements.find(element => element.localName === 'affine-database');
    const component = database;
    const model = component?.model;
    const source = component?.dataSource?.value;
    const store = resourceHost.__sbBlockSuiteStore;
    const doc = store?.spaceDoc;
    const columns = model?.props?.columns$?.value ?? [];
    const rows = model?.children ?? [];
    const cellValues = rows.map(row => ({ rowId: row.id,
      values: columns.map(column => ({ name: column.name,
        value: source?.cellValueGet?.(row.id, column.id)?.toString?.() ?? '' })) }));
    const active = document.activeElement;
    const selection = document.getSelection();
    return {
      dialogBusy: resourceHost.closest('[role="dialog"]')?.getAttribute('aria-busy') ?? null,
      databaseFound: Boolean(database), databaseTag: database?.localName ?? null,
      databaseConnected: database?.isConnected ?? false,
      dataSourceReady: Boolean(source), propertyAddType: typeof source?.propertyAdd,
      cellValueChangeType: typeof source?.cellValueChange,
      rowCount: rows.length, rowIds: rows.map(row => row.id),
      columns: columns.map(column => ({ id: column.id, name: column.name, type: column.type })),
      cellValues,
      viewCount: model?.props?.views?.length ?? model?.props?.views$?.value?.length ?? null,
      kanbanGroupCount: elements.filter(element => element.localName === 'affine-data-view-kanban-group').length,
      kanbanCardCount: elements.filter(element => element.localName === 'affine-data-view-kanban-card').length,
      kanbanText: elements.filter(element => element.localName === 'affine-data-view-kanban-group'
        || element.localName === 'affine-data-view-kanban-card').map(element => (element.textContent ?? '').trim().slice(0, 180)),
      editorFocus: active ? { tag: active.tagName, id: active.id || null,
        contenteditable: active.getAttribute('contenteditable') } : null,
      contenteditables: elements.filter(element => element.hasAttribute('contenteditable'))
        .map(element => ({ tag: element.tagName, value: element.getAttribute('contenteditable') })).slice(0, 16),
      selection: selection ? { anchorTag: selection.anchorNode?.parentElement?.tagName ?? selection.anchorNode?.nodeName ?? null,
        anchorOffset: selection.anchorOffset, focusTag: selection.focusNode?.parentElement?.tagName ?? selection.focusNode?.nodeName ?? null,
        focusOffset: selection.focusOffset, textLength: selection.toString().length } : null,
      yjs: doc ? { guid: doc.guid, clientCount: doc.store?.clients?.size ?? null,
        sharedTypeCount: doc.share?.size ?? null, localState: doc.getMap?.('secondbrain-rich-page-properties')?.toJSON?.() ?? {} } : null,
    };
  });
}

try {
  await page.goto(`${baseURL}/chat/blank`);
  await page.getByLabel('SecondBrain 登录口令').fill(password);
  await page.getByRole('button', { name: '登录' }).click();
  await page.getByRole('heading', { name: '空白验收' }).waitFor({ state: 'visible', timeout: 15000 });
  await page.locator('.sidebar nav').getByRole('button', { name: '笔记', exact: true }).click();
  await page.waitForURL(/\/notes(?:\?.*)?$/);

  const title = 'WP5 standalone Database DOM probe';
  const markdown = `---\ntitle: ${title}\ntags: []\n---\n\n# ${title}\n\nSynthetic Database DOM probe.\n`;
  const seeded = await page.evaluate(async content => {
    const response = await fetch('/api/notes', { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }) });
    return { status: response.status, note: response.ok ? await response.json() : null };
  }, markdown);
  if (seeded.status !== 200 || seeded.note?.collection !== 'drafts') throw new Error(`synthetic note seed status ${seeded.status}`);
  await page.reload();
  await page.getByRole('button', { name: title, exact: true }).click();
  await page.locator('.blocksuite-notes-canvas').waitFor({ state: 'visible', timeout: 20000 });
  await page.locator('.notes-document-heading [role="status"]').getByText('已保存').waitFor({ state: 'visible', timeout: 15000 });

  const resourcePost = page.waitForResponse(response => response.request().method() === 'POST'
    && new URL(response.url()).pathname === `/api/notes/drafts/${seeded.note.path}/blocksuite/resources`);
  await page.getByRole('button', { name: '新建 BlockSuite Database', exact: true }).click();
  const resourceResponse = await resourcePost;
  if (resourceResponse.status() !== 200) throw new Error(`resource create status ${resourceResponse.status()}`);
  const resource = await resourceResponse.json();
  const dialog = page.getByRole('dialog', { name: 'BlockSuite 数据库资源' });
  await dialog.waitFor({ state: 'visible', timeout: 20000 });
  const host = dialog.locator('.blocksuite-resource-host');
  await host.getByText('测试数据库', { exact: true }).waitFor({ state: 'visible', timeout: 15000 });
  const database = host.locator('affine-database').first();
  await database.waitFor({ state: 'attached', timeout: 15000 });
  emit('created_before_group_change', await inspect(host));

  const seededGroup = await database.evaluate(element => {
    const component = element;
    const source = component.dataSource?.value;
    const columnId = source?.propertyAdd?.('end', { type: 'select', name: '状态' });
    const rowId = component.model?.children?.[0]?.id;
    if (!source || !columnId || !rowId) return { ok: false,
      sourceReady: Boolean(source), columnId: Boolean(columnId), rowCount: component.model?.children?.length ?? null };
    source.propertyDataSet?.(columnId, { options: [{ id: 'wp5-in-progress', value: '进行中', color: '#3b82f6' }] });
    source.cellValueChange?.(rowId, columnId, 'wp5-in-progress');
    return { ok: true, rowId, columnId };
  });
  emit('seeded_select_group', seededGroup);
  if (!seededGroup.ok) throw new Error('Database datasource/model row unavailable in standalone DOM probe');

  const addView = host.getByTestId('database-add-view-button');
  await addView.waitFor({ state: 'visible', timeout: 10000 });
  await addView.click();
  const menuItem = page.getByText('看板视图', { exact: true }).last();
  await menuItem.waitFor({ state: 'visible', timeout: 10000 });
  await menuItem.click();
  await page.waitForFunction(() => document.querySelectorAll('affine-data-view-kanban-group').length > 0,
    null, { timeout: 10000 }).catch(() => {});
  emit('kanban_rendered', await inspect(host));

  const saveResponse = page.waitForResponse(response => response.request().method() === 'PUT'
    && new URL(response.url()).pathname === `/api/notes/drafts/${seeded.note.path}/blocksuite/resources/${resource.resource_id}`);
  await dialog.getByRole('button', { name: '保存资源', exact: true }).click();
  const saved = await saveResponse;
  emit('saved_status', { status: saved.status(), text: await dialog.getByRole('status').textContent() });
  await dialog.getByRole('button', { name: '关闭', exact: true }).click();
  const reference = page.locator('.blocksuite-notes-canvas a').filter({ hasText: 'BlockSuite resource' }).last();
  await reference.waitFor({ state: 'visible', timeout: 10000 });
  await reference.click();
  const reopenedDialog = page.getByRole('dialog', { name: 'BlockSuite 数据库资源' });
  await reopenedDialog.waitFor({ state: 'visible', timeout: 15000 });
  await reopenedDialog.locator('.blocksuite-resource-host affine-database').first().waitFor({ state: 'attached', timeout: 15000 });
  emit('resource_reopened', await inspect(reopenedDialog.locator('.blocksuite-resource-host')));

  await reopenedDialog.getByRole('button', { name: '关闭', exact: true }).click();
  await page.reload();
  await page.getByRole('button', { name: title, exact: true }).click();
  await page.locator('.blocksuite-notes-canvas').waitFor({ state: 'visible', timeout: 15000 });
  await page.locator('.blocksuite-notes-canvas a').filter({ hasText: 'BlockSuite resource' }).last().click();
  const refreshedDialog = page.getByRole('dialog', { name: 'BlockSuite 数据库资源' });
  await refreshedDialog.waitFor({ state: 'visible', timeout: 15000 });
  emit('after_note_reload', await inspect(refreshedDialog.locator('.blocksuite-resource-host')));
  console.log('WP5_DATABASE_DOM_PROBE_COMPLETE');
} catch (error) {
  const state = await page.locator('.blocksuite-resource-host').last().evaluate(inspect).catch(() => null);
  emit('probe_error', { name: error?.name ?? 'Error', message: String(error?.message ?? error).slice(0, 240), state });
  process.exitCode = 1;
} finally {
  await context.close();
  await browser.close();
}
