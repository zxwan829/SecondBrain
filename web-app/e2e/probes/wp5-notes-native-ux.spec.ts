import { expect, test } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';

const enabled = process.env.SB_WP5_NATIVE_UX_PROBE_ONLY === 'true';
const baseUrl = process.env.SB_E2E_BASE_URL ?? 'http://127.0.0.1:4173';

test.skip(!enabled, 'Run only from the independent WP5 Linux Chromium probe entry point.');

test.afterEach(async ({ page }, testInfo) => {
  if (testInfo.status === 'passed' || testInfo.status === 'skipped'
      || !process.env.SB_WP5_NATIVE_FAILURE_EVIDENCE_PATH) return;
  const failure = await page.evaluate(() => {
    const selection = window.getSelection();
    const anchor = selection?.anchorNode instanceof Element ? selection.anchorNode : selection?.anchorNode?.parentElement;
    const editable = anchor?.closest('[contenteditable="true"]') ?? null;
    const root = document.querySelector('.notes-document-rich-page');
    const host = root?.querySelector<HTMLElement>('.blocksuite-resource-host') as (HTMLElement & { __sbBlockSuiteStore?: any }) | null;
    const store = host?.__sbBlockSuiteStore;
    const blocks = (store?.getBlocksByFlavour('affine:paragraph') ?? []).map(({ model }: any) => ({
      idLength: String(model.id ?? '').length, text: model.props.text?.toString?.() ?? '', type: model.props.type ?? 'text',
    }));
    const active = document.activeElement as HTMLElement | null;
    return { result: 'FAIL', viewport: `${window.innerWidth}x${window.innerHeight}`,
      activeTag: active?.tagName ?? null, activeRole: active?.getAttribute('role') ?? null,
      contenteditable: editable?.getAttribute('contenteditable') ?? null,
      selectionInsideEditor: Boolean(selection?.anchorNode && editable?.contains(selection.anchorNode)),
      selectionCollapsed: selection?.isCollapsed ?? null, selectionOffset: selection?.anchorOffset ?? null,
      titleBlockDisplay: host?.querySelector('[data-sb-document-title-block="true"]')
        ? getComputedStyle(host.querySelector('[data-sb-document-title-block="true"]')!).display : null,
      blocks, editorVisible: Boolean(root?.querySelector('.blocksuite-resource-inline')),
      modalCount: document.querySelectorAll('.blocksuite-resource-backdrop').length };
  }).catch(() => ({ result: 'FAIL', viewport: 'unknown', activeTag: null, activeRole: null,
    contenteditable: null, selectionInsideEditor: false, selectionCollapsed: null, selectionOffset: null,
    titleBlockDisplay: null, blocks: [], editorVisible: false, modalCount: 0 }));
  await writeFile(process.env.SB_WP5_NATIVE_FAILURE_EVIDENCE_PATH, JSON.stringify(failure, null, 2));
  const screenshotPath = process.env.SB_WP5_NATIVE_SCREENSHOT_PATH;
  if (screenshotPath) await page.screenshot({ path: screenshotPath, fullPage: false }).catch(() => undefined);
  if (testInfo.title === 'WP5 independent nested canvas open minimal reproduction') {
    const canvasOpenState = await page.evaluate(() => {
      const visible = (element: Element | null) => Boolean(element && (element as HTMLElement).getClientRects().length);
      const buttons = [...document.querySelectorAll<HTMLButtonElement>('.canvas-b-card button')]
        .filter(button => button.textContent?.trim() === '打开编辑');
      return {
        galleryExpanded: document.querySelector<HTMLElement>('.blocksuite-canvas-tools')?.hasAttribute('open') ?? false,
        canvasCardCount: document.querySelectorAll('.canvas-b-card').length,
        openButtonCount: buttons.length,
        openButtonsEnabled: buttons.filter(button => !button.disabled).length,
        resourceDialogVisible: visible(document.querySelector('[role="dialog"][aria-label="BlockSuite Edgeless 资源"]')),
        nestedEditorVisible: visible(document.querySelector('.blocksuite-resource-backdrop [data-kind="edgeless-canvas"]')),
      };
    }).catch(() => ({ galleryExpanded: false, canvasCardCount: 0, openButtonCount: 0,
      openButtonsEnabled: 0, resourceDialogVisible: false, nestedEditorVisible: false }));
    await writeFile(process.env.SB_WP5_NATIVE_CANVAS_OPEN_FAILURE_EVIDENCE_PATH!, JSON.stringify({
      result: 'FAIL', scope: 'independent synthetic canvas-open repro', viewport: '1440x1000', canvasOpenState,
    }, null, 2));
    const canvasFailureScreenshot = process.env.SB_WP5_NATIVE_CANVAS_OPEN_FAILURE_SCREENSHOT_PATH;
    if (canvasFailureScreenshot) await page.screenshot({ path: canvasFailureScreenshot, fullPage: false }).catch(() => undefined);
  }
});

test('WP5 native Notes: create, Enter, save, switch, reopen and refresh', async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.addInitScript(() => {
    (window as Window & { __wp5ReadyEvents?: unknown[] }).__wp5ReadyEvents = [];
    window.addEventListener('sb:blocksuite-editor-ready', event =>
      (window as Window & { __wp5ReadyEvents?: unknown[] }).__wp5ReadyEvents?.push((event as CustomEvent).detail));
  });
  await page.goto('/chat/blank');
  const password = (await readFile(process.env.SB_E2E_PASSWORD_FILE!, 'utf8')).trim();
  await page.getByLabel('SecondBrain 登录口令').fill(password);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page.getByRole('heading', { name: '空白验收' })).toBeVisible();
  await page.locator('.sidebar nav').getByRole('button', { name: '笔记', exact: true }).click();
  await expect(page).toHaveURL(/\/notes(?:\?.*)?$/);

  const richRefCreate = page.waitForResponse(response => response.request().method() === 'POST'
    && /\/api\/notes\/drafts\/[^/]+\/blocksuite\/resources$/.test(new URL(response.url()).pathname));
  const firstOpenStarted = await page.evaluate(() => Date.now());
  await page.getByRole('button', { name: '新建笔记', exact: true }).click();
  const resourceResponse = await richRefCreate;
  expect(resourceResponse.status()).toBe(200);
  const created = await resourceResponse.json() as { resource_id: string };
  const editor = page.locator('.blocksuite-resource-inline');
  await expect(editor).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('dialog', { name: '笔记编辑器' })).toHaveCount(0);
  await expect(editor).toHaveAttribute('aria-busy', 'false', { timeout: 30_000 });
  const openMetrics = await page.evaluate(() => (window as Window & { __wp5ReadyEvents?: Array<Record<string, unknown>> }).__wp5ReadyEvents ?? []);
  expect(openMetrics.length).toBeGreaterThan(0);
  const firstOpenSetup = openMetrics.at(-1);
  await expect(page.locator('.notes-properties')).toHaveCount(0);

  const paragraphs = editor.locator('.blocksuite-resource-host .affine-page-viewport affine-paragraph');
  await expect(paragraphs).toHaveCount(2);
  const body = paragraphs.nth(1);
  await body.click();
  const inline = body.locator('rich-text .inline-editor');
  await expect(inline).toHaveAttribute('contenteditable', 'true');
  await expect.poll(() => inline.evaluate(node => {
    const selection = window.getSelection();
    return Boolean(selection?.anchorNode && node.contains(selection.anchorNode));
  })).toBe(true);
  const firstOpen = await page.evaluate(start => ({ durationMs: Date.now() - start,
    viewport: `${window.innerWidth}x${window.innerHeight}` }), firstOpenStarted);
  await editor.getByRole('button', { name: '重命名文档' }).click();
  const titleInput = editor.getByRole('textbox', { name: '重命名文档' });
  await titleInput.fill('WP5 Native Probe');
  await titleInput.press('Enter');
  const titleBlock = editor.locator('.blocksuite-resource-host [data-sb-document-title-block="true"]');
  await expect(titleBlock).toBeHidden();
  await expect(editor.locator('.document-heading')).toContainText('WP5 Native Probe');
  await expect.poll(() => editor.locator('.blocksuite-resource-host').evaluate(host => {
    const store = (host as HTMLDivElement & { __sbBlockSuiteStore?: any }).__sbBlockSuiteStore;
    const title = store?.getBlocksByFlavour('affine:paragraph').find(({ model }: any) => model.props.type === 'h1')?.model;
    return title?.props.text?.toString?.() ?? '';
  })).toBe('WP5 Native Probe');
  await body.click();
  await expect.poll(() => inline.evaluate(node => {
    const selection = window.getSelection();
    return node.getAttribute('contenteditable') === 'true' && Boolean(selection?.anchorNode && node.contains(selection.anchorNode));
  })).toBe(true);
  await page.keyboard.insertText('First line after title');
  await page.keyboard.press('Enter');
  await page.keyboard.insertText('Second paragraph after Enter');

  const enter = await editor.locator('.blocksuite-resource-host').evaluate(host => {
    const store = (host as HTMLDivElement & { __sbBlockSuiteStore?: any }).__sbBlockSuiteStore;
    const blocks = (store?.getBlocksByFlavour('affine:paragraph') ?? []).map(({ model }: any, index: number) => ({
      id: model.id, parentId: store.getParent(model)?.id, index, text: model.props.text?.toString?.() ?? '', type: model.props.type,
    }));
    const selection = window.getSelection();
    const active = document.activeElement as HTMLElement | null;
    const composingTarget = selection?.anchorNode?.parentElement?.closest('[contenteditable="true"]');
    return { activeTag: active?.tagName ?? null, contenteditable: composingTarget?.getAttribute('contenteditable') ?? null,
      selectionInsideEditor: Boolean(selection?.anchorNode && composingTarget?.contains(selection.anchorNode)),
      anchorOffset: selection?.anchorOffset ?? null, blocks };
  });
  expect(enter.contenteditable).toBe('true');
  expect(enter.selectionInsideEditor).toBe(true);
  const firstEnteredBlock = enter.blocks.find(block => block.text.includes('First line after title'));
  const secondEnteredBlock = enter.blocks.find(block => block.text.includes('Second paragraph after Enter'));
  expect(firstEnteredBlock).toBeDefined();
  expect(secondEnteredBlock).toBeDefined();
  expect(firstEnteredBlock?.id).not.toBe(secondEnteredBlock?.id);
  expect(firstEnteredBlock?.parentId).toBe(secondEnteredBlock?.parentId);
  expect(firstEnteredBlock!.index).toBeLessThan(secondEnteredBlock!.index);
  expect(firstEnteredBlock?.text).toBe('First line after title');
  expect(secondEnteredBlock?.text).toContain('Second paragraph after Enter');

  const second = editor.locator('affine-paragraph').filter({ hasText: 'Second paragraph after Enter' }).last().locator('rich-text .inline-editor');
  await page.evaluate(() => {
    (window as Window & { __wp5CompositionEvents?: string[] }).__wp5CompositionEvents = [];
    for (const type of ['compositionstart', 'compositionupdate', 'compositionend']) {
      window.addEventListener(type, () => (window as Window & { __wp5CompositionEvents?: string[] })
        .__wp5CompositionEvents?.push(type), true);
    }
  });
  const ime = await page.context().newCDPSession(page);
  await ime.send('Input.imeSetComposition', { text: ' 中文输入法内容', selectionStart: 8, selectionEnd: 8 });
  await expect(second).toContainText('中文输入法内容');
  await ime.send('Input.insertText', { text: ' 中文输入法内容' });
  await ime.detach();
  await expect.poll(() => page.evaluate(() => (window as Window & { __wp5CompositionEvents?: string[] })
    .__wp5CompositionEvents ?? [])).toEqual(expect.arrayContaining(['compositionstart', 'compositionupdate', 'compositionend']));
  await expect(editor.locator('affine-paragraph').filter({ hasText: '中文输入法内容' })).toBeVisible();
  const backspaceText = ` backspace-${Date.now()}`;
  await page.keyboard.insertText(backspaceText);
  await page.keyboard.press('Backspace');
  await expect(editor.locator('affine-paragraph').filter({ hasText: backspaceText.slice(0, -1) })).toBeVisible();
  const undoText = ` undo-${Date.now()}`;
  await page.keyboard.insertText(undoText);
  await expect.poll(() => editor.locator('.blocksuite-resource-host').evaluate((host, marker) => {
    const store = (host as HTMLDivElement & { __sbBlockSuiteStore?: any }).__sbBlockSuiteStore;
    return (store?.getBlocksByFlavour('affine:paragraph') ?? []).some(({ model }: any) => model.props.text?.toString?.().includes(marker));
  }, undoText)).toBe(true);
  await page.keyboard.press('Control+z');
  await expect.poll(() => editor.locator('.blocksuite-resource-host').evaluate((host, marker) => {
    const store = (host as HTMLDivElement & { __sbBlockSuiteStore?: any }).__sbBlockSuiteStore;
    return (store?.getBlocksByFlavour('affine:paragraph') ?? []).some(({ model }: any) => model.props.text?.toString?.().includes(marker));
  }, undoText)).toBe(false);
  await expect(editor.locator('affine-paragraph').filter({ hasText: undoText })).toHaveCount(0);
  await page.keyboard.press('Control+Shift+z');
  await expect.poll(() => editor.locator('.blocksuite-resource-host').evaluate((host, marker) => {
    const store = (host as HTMLDivElement & { __sbBlockSuiteStore?: any }).__sbBlockSuiteStore;
    return (store?.getBlocksByFlavour('affine:paragraph') ?? []).some(({ model }: any) => model.props.text?.toString?.().includes(marker));
  }, undoText)).toBe(true);
  await expect(editor.locator('affine-paragraph').filter({ hasText: undoText })).toBeVisible();

  const firstBodyParagraph = editor.locator('affine-paragraph').filter({ hasText: 'First line after title' }).first();
  const firstBodyBlockId = await firstBodyParagraph.getAttribute('data-block-id');
  expect(firstBodyBlockId).toBeTruthy();
  const titleBodyParagraph = editor.locator(`affine-paragraph[data-block-id="${firstBodyBlockId}"]`);
  await titleBodyParagraph.click();
  await page.keyboard.press('Home');
  await expect.poll(() => titleBodyParagraph.locator('rich-text').evaluate(node => {
    const inlineEditor = (node as HTMLElement & { inlineEditor?: { getInlineRange: () => { index: number; length: number } | null } }).inlineEditor;
    return inlineEditor?.getInlineRange()?.index ?? null;
  })).toBe(0);
  await page.keyboard.press('Backspace');
  const titleBoundary = await editor.locator('.blocksuite-resource-host').evaluate(host => {
    const store = (host as HTMLDivElement & { __sbBlockSuiteStore?: any }).__sbBlockSuiteStore;
    const blocks = (store?.getBlocksByFlavour('affine:paragraph') ?? []).map(({ model }: any) => ({
      id: model.id, text: model.props.text?.toString?.() ?? '', type: model.props.type,
    }));
    const titleBlock = blocks.find(block => block.type === 'h1');
    return { title: titleBlock?.text ?? '', titleBlockId: titleBlock?.id ?? null,
      firstBody: blocks.find(block => block.text.includes('First line after title')) ?? null,
      blocks };
  });
  expect(titleBoundary.title).toBe('WP5 Native Probe');
  expect(titleBoundary.firstBody?.text).toBe('First line after title');
  expect(titleBoundary.firstBody?.id).not.toBe(titleBoundary.titleBlockId);

  const segmentedParagraph = editor.locator(`affine-paragraph[data-block-id="${firstBodyBlockId}"]`);
  const segmentedRichText = segmentedParagraph.locator('rich-text');
  await segmentedParagraph.locator('rich-text').evaluate(node => {
    const inlineEditor = (node as HTMLElement & { inlineEditor?: { formatText: (range: { index: number; length: number }, attributes: Record<string, unknown>) => void } }).inlineEditor;
    if (!inlineEditor) throw new Error('BlockSuite inline editor was unavailable');
    inlineEditor.formatText({ index: 0, length: 5 }, { bold: true });
  });
  await expect.poll(() => segmentedRichText.evaluate(node => {
    const inlineEditor = (node as HTMLElement & { inlineEditor?: { rootElement?: HTMLElement } }).inlineEditor;
    return [...(inlineEditor?.rootElement ?? node).querySelectorAll('[data-v-text="true"]')]
      .filter(element => [...element.childNodes].some(child => child instanceof Text)).length;
  })).toBeGreaterThanOrEqual(2);
  await segmentedRichText.evaluate(node => {
    const inlineEditor = (node as HTMLElement & { inlineEditor?: { rootElement?: HTMLElement } }).inlineEditor;
    if (!inlineEditor) throw new Error('BlockSuite inline editor was unavailable');
    const textNodes = [...(inlineEditor.rootElement ?? node).querySelectorAll('[data-v-text="true"]')]
      .map(element => [...element.childNodes].find(child => child instanceof Text))
      .filter((child): child is Text => child instanceof Text);
    if (textNodes.length < 2) throw new Error('Formatted paragraph did not expose separate text nodes');
    const selection = window.getSelection();
    if (!selection) throw new Error('Browser selection was unavailable');
    const range = document.createRange();
    range.setStart(textNodes[1]!, 0);
    range.collapse(true);
    selection.removeAllRanges();
    selection.addRange(range);
  });
  await expect.poll(() => segmentedRichText.evaluate(node => {
    const inlineEditor = (node as HTMLElement & { inlineEditor?: { getInlineRange: () => { index: number; length: number } | null } }).inlineEditor;
    const range = inlineEditor?.getInlineRange() ?? null;
    return { range, domOffset: window.getSelection()?.anchorOffset ?? null };
  })).toEqual({ range: { index: 5, length: 0 }, domOffset: 0 });
  await page.keyboard.press('Backspace');
  await expect(segmentedParagraph).toContainText('Firs line after title');
  await page.keyboard.press('Control+z');
  await expect(segmentedParagraph).toContainText('First line after title');

  const resourceSave = page.waitForResponse(response => response.request().method() === 'PUT'
    && new URL(response.url()).pathname.endsWith(`/blocksuite/resources/${created.resource_id}`));
  const markdownSave = page.waitForResponse(response => response.request().method() === 'PUT'
    && /\/api\/notes\/drafts\/[^/]+$/.test(new URL(response.url()).pathname));
  await editor.getByRole('button', { name: '保存笔记', exact: true }).click();
  expect((await resourceSave).status()).toBe(200);
  expect((await markdownSave).status()).toBe(200);
  await expect(editor.getByRole('status').first()).toContainText('已保存');
  const firstPath = await page.locator('.notes-sidebar li button').filter({ hasText: 'WP5 Native Probe' }).last().textContent();
  expect(firstPath).toContain('WP5 Native Probe');

  const noteRow = page.locator('.notes-sidebar li.notes-item-row').filter({ hasText: 'WP5 Native Probe' }).last();
  await noteRow.locator('.notes-item-more > summary').click();
  await noteRow.getByRole('button', { name: '编辑类型与标签' }).click();
  await expect(editor).toHaveCount(0);
  await expect(page.getByRole('region', { name: '笔记属性编辑' })).toBeVisible();
  await expect(page.locator('.notes-properties')).toBeVisible();
  await page.getByRole('button', { name: '返回笔记列表' }).click();
  await noteRow.locator('.notes-item-open').click();
  await expect(editor).toBeVisible();

  await editor.getByRole('button', { name: '返回笔记列表' }).click();
  await expect(editor).toHaveCount(0);
  await page.getByRole('button', { name: '新建笔记', exact: true }).click();
  const secondEditor = page.locator('.blocksuite-resource-inline');
  await expect(secondEditor).toBeVisible({ timeout: 30_000 });
  await secondEditor.getByRole('button', { name: '返回笔记列表' }).click();
  const warmOpenStarted = await page.evaluate(() => Date.now());
  await page.locator('.notes-sidebar li button').filter({ hasText: 'WP5 Native Probe' }).last().click();
  await expect(editor).toBeVisible({ timeout: 30_000 });
  await expect(editor.getByText('Second paragraph after Enter', { exact: false })).toBeVisible();
  const reopenedFirstLine = editor.locator('affine-paragraph').filter({ hasText: 'First line after title' }).last().locator('rich-text .inline-editor');
  await reopenedFirstLine.click();
  await expect.poll(() => reopenedFirstLine.evaluate(node => {
    const selection = window.getSelection();
    return node.getAttribute('contenteditable') === 'true' && Boolean(selection?.anchorNode && node.contains(selection.anchorNode));
  })).toBe(true);
  const warmOpen = await page.evaluate(start => ({ durationMs: Date.now() - start,
    viewport: `${window.innerWidth}x${window.innerHeight}` }), warmOpenStarted);
  const refreshStarted = await page.evaluate(() => Date.now());
  await page.reload();
  await expect(editor).toBeVisible({ timeout: 30_000 });
  await expect(editor).toHaveAttribute('aria-busy', 'false', { timeout: 30_000 });
  const refreshLineEditor = editor.locator('affine-paragraph').filter({ hasText: 'First line after title' }).last().locator('rich-text .inline-editor');
  await refreshLineEditor.click();
  await expect.poll(() => refreshLineEditor.evaluate(node => {
    const selection = window.getSelection();
    return node.getAttribute('contenteditable') === 'true' && Boolean(selection?.anchorNode && node.contains(selection.anchorNode));
  })).toBe(true);
  const refreshOpen = await page.evaluate(start => ({ durationMs: Date.now() - start,
    viewport: `${window.innerWidth}x${window.innerHeight}` }), refreshStarted);

  // Remove temporary interaction markers before capturing a user-facing
  // screenshot, then verify the cleaned synthetic paragraph survives a save
  // and reload through the normal editor path.
  const cleanParagraphBlock = editor.locator('affine-paragraph')
    .filter({ hasText: 'Second paragraph after Enter' }).last();
  const cleanParagraphBlockId = await cleanParagraphBlock.getAttribute('data-block-id');
  expect(cleanParagraphBlockId).toBeTruthy();
  const cleanParagraph = cleanParagraphBlock.locator('rich-text .inline-editor');
  await cleanParagraph.click();
  await expect.poll(() => cleanParagraph.evaluate(node => {
    const selection = window.getSelection();
    return node.getAttribute('contenteditable') === 'true'
      && Boolean(selection?.anchorNode && node.contains(selection.anchorNode));
  })).toBe(true);
  await page.keyboard.press('Home');
  await page.keyboard.press('Shift+End');
  const fullParagraphText = await editor.locator('.blocksuite-resource-host').evaluate((host, blockId) => {
    const store = (host as HTMLDivElement & { __sbBlockSuiteStore?: any }).__sbBlockSuiteStore;
    return store?.getBlock(blockId)?.model.props.text?.toString?.() ?? '';
  }, cleanParagraphBlockId);
  await expect.poll(() => page.evaluate(() => window.getSelection()?.toString() ?? '')).toBe(fullParagraphText);
  await page.keyboard.insertText('Second paragraph after Enter 中文输入法内容');
  await expect.poll(() => editor.locator('.blocksuite-resource-host').evaluate((host, blockId) => {
    const store = (host as HTMLDivElement & { __sbBlockSuiteStore?: any }).__sbBlockSuiteStore;
    return store?.getBlock(blockId)?.model.props.text?.toString?.() ?? '';
  }, cleanParagraphBlockId)).toBe('Second paragraph after Enter 中文输入法内容');
  await editor.getByRole('button', { name: '保存笔记', exact: true }).click();
  await expect(editor.getByRole('status').first()).toContainText('已保存');
  await page.reload();
  await expect(editor).toBeVisible();
  await expect(editor.getByText('Second paragraph after Enter 中文输入法内容', { exact: true })).toBeVisible();

  const target = editor.locator('affine-paragraph').filter({ hasText: 'First line after title' }).last();
  const plus = editor.locator('sb-desktop-page-plus-widget button[data-kind="plus"]');
  const grip = editor.locator('sb-desktop-page-plus-widget button[data-kind="grip"]');
  await target.hover();
  await expect(plus).toHaveAttribute('data-visible', 'true');
  await expect(grip).toHaveAttribute('data-visible', 'true');
  const blockControls = await Promise.all([grip, plus].map(locator => locator.evaluate(button => {
    const rect = button.getBoundingClientRect(); const style = getComputedStyle(button);
    return { kind: button.getAttribute('data-kind'), visible: button.dataset.visible === 'true'
      && rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden',
      x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) };
  })));
  expect(Math.abs(blockControls[0]!.y - blockControls[1]!.y)).toBeLessThan(2);
  expect(Math.abs(blockControls[0]!.x - blockControls[1]!.x)).toBeGreaterThanOrEqual(22);
  expect(Math.abs(blockControls[0]!.x - blockControls[1]!.x)).toBeLessThanOrEqual(26);
  const secondTarget = editor.locator('affine-paragraph').filter({ hasText: 'Second paragraph after Enter' }).last();
  const dragOrder = async () => {
    const [firstBox, secondBox] = await Promise.all([target.boundingBox(), secondTarget.boundingBox()]);
    if (!firstBox || !secondBox) throw new Error('BlockSuite drag targets were not visible');
    return { firstY: firstBox.y, secondY: secondBox.y };
  };
  const dragGripTo = async (dropBefore: boolean) => {
    await target.hover();
    await expect(grip).toHaveAttribute('data-visible', 'true');
    const [gripBox, targetBox] = await Promise.all([grip.boundingBox(), secondTarget.boundingBox()]);
    if (!gripBox || !targetBox) throw new Error('BlockSuite drag geometry was unavailable');
    await page.mouse.move(gripBox.x + gripBox.width / 2, gripBox.y + gripBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(targetBox.x + targetBox.width / 3,
      dropBefore ? targetBox.y + 1 : targetBox.y + targetBox.height - 1, { steps: 8 });
    await page.mouse.up();
  };
  await dragGripTo(false);
  await expect.poll(async () => {
    const order = await dragOrder();
    return order.firstY > order.secondY;
  }).toBe(true);
  await dragGripTo(true);
  await expect.poll(async () => {
    const order = await dragOrder();
    return order.firstY < order.secondY;
  }).toBe(true);
  const dragResourceSave = page.waitForResponse(response => response.request().method() === 'PUT'
    && new URL(response.url()).pathname.endsWith(`/blocksuite/resources/${created.resource_id}`));
  const dragMarkdownSave = page.waitForResponse(response => response.request().method() === 'PUT'
    && /\/api\/notes\/drafts\/[^/]+$/.test(new URL(response.url()).pathname));
  await editor.getByRole('button', { name: '保存笔记', exact: true }).click();
  expect((await dragResourceSave).status()).toBe(200);
  expect((await dragMarkdownSave).status()).toBe(200);
  await expect(editor.getByRole('status').first()).toContainText('已保存');
  await page.reload();
  await expect(editor).toBeVisible();
  await expect.poll(async () => {
    const order = await dragOrder();
    return order.firstY < order.secondY;
  }).toBe(true);
  await page.locator('.notes-layout').screenshot({ path: process.env.SB_WP5_NATIVE_SCREENSHOT_PATH! });
  await target.hover();
  await expect(plus).toHaveAttribute('data-visible', 'true');
  await plus.click();
  const headingMenuItem = page.getByTestId('一级标题');
  await expect(headingMenuItem).toBeVisible();
  await headingMenuItem.click();
  await expect.poll(() => editor.locator('.blocksuite-resource-host').evaluate(host => {
    const store = (host as HTMLDivElement & { __sbBlockSuiteStore?: any }).__sbBlockSuiteStore;
    return store?.getBlocksByFlavour('affine:paragraph').find(({ model }: any) => model.props.text?.toString?.().includes('First line after title'))?.model.props.type;
  })).toBe('h1');
  await titleBodyParagraph.click();
  await page.keyboard.press('Home');
  await expect.poll(() => titleBodyParagraph.locator('rich-text').evaluate(node => {
    const inlineEditor = (node as HTMLElement & { inlineEditor?: { getInlineRange: () => { index: number; length: number } | null } }).inlineEditor;
    return inlineEditor?.getInlineRange()?.index ?? null;
  })).toBe(0);
  await page.keyboard.press('Backspace');
  await expect.poll(() => editor.locator('.blocksuite-resource-host').evaluate((host, titleBlockId) => {
    const store = (host as HTMLDivElement & { __sbBlockSuiteStore?: any }).__sbBlockSuiteStore;
    const blocks = store?.getBlocksByFlavour('affine:paragraph') ?? [];
    return { bodyType: blocks.find(({ model }: any) => model.props.text?.toString?.().includes('First line after title'))?.model.props.type,
      titleText: blocks.find(({ model }: any) => model.id === titleBlockId)?.model.props.text?.toString?.() ?? null };
  }, titleBoundary.titleBlockId)).toEqual({ bodyType: 'text', titleText: 'WP5 Native Probe' });

  const titleAndBody = await page.locator('.notes-document-rich-page').evaluate(root => {
    const visible = (node: Element) => { const rect = node.getBoundingClientRect(); return rect.width > 0 && rect.height > 0 && getComputedStyle(node).display !== 'none'; };
    const visibleTitleHeadings = [...root.querySelectorAll('.document-heading')].filter(visible).map(node => node.textContent?.trim() ?? '');
    const hiddenTitle = root.querySelector('[data-sb-document-title-block="true"]');
    const host = root.querySelector<HTMLElement>('.blocksuite-resource-host') as (HTMLElement & { __sbBlockSuiteStore?: any }) | null;
    const blocks = (host?.__sbBlockSuiteStore?.getBlocksByFlavour('affine:paragraph') ?? []).map(({ model }: any) => ({
      text: model.props.text?.toString?.() ?? '', type: model.props.type,
    }));
    return { visibleTitleHeadings, hiddenTitleDisplay: hiddenTitle ? getComputedStyle(hiddenTitle).display : null,
      blocks, inlineEditor: Boolean(root.querySelector('.blocksuite-resource-dialog.blocksuite-resource-inline')),
      modalEditorCount: document.querySelectorAll('.blocksuite-resource-backdrop').length };
  });
  const evidence: Record<string, unknown> = { viewport: '1440x1000', enter, titleBoundary, firstOpen, warmOpen, refreshOpen,
    firstOpenSetup, titleAndBody, blockControls,
    journey: ['new note', 'title', 'first line', 'Enter', 'multi paragraph', 'Chromium IME composition', 'Backspace',
      'undo/redo', 'save', 'switch note', 'reopen', 'reload', 'six-dot hover and drag reorder', 'save and reload reorder', 'plus insert'] };
  expect(titleAndBody.visibleTitleHeadings).toHaveLength(1);
  expect(titleAndBody.hiddenTitleDisplay).toBe('none');
  expect(titleAndBody.modalEditorCount).toBe(0);

  await page.setViewportSize({ width: 390, height: 844 });
  await target.hover();
  await expect(plus).toHaveAttribute('data-visible', 'true');
  await expect(grip).toHaveAttribute('data-visible', 'true');
  const mobileBlockControls = await Promise.all([grip, plus].map(locator => locator.evaluate(element => {
    const rect = element.getBoundingClientRect(); const style = getComputedStyle(element);
    return { kind: element.getAttribute('data-kind'), visible: element.getAttribute('data-visible') === 'true'
      && rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden',
      x: rect.x, y: rect.y, width: rect.width, height: rect.height,
      withinViewport: rect.left >= 0 && rect.right <= window.innerWidth + 1 };
  })));
  const mobileLayout = await page.locator('.notes-layout').evaluate((root, blockControls) => {
    const rectWithinViewport = (element: Element | null) => {
      if (!element) return false;
      const rect = element.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0 && rect.left >= 0 && rect.right <= window.innerWidth + 1;
    };
    const controls = [...root.querySelectorAll('.document-controls button, .blocksuite-resource-toolbar > button, .blocksuite-more-tools > summary')];
    return { viewportWidth: window.innerWidth, documentWidth: document.documentElement.scrollWidth,
      notesWidth: (root as HTMLElement).scrollWidth,
      controlsVisible: controls.map(button => ({ label: button.getAttribute('aria-label') ?? button.textContent?.trim() ?? '',
        visibleAndWithinViewport: rectWithinViewport(button) })),
      plusVisible: blockControls[1]?.visible && blockControls[1]?.withinViewport,
      gripVisible: blockControls[0]?.visible && blockControls[0]?.withinViewport,
      plusControl: blockControls[1] ?? null, gripControl: blockControls[0] ?? null };
  }, mobileBlockControls);
  await writeFile(process.env.SB_WP5_NATIVE_MOBILE_DIAGNOSTIC_PATH!, JSON.stringify(mobileLayout, null, 2));
  expect(mobileLayout.documentWidth).toBeLessThanOrEqual(390);
  expect(mobileLayout.notesWidth).toBeLessThanOrEqual(390);
  expect(mobileLayout.controlsVisible.length).toBeGreaterThan(0);
  expect(mobileLayout.controlsVisible.every(item => item.visibleAndWithinViewport)).toBe(true);
  expect(mobileLayout.plusVisible).toBe(true);
  expect(mobileLayout.gripVisible).toBe(true);
  const mobilePlus = mobileLayout.plusControl!;
  const mobileGrip = mobileLayout.gripControl!;
  expect(mobileGrip.x).toBeGreaterThanOrEqual(10);
  expect(mobilePlus.x).toBeGreaterThanOrEqual(10);
  const gripDots = await grip.evaluate(button => [...button.querySelectorAll('.grip-dots i')].map(dot => {
    const rect = dot.getBoundingClientRect();
    return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
  }));
  expect(gripDots).toHaveLength(6);
  expect(gripDots.every(dot => dot.left >= 0 && dot.right <= 390 && dot.top >= 0 && dot.bottom <= 844)).toBe(true);
  expect(mobilePlus.x < mobileGrip.x + mobileGrip.width && mobileGrip.x < mobilePlus.x + mobilePlus.width
    && mobilePlus.y < mobileGrip.y + mobileGrip.height && mobileGrip.y < mobilePlus.y + mobilePlus.height).toBe(false);
  await page.locator('.notes-layout').screenshot({ path: process.env.SB_WP5_NATIVE_MOBILE_SCREENSHOT_PATH! });
  evidence.mobileLayout = mobileLayout;
  await writeFile(process.env.SB_WP5_NATIVE_DOM_EVIDENCE_PATH!, JSON.stringify(evidence, null, 2));
});

test('WP5 independent nested canvas open minimal reproduction', async ({ page }) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/chat/blank');
  const password = (await readFile(process.env.SB_E2E_PASSWORD_FILE!, 'utf8')).trim();
  await page.getByLabel('SecondBrain 登录口令').fill(password);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page.getByRole('heading', { name: '空白验收' })).toBeVisible();
  await page.locator('.sidebar nav').getByRole('button', { name: '笔记', exact: true }).click();
  await expect(page).toHaveURL(/\/notes(?:\?.*)?$/);

  const createRichPage = page.waitForResponse(response => response.request().method() === 'POST'
    && /\/api\/notes\/drafts\/[^/]+\/blocksuite\/resources$/.test(new URL(response.url()).pathname));
  await page.getByRole('button', { name: '新建笔记', exact: true }).click();
  const richPageCreated = await createRichPage;
  expect(richPageCreated.status()).toBe(200);
  const richPage = await richPageCreated.json() as { resource_id: string };
  const editor = page.locator('.blocksuite-resource-inline');
  await expect(editor).toBeVisible();
  await expect(editor).toHaveAttribute('aria-busy', 'false', { timeout: 30_000 });

  const longBody = editor.locator('.blocksuite-resource-host affine-paragraph').nth(1);
  await longBody.click();
  await page.keyboard.press('End');
  for (let index = 0; index < 12; index += 1) {
    if (index > 0) await page.keyboard.press('Enter');
    await page.keyboard.insertText(`Synthetic canvas layout paragraph ${index + 1}`);
  }
  await expect(editor.locator('.blocksuite-resource-host affine-paragraph')).toHaveCount(13);
  const saveRichResource = page.waitForResponse(response => response.request().method() === 'PUT'
    && new URL(response.url()).pathname.endsWith(`/blocksuite/resources/${richPage.resource_id}`));
  const saveRichMarkdown = page.waitForResponse(response => response.request().method() === 'PUT'
    && /\/api\/notes\/drafts\/[^/]+$/.test(new URL(response.url()).pathname));
  await editor.getByRole('button', { name: '保存笔记', exact: true }).click();
  expect((await saveRichResource).status()).toBe(200);
  expect((await saveRichMarkdown).status()).toBe(200);

  await editor.locator('.blocksuite-canvas-tools > summary').click();
  const createCanvas = page.waitForResponse(response => response.request().method() === 'POST'
    && /\/api\/notes\/drafts\/[^/]+\/blocksuite\/resources$/.test(new URL(response.url()).pathname));
  await editor.getByRole('button', { name: '新建独立画布', exact: true }).click();
  const canvasCreated = await createCanvas;
  expect(canvasCreated.status()).toBe(200);
  const canvas = await canvasCreated.json() as { resource_id: string };
  const card = editor.locator('.canvas-b-card').filter({ hasText: canvas.resource_id });
  await expect(card).toBeVisible();
  const canvasLayout = await page.evaluate(() => {
    const inline = document.querySelector<HTMLElement>('.blocksuite-resource-inline');
    const host = inline?.querySelector<HTMLElement>('.blocksuite-resource-host') ?? null;
    const viewport = host?.querySelector<HTMLElement>('.sb-archive-viewport');
    const gallery = inline?.querySelector<HTMLElement>('.blocksuite-canvas-tools') ?? null;
    const paragraphs = [...(host?.querySelectorAll<HTMLElement>('affine-paragraph') ?? [])];
    const hostBottom = host?.getBoundingClientRect().bottom ?? 0;
    const galleryTop = gallery?.getBoundingClientRect().top ?? 0;
    const lastParagraphBottom = paragraphs.at(-1)?.getBoundingClientRect().bottom ?? 0;
    const hostHeight = host?.getBoundingClientRect().height ?? 0;
    const lastParagraphHeight = paragraphs.at(-1)?.getBoundingClientRect().height ?? 0;
    const box = (element: HTMLElement | null) => element ? {
      height: element.getBoundingClientRect().height, scrollHeight: element.scrollHeight,
      cssHeight: getComputedStyle(element).height, minHeight: getComputedStyle(element).minHeight,
      display: getComputedStyle(element).display, flex: getComputedStyle(element).flex,
    } : null;
    return { paragraphCount: paragraphs.length, hostCount: document.querySelectorAll('.blocksuite-resource-host').length,
      inlineHostCount: inline?.querySelectorAll('.blocksuite-resource-host').length ?? 0,
      hostHeight, hostScrollHeight: host?.scrollHeight ?? 0, lastParagraphHeight,
      hostStyle: box(host), viewportStyle: box(viewport),
      editorHostStyle: box(host?.querySelector<HTMLElement>('editor-host') ?? null),
      pageRootStyle: box(host?.querySelector<HTMLElement>('affine-page-root') ?? null),
      paragraphStyles: paragraphs.slice(1, 3).concat(paragraphs.slice(-1)).map(box),
      hostBottom, galleryTop, lastParagraphBottom,
      noOverlap: Boolean(viewport && gallery && paragraphs.length >= 12 && galleryTop >= hostBottom - 1
        && galleryTop >= lastParagraphBottom - 1) };
  });
  console.log(`WP5_NATIVE_CANVAS_LAYOUT ${JSON.stringify(canvasLayout)}`);
  expect(canvasLayout.paragraphCount).toBe(13);
  expect(canvasLayout.inlineHostCount).toBe(1);
  expect(canvasLayout.noOverlap, `canvas gallery must follow the full document body: ${JSON.stringify(canvasLayout)}`).toBe(true);
  const canvasRead = page.waitForResponse(response => response.request().method() === 'GET'
    && new URL(response.url()).pathname.endsWith(`/blocksuite/resources/${canvas.resource_id}`), { timeout: 15_000 });
  const openButton = card.getByRole('button', { name: '打开编辑', exact: true });
  await openButton.scrollIntoViewIfNeeded();
  await expect(openButton).toBeVisible();
  const openButtonBox = await openButton.boundingBox();
  expect(openButtonBox).not.toBeNull();
  const receivesPointer = await openButton.evaluate(button => {
    const rect = button.getBoundingClientRect();
    const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
    return hit === button || (hit instanceof Node && button.contains(hit));
  });
  expect(receivesPointer).toBe(true);
  await page.mouse.click(openButtonBox!.x + openButtonBox!.width / 2, openButtonBox!.y + openButtonBox!.height / 2);
  const readResponse = await canvasRead;
  expect(readResponse.status()).toBe(200);
  const dialog = page.getByRole('dialog', { name: 'BlockSuite Edgeless 资源' });
  await expect(dialog).toBeVisible({ timeout: 15_000 });
  await expect(dialog).toHaveAttribute('aria-busy', 'false', { timeout: 30_000 });
  const canvasUi = await page.evaluate(() => ({
    dialogVisible: Boolean(document.querySelector('[role="dialog"][aria-label="BlockSuite Edgeless 资源"]')?.getClientRects().length),
    nestedEditorVisible: Boolean(document.querySelector('.blocksuite-resource-backdrop [data-kind="edgeless-canvas"]')?.getClientRects().length),
  }));
  const evidence = { result: 'PASS', scope: 'independent synthetic canvas-open repro',
    resourceReadStatus: readResponse.status(), canvasLayout: {
      paragraphCount: canvasLayout.paragraphCount, hostBottom: canvasLayout.hostBottom,
      galleryTop: canvasLayout.galleryTop, lastParagraphBottom: canvasLayout.lastParagraphBottom,
      noOverlap: canvasLayout.noOverlap,
    }, ...canvasUi };
  await writeFile(process.env.SB_WP5_NATIVE_CANVAS_OPEN_EVIDENCE_PATH!, JSON.stringify(evidence, null, 2));
  await page.screenshot({ path: process.env.SB_WP5_NATIVE_CANVAS_OPEN_SCREENSHOT_PATH!, fullPage: false });
});
