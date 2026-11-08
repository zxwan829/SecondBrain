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
  const paragraph = dialog.locator('.affine-page-viewport affine-paragraph')
    .filter({ hasText: '在这里开始编辑完整富格式内容。' }).first();
  await paragraph.locator('rich-text .inline-editor').click();
  await page.keyboard.press('End');
  await page.keyboard.press('/');
  await page.waitForTimeout(600);
  const keyboardEvidence = await page.evaluate(() => {
    const root = document.querySelector('.blocksuite-resource-host');
    const paragraph = [...document.querySelectorAll('.affine-page-viewport affine-paragraph')]
      .find(item => item.textContent?.includes('在这里开始编辑完整富格式内容。'));
    const rich = paragraph?.querySelector('rich-text');
    const editor = rich?.querySelector('.inline-editor') ?? null;
    const selection = window.getSelection();
    const text = paragraph?.textContent ?? '';
    const menus = [...document.querySelectorAll('affine-slash-menu, inner-slash-menu')].map(menu => {
      const style = getComputedStyle(menu);
      const rect = menu.getBoundingClientRect();
      return { tag: menu.tagName.toLowerCase(), testIds: [...menu.querySelectorAll('[data-testid]')].map(item => item.getAttribute('data-testid')),
        visible: style.visibility, display: style.display, opacity: style.opacity, zIndex: style.zIndex,
        rect: [rect.x, rect.y, rect.width, rect.height], itemTextPresent: menu.textContent?.includes('插入表情图标') ?? false };
    });
    const modelId = paragraph?.getAttribute('data-block-id') ?? '';
    const model = modelId ? root?.__sbBlockSuiteStore?.getBlock(modelId)?.model : undefined;
    let inlineRange = null;
    try { inlineRange = rich?.inlineEditor?.getInlineRange?.() ?? null; } catch {}
    return {
      stage: 'keyboard-slash', blockTag: paragraph?.tagName.toLowerCase() ?? null,
      textEndsWithSlash: text.endsWith('/'), yTextLength: model?.text?.length ?? model?.props?.text?.length ?? null,
      activeTag: document.activeElement?.tagName ?? null,
      activeIsTargetEditor: document.activeElement === editor,
      activeContenteditable: document.activeElement?.getAttribute?.('contenteditable') ?? null,
      selectionAnchorTag: selection?.anchorNode instanceof Element ? selection.anchorNode.tagName : selection?.anchorNode?.parentElement?.tagName ?? null,
      selectionAnchorOffset: selection?.anchorOffset ?? null,
      selectionIsInsideEditor: Boolean(selection?.anchorNode && editor?.contains(selection.anchorNode)),
      inlineRange, textSelectionApiPresent: typeof root?.__sbBlockSuiteStd?.selection?.find === 'function',
      slashMenuWidgetCount: document.querySelectorAll('affine-slash-menu-widget').length,
      slashMenuCount: menus.length, emojiCommandCount: document.querySelectorAll('[data-testid="插入表情图标"]').length, menus,
    };
  });
  console.log('WP5_INDEPENDENT_SLASH_DOM ' + JSON.stringify(keyboardEvidence));

  await page.keyboard.press('Escape');
  await paragraph.hover();
  const plus = dialog.locator('sb-desktop-page-plus-widget button[data-kind="plus"]');
  await plus.waitFor({ state: 'visible' });
  await plus.click();
  await page.waitForTimeout(300);
  const plusEvidence = await page.evaluate(() => ({
    stage: 'leading-plus',
    menuCount: document.querySelectorAll('affine-slash-menu, inner-slash-menu').length,
    emojiCommandCount: document.querySelectorAll('[data-testid="插入表情图标"]').length,
    commandVisible: [...document.querySelectorAll('[data-testid="插入表情图标"]')].some(element => {
      const rect = element.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0 && getComputedStyle(element).visibility !== 'hidden';
    }),
  }));
  console.log('WP5_INDEPENDENT_SLASH_DOM ' + JSON.stringify(plusEvidence));
} finally {
  await browser.close();
}
