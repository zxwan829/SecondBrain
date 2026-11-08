import { readFile, writeFile } from 'node:fs/promises';
import { chromium, expect } from '@playwright/test';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const marker = 'WP5 minimal undo marker';
const password = (await readFile(process.env.SB_E2E_PASSWORD_FILE, 'utf8')).trim();

const readState = () => page.locator('.blocksuite-resource-host').evaluate((host, value) => {
  const store = host.__sbBlockSuiteStore;
  const blocks = store?.getBlocksByFlavour('affine:paragraph') ?? [];
  const text = blocks.map(({ model }) => model.props.text?.toString?.() ?? '').join('\n');
  const selection = window.getSelection();
  const anchor = selection?.anchorNode instanceof Element ? selection.anchorNode : selection?.anchorNode?.parentElement;
  const editable = anchor?.closest('[contenteditable="true"]') ?? null;
  const active = document.activeElement;
  const paragraph = [...host.querySelectorAll('affine-paragraph')].find(element => element.textContent?.includes(value));
  const richText = paragraph?.querySelector('rich-text');
  return {
    markerPresent: text.includes(value),
    paragraphTypes: blocks.map(({ model }) => model.props.type ?? 'text'),
    contenteditable: editable?.getAttribute('contenteditable') ?? null,
    selectionInsideEditor: Boolean(selection?.anchorNode && editable?.contains(selection.anchorNode)),
    selectionCollapsed: selection?.isCollapsed ?? null,
    activeTag: active?.tagName ?? null,
    inlineRangeIndex: richText?.inlineEditor?.getInlineRange?.()?.index ?? null,
  };
}, marker);

try {
  const baseUrl = process.env.SB_E2E_BASE_URL;
  if (!baseUrl) throw new Error('isolated synthetic base URL was not configured');
  await page.goto(new URL('/chat/blank', baseUrl).toString());
  await page.getByLabel('SecondBrain 登录口令').fill(password);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page.getByRole('heading', { name: '空白验收' })).toBeVisible();
  await page.locator('.sidebar nav').getByRole('button', { name: '笔记', exact: true }).click();
  await page.getByRole('button', { name: '新建笔记', exact: true }).click();
  const editor = page.locator('.blocksuite-resource-inline');
  await expect(editor).toBeVisible();
  await expect(editor).toHaveAttribute('aria-busy', 'false');
  const body = editor.locator('.blocksuite-resource-host .affine-page-viewport affine-paragraph').nth(1);
  await body.click();
  const inline = body.locator('rich-text .inline-editor');
  await expect(inline).toHaveAttribute('contenteditable', 'true');
  await expect.poll(() => inline.evaluate(node => {
    const selection = window.getSelection();
    return Boolean(selection?.anchorNode && node.contains(selection.anchorNode));
  })).toBe(true);
  const beforeUndo = await readState();
  await page.keyboard.insertText(marker);
  await expect.poll(async () => (await readState()).markerPresent).toBe(true);
  const afterInsert = await readState();
  await page.keyboard.press('Control+z');
  await page.waitForTimeout(750);
  const afterUndo = await readState();
  await page.keyboard.press('Control+Shift+z');
  await page.waitForTimeout(750);
  const afterRedo = await readState();
  await page.screenshot({ path: process.env.SB_WP5_UNDO_REPRO_SCREENSHOT_PATH, fullPage: false });
  const evidence = { scope: 'synthetic isolated Notes page', viewport: '1440x1000',
    sequence: { beforeUndo, afterInsert, afterUndo, afterRedo },
    undoRemovedTypedText: !afterUndo.markerPresent, redoRestoredTypedText: afterRedo.markerPresent,
    observationOnly: true };
  await writeFile(process.env.SB_WP5_UNDO_REPRO_JSON_PATH, JSON.stringify(evidence, null, 2));
  process.stdout.write(`WP5_UNDO_MINIMAL_REPRO ${JSON.stringify(evidence)}\n`);
} finally {
  await browser.close();
}
