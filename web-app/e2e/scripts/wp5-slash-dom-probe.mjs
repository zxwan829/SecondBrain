import fs from 'node:fs';
import { chromium } from 'playwright';

const base = process.env.WP5_DOM_PROBE_URL;
const password = fs.readFileSync(process.env.WP5_DOM_PROBE_PASSWORD_FILE, 'utf8').trim();
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
try {
  await page.goto(`${base}/chat/blank`);
  await page.getByLabel('SecondBrain 登录口令').fill(password);
  await page.getByRole('button', { name: '登录' }).click();
  await page.getByRole('heading', { name: '空白验收' }).waitFor();
  await page.locator('.sidebar nav').getByRole('button', { name: '笔记', exact: true }).click();
  await page.getByRole('button', { name: '新建富 Page', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'BlockSuite 富 Page 资源' });
  await dialog.waitFor({ state: 'visible' });
  const placeholder = dialog.locator('.affine-page-viewport affine-paragraph')
    .filter({ hasText: '在这里开始编辑完整富格式内容。' }).first();
  await placeholder.locator('rich-text .inline-editor').click();
  await page.keyboard.insertText('Synthetic rich page round trip');
  const paragraph = dialog.locator('.affine-page-viewport affine-paragraph')
    .filter({ hasText: 'Synthetic rich page round trip' }).first();
  await paragraph.waitFor({ state: 'visible' });
  await paragraph.locator('rich-text .inline-editor').click();
  await page.keyboard.press('End');
  await page.keyboard.press('/');
  await page.waitForTimeout(600);
  const keyboardEvidence = await paragraph.evaluate(paragraph => {
    const root = document.querySelector('.blocksuite-resource-host');
    const deepQueryAll = (base, selector) => {
      const found = [];
      const visit = node => {
        if (node instanceof Element && node.matches(selector)) found.push(node);
        for (const child of node.children ?? []) visit(child);
        if (node.shadowRoot) visit(node.shadowRoot);
      };
      visit(base);
      return found;
    };
    const composedContains = (base, node) => {
      let current = node;
      while (current) {
        if (current === base) return true;
        current = current instanceof ShadowRoot ? current.host : current.parentNode;
      }
      return false;
    };
    const rich = deepQueryAll(paragraph, 'rich-text')[0];
    const editor = deepQueryAll(paragraph, '.inline-editor')[0] ?? null;
    const selection = window.getSelection();
    const modelId = paragraph.getAttribute('data-block-id') ?? '';
    const model = modelId ? root?.__sbBlockSuiteStore?.getBlock(modelId)?.model : undefined;
    const menus = deepQueryAll(document, 'affine-slash-menu, inner-slash-menu').map(menu => {
      const style = getComputedStyle(menu);
      const rect = menu.getBoundingClientRect();
      const item = deepQueryAll(menu, '[data-testid="插入表情图标"]')[0];
      const panel = menu.shadowRoot?.querySelector('.slash-menu');
      const panelRect = panel?.getBoundingClientRect();
      const itemRect = item?.getBoundingClientRect();
      return { tag: menu.tagName.toLowerCase(), testIds: deepQueryAll(menu, '[data-testid]').map(item => item.getAttribute('data-testid')),
        visible: style.visibility, display: style.display, opacity: style.opacity, zIndex: style.zIndex,
        rect: [rect.x, rect.y, rect.width, rect.height], cssPopoverLayer: style.getPropertyValue('--affine-z-index-popover').trim(),
        panel: panelRect ? { rect: [panelRect.x, panelRect.y, panelRect.width, panelRect.height],
          visibility: getComputedStyle(panel).visibility, zIndex: getComputedStyle(panel).zIndex,
          transform: getComputedStyle(panel).transform } : null,
        itemRect: itemRect ? [itemRect.x, itemRect.y, itemRect.width, itemRect.height] : null, emojiItemPresent: Boolean(item) };
    });
    const nativeRange = selection?.rangeCount ? selection.getRangeAt(0) : null;
    const rangeRect = nativeRange?.getBoundingClientRect();
    const backdrop = document.querySelector('.blocksuite-resource-backdrop');
    let inlineRange = null;
    try { inlineRange = rich?.inlineEditor?.getInlineRange?.() ?? null; } catch {}
    return {
      stage: 'keyboard-slash', blockTag: paragraph.tagName.toLowerCase(),
      textEndsWithSlash: model?.text?.toString?.().endsWith('/') ?? false,
      yTextLength: model?.text?.length ?? model?.props?.text?.length ?? null,
      activeTag: document.activeElement?.tagName ?? null,
      activeIsTargetEditor: document.activeElement === editor,
      activeContenteditable: document.activeElement?.getAttribute?.('contenteditable') ?? null,
      selectionAnchorTag: selection?.anchorNode instanceof Element ? selection.anchorNode.tagName : selection?.anchorNode?.parentElement?.tagName ?? null,
      selectionAnchorOffset: selection?.anchorOffset ?? null,
      selectionIsInsideEditor: Boolean(selection?.anchorNode && composedContains(editor, selection.anchorNode)),
      inlineRange, nativeRangeRect: rangeRect ? [rangeRect.x, rangeRect.y, rangeRect.width, rangeRect.height] : null,
      nativeRangeClientRects: nativeRange ? Array.from(nativeRange.getClientRects()).map(rect => [rect.x, rect.y, rect.width, rect.height]) : [],
      backdrop: backdrop ? { zIndex: getComputedStyle(backdrop).zIndex, rect: (() => { const r = backdrop.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })() } : null,
      textSelectionApiPresent: typeof root?.__sbBlockSuiteStd?.selection?.find === 'function',
      slashMenuWidgetCount: document.querySelectorAll('affine-slash-menu-widget').length,
      slashMenuCount: menus.length, emojiCommandCount: menus.filter(menu => menu.emojiItemPresent).length, menus,
    };
  });
  console.log('WP5_INDEPENDENT_SLASH_DOM ' + JSON.stringify(keyboardEvidence));

  await page.keyboard.press('Escape');
  await paragraph.hover();
  const plus = dialog.locator('sb-desktop-page-plus-widget button[data-kind="plus"]');
  await plus.waitFor({ state: 'visible' });
  await plus.click();
  await page.waitForTimeout(300);
  const plusEvidence = await page.evaluate(() => {
    const deepQueryAll = (base, selector) => {
      const found = [];
      const visit = node => {
        if (node instanceof Element && node.matches(selector)) found.push(node);
        for (const child of node.children ?? []) visit(child);
        if (node.shadowRoot) visit(node.shadowRoot);
      };
      visit(base);
      return found;
    };
    const items = deepQueryAll(document, '[data-testid="插入表情图标"]');
    return {
    stage: 'leading-plus',
    menuCount: deepQueryAll(document, 'affine-slash-menu, inner-slash-menu').length,
    emojiCommandCount: items.length,
    commandVisible: items.some(element => {
      const rect = element.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0 && getComputedStyle(element).visibility !== 'hidden';
    }),
  }; });
  console.log('WP5_INDEPENDENT_SLASH_DOM ' + JSON.stringify(plusEvidence));
} finally {
  await browser.close();
}
