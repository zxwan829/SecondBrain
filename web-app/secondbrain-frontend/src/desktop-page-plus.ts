import { getInlineEditorByModel } from '@blocksuite/affine-rich-text';
import { SlashMenuExtension } from '@blocksuite/affine-widget-slash-menu';
import { WidgetComponent, WidgetViewExtension } from '@blocksuite/std';
import { BLOCK_ID_ATTR } from '@blocksuite/std';
import { css, html } from 'lit';
import { literal, unsafeStatic } from 'lit/static-html.js';

// These two imports intentionally reuse the 0.22.4 native Slash menu renderer
// and item builder. The package root does not export either symbol.
import { SlashMenu, buildSlashMenuItems } from './archive-slash-renderer.js';
import { localizeSlashMenuItem } from './slash-locale.js';

const WIDGET_TAG = 'sb-desktop-page-plus-widget';
const WIDGET_ID = 'sb-desktop-page-plus';

class DesktopPagePlusWidget extends WidgetComponent {
  static override styles = css`
    :host { position: fixed; inset: 0 auto auto 0; z-index: 50; pointer-events: none; }
    button {
      position: fixed; display: none; pointer-events: auto; width: 22px; height: 22px;
      padding: 0; border: 0; border-radius: 6px; color: #60646c; background: transparent;
      cursor: pointer;
    }
    button[data-kind="plus"] { align-items:center;justify-content:center; }
    button[data-kind="plus"] svg { width:20px;height:20px;display:block; }
    button[data-kind="grip"] { align-items:center;justify-content:center; }
    .grip-dots { display:grid;grid-template-columns:repeat(2,4px);grid-template-rows:repeat(3,4px);gap:2px; }
    .grip-dots i { width:4px;height:4px;border-radius:50%;background:currentColor; }
    button[data-visible="true"] { display: flex; }
    button:hover, button:focus-visible { color: #272a31; background: #eceef2; outline: none; }
    button[data-dragging="true"] { color: #2457c5; background: #e5edff; }
  `;

  private anchor: { id: string; element: HTMLElement } | null = null;
  private dragSource: { id: string; element: HTMLElement } | null = null;
  private dropTarget: { id: string; element: HTMLElement; before: boolean; previousBoxShadow: string } | null = null;
  private hideTimer: ReturnType<typeof setTimeout> | null = null;
  private lastPointerActivation = 0;
  private menuOpen = false;

  private get plusButton() {
    return this.renderRoot.querySelector<HTMLButtonElement>('button[data-kind="plus"]');
  }

  private get gripButton() {
    return this.renderRoot.querySelector<HTMLButtonElement>('button[data-kind="grip"]');
  }

  private readonly onPointerMove = (event: PointerEvent) => {
    if (this.dragSource) {
      this.updateDropTarget(event);
      return;
    }
    if (this.menuOpen) {
      this.cancelHide();
      return;
    }
    const button = this.plusButton;
    const target = event.composedPath().find(
      (node): node is Element => node instanceof Element && node.hasAttribute(BLOCK_ID_ATTR)
    );
    const grip = this.gripButton;
    if (button && (this.isOverControl(event) || event.composedPath().includes(button) || (grip && event.composedPath().includes(grip)) || event.composedPath().includes(this))) {
      this.cancelHide();
      return;
    }

    const blockElement = target?.closest<HTMLElement>(`[${BLOCK_ID_ATTR}]`);
    const id = blockElement?.getAttribute(BLOCK_ID_ATTR);
    const model = id ? this.store.getBlock(id)?.model : null;
    if (!blockElement || !model || model.flavour === 'affine:page' || !getInlineEditorByModel(this.std, model)) {
      this.scheduleHide();
      return;
    }

    this.cancelHide();
    this.anchor = { id: model.id, element: blockElement };
    this.positionButton();
  };

  private readonly onScroll = () => this.positionButton();

  private readonly onButtonPointerEnter = () => this.cancelHide();

  private readonly onButtonPointerLeave = () => {
    if (!this.dragSource) this.scheduleHide();
  };

  private readonly onButtonPointerDown = (event: PointerEvent) => {
    event.preventDefault();
    event.stopPropagation();
    this.lastPointerActivation = performance.now();
    this.openSlashMenu();
  };

  private readonly onPointerCancel = () => {
    this.clearDropTarget();
    this.dragSource = null;
    if (this.gripButton) delete this.gripButton.dataset.dragging;
    this.scheduleHide();
  };

  private readonly onGripPointerDown = (event: PointerEvent) => {
    const anchor = this.anchor;
    if (!anchor || event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    this.cancelHide();
    this.dragSource = anchor;
    this.gripButton?.setPointerCapture(event.pointerId);
    if (this.gripButton) this.gripButton.dataset.dragging = 'true';
    this.updateDropTarget(event);
  };

  private readonly onPointerUp = (event: PointerEvent) => {
    const source = this.dragSource;
    const target = this.dropTarget;
    if (!source) return;
    this.clearDropTarget();
    this.dragSource = null;
    if (this.gripButton) delete this.gripButton.dataset.dragging;
    if (!source || !target || source.id === target.id) {
      if (!this.isOverControl(event)) this.scheduleHide();
      return;
    }
    const sourceModel = this.store.getBlock(source.id)?.model;
    const targetModel = this.store.getBlock(target.id)?.model;
    if (!sourceModel || !targetModel) { if (!this.isOverControl(event)) this.scheduleHide(); return; }
    const sourceParent = this.store.getParent(sourceModel);
    const targetParent = this.store.getParent(targetModel);
    if (!sourceParent || sourceParent.id !== targetParent?.id) { if (!this.isOverControl(event)) this.scheduleHide(); return; }
    this.store.moveBlocks([sourceModel], sourceParent, targetModel, target.before);
    this.anchor = { id: source.id, element: source.element };
    this.positionButton();
    if (!this.isOverControl(event)) this.scheduleHide();
  };

  private isOverControl(event: PointerEvent) {
    // Pointer capture keeps composedPath on the grip after a drop elsewhere.
    // Coordinates also preserve the continuous gap between the two buttons.
    const buttons = [this.plusButton, this.gripButton].filter((button): button is HTMLButtonElement => !!button && button.dataset.visible === 'true');
    if (buttons.length !== 2) return false;
    const rects = buttons.map(button => button.getBoundingClientRect());
    return event.clientX >= Math.min(...rects.map(rect => rect.left)) &&
      event.clientX <= Math.max(...rects.map(rect => rect.right)) &&
      event.clientY >= Math.min(...rects.map(rect => rect.top)) &&
      event.clientY <= Math.max(...rects.map(rect => rect.bottom));
  }

  private readonly onButtonClick = (event: MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    // Pointer activation already opened the menu on pointerdown. Keep click
    // for keyboard activation, where detail is zero and no pointerdown occurs.
    if (event.detail > 0 && performance.now() - this.lastPointerActivation < 1000) return;
    this.openSlashMenu();
  };

  private openSlashMenu() {
    const anchor = this.anchor;
    const model = anchor && this.store.getBlock(anchor.id)?.model;
    if (!model) return;

    const inlineEditor = getInlineEditorByModel(this.std, model);
    if (!inlineEditor) return;
    const range = inlineEditor.getInlineRange();
    // A collapsed range makes the native menu show its complete command list,
    // even when a text selection existed before clicking the row control.
    const menuRange = {
      index: range?.index ?? inlineEditor.yTextLength,
      length: 0,
    };
    inlineEditor.setInlineRange(menuRange);
    // SlashMenu positions itself from window.getSelection(). The range
    // provider can skip syncing when this logical range equals its cached
    // value (for example after pointer focus left the editor), leaving the
    // native Range empty and causing the menu to abort during first render.
    inlineEditor.syncInlineRange(menuRange);

    const context = { std: this.std, model };
    const config = this.std.get(SlashMenuExtension).config;
    if (config.disableWhen?.(context)) return;
    const items = typeof config.items === 'function' ? config.items(context) : config.items;
    const controller = new AbortController();
    const menu = new SlashMenu(inlineEditor, controller);
    // The resource editor is rendered in a modal stacking context above the
    // theme's default popover layer. SlashMenu portals itself to document.body,
    // so inherit a layer just above this editor's backdrop when present.
    let resourceBackdrop: HTMLElement | null = null;
    let currentRoot: Node | null = anchor.element;
    while (currentRoot) {
      if (currentRoot instanceof HTMLElement && currentRoot.matches('.blocksuite-resource-backdrop')) {
        resourceBackdrop = currentRoot;
        break;
      }
      currentRoot = currentRoot.parentNode ?? (currentRoot instanceof ShadowRoot ? currentRoot.host : null);
    }
    if (resourceBackdrop) {
      const backdropZIndex = Number.parseInt(getComputedStyle(resourceBackdrop).zIndex, 10);
      if (Number.isFinite(backdropZIndex)) {
        menu.style.setProperty('--affine-z-index-popover', String(backdropZIndex + 1));
      }
    }
    this.menuOpen = true;
    this.cancelHide();
    menu.context = context;
    menu.items = buildSlashMenuItems(items, context, localizeSlashMenuItem);
    controller.signal.addEventListener('abort', () => {
      menu.remove();
      this.menuOpen = false;
      this.scheduleHide();
    }, { once: true });
    document.body.append(menu);
  };

  override connectedCallback() {
    super.connectedCallback();
    document.addEventListener('pointermove', this.onPointerMove, true);
    document.addEventListener('pointerup', this.onPointerUp, true);
    document.addEventListener('pointercancel', this.onPointerCancel, true);
    document.addEventListener('scroll', this.onScroll, true);
    window.addEventListener('resize', this.onScroll);
  }

  override disconnectedCallback() {
    document.removeEventListener('pointermove', this.onPointerMove, true);
    document.removeEventListener('pointerup', this.onPointerUp, true);
    document.removeEventListener('pointercancel', this.onPointerCancel, true);
    document.removeEventListener('scroll', this.onScroll, true);
    window.removeEventListener('resize', this.onScroll);
    this.cancelHide();
    super.disconnectedCallback();
  }

  override firstUpdated() {
    const plus = this.plusButton;
    const grip = this.gripButton;
    for (const button of [plus, grip]) {
      button?.addEventListener('pointerenter', this.onButtonPointerEnter);
      button?.addEventListener('pointerleave', this.onButtonPointerLeave);
    }
    plus?.addEventListener('pointerdown', this.onButtonPointerDown);
    plus?.addEventListener('click', this.onButtonClick);
    grip?.addEventListener('pointerdown', this.onGripPointerDown);
  }

  override render() {
    return html`
      <button type="button" data-kind="grip" aria-label="拖动块重新排序" title="拖动以重新排序" data-visible="false"><span class="grip-dots" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i></span></button>
      <button type="button" data-kind="plus" aria-label="插入块" title="插入块" data-visible="false"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2v16M2 10h16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button>
    `;
  }

  private positionButton() {
    const plus = this.plusButton;
    const grip = this.gripButton;
    const anchor = this.anchor;
    if (!plus || !grip || !anchor || !anchor.element.isConnected) return this.hide();
    const rect = anchor.element.getBoundingClientRect();
    const line = this.firstVisualLineRect(anchor.element);
    const left = Math.min(rect.left, line?.left ?? rect.left);
    // Keep the visual centers on the paragraph's first text line while the
    // glyphs remain 16–18px, matching the text baseline without covering it.
    // Headings with children expose a 32px collapse toggle at text-left - 32px.
    // Keep an 8px gap to that control while preserving the 2px gap between grip and plus.
    const lineTop = Math.max(4, (line?.top ?? rect.top) + ((line?.height ?? 22) - 22) / 2);
    const plusLeft = left - 62;
    const gripLeft = left - 86;
    if (left >= 90) {
      plus.style.left = `${plusLeft}px`;
      grip.style.left = `${gripLeft}px`;
      plus.style.top = `${lineTop}px`;
      grip.style.top = `${lineTop}px`;
    } else if (left >= 48) {
      // On narrow viewports both legacy offsets clamp to the same x=4px,
      // causing the plus and grip to overlap. Keep the 2px gap immediately
      // before the text instead.
      const rowLeft = Math.max(0, left - 48);
      grip.style.left = `${rowLeft}px`;
      plus.style.left = `${rowLeft + 24}px`;
      plus.style.top = `${lineTop}px`;
      grip.style.top = `${lineTop}px`;
    } else {
      // If even one horizontal row cannot fit before the text, stack the
      // controls in the left gutter without covering the first character.
      grip.style.left = '4px';
      plus.style.left = '4px';
      grip.style.top = `${Math.max(4, lineTop - 24)}px`;
      plus.style.top = `${Math.max(4, lineTop - 24) + 24}px`;
    }
    plus.dataset.visible = 'true';
    grip.dataset.visible = 'true';
  }

  private firstVisualLineRect(block: HTMLElement): DOMRect | null {
    const roots: (Document | ShadowRoot | HTMLElement)[] = [block];
    let editable: HTMLElement | null = null;
    while (roots.length && !editable) {
      const root = roots.shift()!;
      editable = root.querySelector<HTMLElement>('[contenteditable="true"]');
      if (editable) break;
      root.querySelectorAll('*').forEach(element => {
        if (element.shadowRoot) roots.push(element.shadowRoot);
      });
    }
    if (!editable) return null;
    const walker = document.createTreeWalker(editable, NodeFilter.SHOW_TEXT);
    let textNode: Node | null = null;
    while ((textNode = walker.nextNode())) {
      if (textNode.textContent?.length) break;
    }
    if (textNode?.textContent?.length) {
      const range = document.createRange();
      range.setStart(textNode, 0);
      range.setEnd(textNode, 1);
      const rect = range.getBoundingClientRect();
      if (rect.height > 0) return rect;
    }
    const rect = editable.getBoundingClientRect();
    const lineHeight = Number.parseFloat(getComputedStyle(editable).lineHeight);
    return new DOMRect(rect.left, rect.top, rect.width, Number.isFinite(lineHeight) ? lineHeight : rect.height);
  }

  private updateDropTarget(event: PointerEvent) {
    const source = this.dragSource;
    if (!source) return;
    // Pointer capture keeps the event target on the grip. Resolve the actual
    // drop block from the pointer coordinates instead of the captured path.
    const target = document.elementFromPoint(event.clientX, event.clientY)
      ?.closest<HTMLElement>(`[${BLOCK_ID_ATTR}]`);
    const targetId = target?.getAttribute(BLOCK_ID_ATTR);
    const sourceModel = this.store.getBlock(source.id)?.model;
    const targetModel = targetId ? this.store.getBlock(targetId)?.model : null;
    const parent = targetModel && this.store.getParent(targetModel);
    if (!target || !targetId || !sourceModel || !targetModel || targetId === source.id ||
      sourceModel.role !== 'content' || targetModel.role !== 'content' ||
      !parent || parent.id !== this.store.getParent(sourceModel)?.id) {
      this.clearDropTarget();
      return;
    }
    this.clearDropTarget();
    const before = event.clientY < target.getBoundingClientRect().top + target.getBoundingClientRect().height / 2;
    this.dropTarget = { id: targetId, element: target, before, previousBoxShadow: target.style.boxShadow };
    target.style.boxShadow = before ? 'inset 0 2px #4c7dff' : 'inset 0 -2px #4c7dff';
  }

  private clearDropTarget() {
    if (this.dropTarget) this.dropTarget.element.style.boxShadow = this.dropTarget.previousBoxShadow;
    this.dropTarget = null;
  }

  private scheduleHide() {
    if (this.dragSource || this.menuOpen) return;
    this.cancelHide();
    this.hideTimer = setTimeout(() => this.hide(), 180);
  }

  private cancelHide() {
    if (this.hideTimer) clearTimeout(this.hideTimer);
    this.hideTimer = null;
  }

  private hide() {
    this.anchor = null;
    this.clearDropTarget();
    for (const button of [this.plusButton, this.gripButton]) {
      if (button) button.dataset.visible = 'false';
    }
  }
}

if (!customElements.get(WIDGET_TAG)) {
  customElements.define(WIDGET_TAG, DesktopPagePlusWidget);
}

export const DesktopPageLeadingPlusExtension = WidgetViewExtension(
  'affine:page',
  WIDGET_ID,
  literal`${unsafeStatic(WIDGET_TAG)}`
);
