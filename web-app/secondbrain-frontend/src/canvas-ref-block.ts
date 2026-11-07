import { BlockSchemaExtension, BlockModel, defineBlockSchema } from '@blocksuite/store';
import { StoreExtensionProvider, ViewExtensionProvider } from '@blocksuite/affine-ext-loader';
import { BlockComponent, BlockSelection, BlockViewExtension, FlavourExtension } from '@blocksuite/std';
import { css, html, nothing, svg } from 'lit';
import { literal } from 'lit/static-html.js';
import { resolvePreviewColor, type CanvasPreviewShape } from './canvas-preview';

export const CANVAS_REF_FLAVOUR = 'sb:canvas-ref';
export const CANVAS_REF_CREATE_EVENT = 'sb-canvas-ref-create';
export const CANVAS_REF_OPEN_EVENT = 'sb-canvas-ref-open';
export const CANVAS_REF_COPY_EVENT = 'sb-canvas-ref-copy';
export const CANVAS_REF_DELETE_EVENT = 'sb-canvas-ref-delete';
export const CANVAS_REF_RESIZE_EVENT = 'sb-canvas-ref-resize';

export type { CanvasPreviewShape } from './canvas-preview';

export type CanvasRefProps = {
  resourceId: string;
  docId: string;
  title: string;
  state: 'creating' | 'ready' | 'missing' | 'error';
  revision: string;
  previewJson: string;
  error: string;
  previewWidth: number;
  previewHeight: number;
};

export const CanvasRefBlockSchema = defineBlockSchema({
  flavour: CANVAS_REF_FLAVOUR,
  metadata: { version: 1, role: 'content', parent: ['affine:note'] },
  props: () => ({
    resourceId: '',
    docId: '',
    title: '内嵌画布',
    state: 'creating' as CanvasRefProps['state'],
    revision: '',
    previewJson: '[]',
    error: '',
    previewWidth: 0,
    previewHeight: 220,
  }),
  toModel: () => new CanvasRefBlockModel(),
});

export class CanvasRefBlockModel extends BlockModel<CanvasRefProps> {}

export class CanvasRefStoreExtension extends StoreExtensionProvider {
  override name = 'secondbrain-canvas-ref-store';
  override setup(context: any) {
    super.setup(context);
    context.register(BlockSchemaExtension(CanvasRefBlockSchema));
  }
}

export class CanvasRefViewExtension extends ViewExtensionProvider {
  override name = 'secondbrain-canvas-ref-view';
  override setup(context: any) {
    super.setup(context);
    context.register([
      FlavourExtension(CANVAS_REF_FLAVOUR),
      BlockViewExtension(CANVAS_REF_FLAVOUR, literal`sb-canvas-ref`),
    ]);
  }
}

function readPreview(json: string): CanvasPreviewShape[] | null {
  try {
    const value: unknown = JSON.parse(json);
    if (!Array.isArray(value)) return null;
    return value.filter((item): item is CanvasPreviewShape =>
      !!item && typeof item.id === 'string' && Array.isArray(item.bound) && item.bound.length === 4 &&
      item.bound.every(Number.isFinite) && typeof item.type === 'string'
    );
  } catch {
    return null;
  }
}

export class CanvasRefBlockComponent extends BlockComponent<CanvasRefBlockModel> {
  static override styles = css`
    :host { display: block; margin: 14px 0; }
    .canvas-ref { overflow: hidden; border: 1px solid #cbd5e1; border-radius: 10px; background: #fff; }
    .canvas-ref[data-selected="true"] { outline: 2px solid #4d7cfe; outline-offset: 1px; }
    header, footer { display: flex; align-items: center; gap: 10px; padding: 10px 12px; }
    header { border-bottom: 1px solid #e5eaf1; }
    header strong { flex: 1; font-size: 14px; }
    .badge { padding: 2px 7px; border-radius: 99px; background: #edf3ff; color: #345a9e; font-size: 11px; }
    .preview { position: relative; display: grid; min-height: 128px; place-items: center; overflow: hidden; background: radial-gradient(#e7ebf2 1px, transparent 1px) 0 0 / 18px 18px, #f8fafc; }
    .preview svg { position: absolute; inset: 8px; width: calc(100% - 16px); height: calc(100% - 16px); }
    .preview .shape { vector-effect: non-scaling-stroke; }
    .preview .connector { fill: none; vector-effect: non-scaling-stroke; }
    .preview .shape-label { pointer-events: none; }
    .empty, .failure { padding: 25px; color: #6b7280; font-size: 13px; text-align: center; }
    .failure { color: #9b2c2c; }
    footer { justify-content: space-between; flex-wrap: wrap; border-top: 1px solid #e5eaf1; }
    .actions { display: flex; flex-wrap: wrap; gap: 6px; }
    button { border: 1px solid #cbd5e1; border-radius: 6px; padding: 5px 9px; background: #fff; color: #263244; cursor: pointer; }
    button:hover { background: #f1f5fb; }
    button:disabled { opacity: .5; cursor: wait; }
    code { color: #64748b; font-size: 10px; }
    :host { max-width: 100%; margin: 18px 0; }
    .canvas-ref { position: relative; width: min(100%, var(--sb-canvas-width, 100%)); max-width: 100%; border: 1px solid var(--sb-table-cell-border, rgba(0, 0, 0, 0.1)); border-radius: 6px; background: transparent; transition: outline-color .15s; }
    .canvas-ref:hover, .canvas-ref:focus-visible, .canvas-ref[data-selected="true"] { border-color: var(--sb-table-cell-border, rgba(0, 0, 0, 0.1)); background: transparent; box-shadow: none; outline: 1px solid #dfe4eb; outline-offset: 2px; }
    header, footer { display: none; }
    .preview { height: var(--sb-canvas-height, 220px); min-height: 120px; background: transparent; cursor: zoom-in; }
    .preview rect, .preview ellipse { stroke-width: 2.4; }
    .preview line { stroke-width: 2.4; }
    .controls { position: absolute; top: 8px; right: 8px; display: flex; opacity: 0; transform: translateY(-3px); transition: opacity .14s, transform .14s; }
    .canvas-ref:hover .controls, .canvas-ref:focus-within .controls, .canvas-ref[data-selected="true"] .controls { opacity: 1; transform: translateY(0); }
    .resize { position: absolute; right: 3px; bottom: 3px; width: 20px; height: 20px; padding: 0; border: 0; background: transparent; color: #778397; cursor: nwse-resize; opacity: 0; box-shadow: none; }
    .canvas-ref:hover .resize, .canvas-ref:focus-within .resize, .canvas-ref[data-selected="true"] .resize { opacity: .75; }
    .context-menu { position: absolute; z-index: 12; top: 42px; right: 8px; display: grid; min-width: 156px; padding: 4px; border: 1px solid #e1e6ed; border-radius: 9px; background: white; box-shadow: 0 8px 24px rgb(26 38 56 / 14%); }
    .context-menu button { width: 100%; height: auto; padding: 8px 10px; border: 0; border-radius: 6px; box-shadow: none; text-align: left; font-size: 12px; }
    .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; }
  `;

  private contextMenuOpen = false;
  private resizing: { pointerId: number; startX: number; startY: number; width: number; height: number; maxWidth: number } | null = null;
  private previewBox: { width: number; height: number } | null = null;

  private get props() { return this.model.props; }

  private onDocumentPointerDown = (event: PointerEvent) => {
    if (!this.contextMenuOpen) return;
    const inMenu = event.composedPath().some(node => node instanceof Element && node.closest('.context-menu'));
    if (inMenu) return;
    this.contextMenuOpen = false;
    this.requestUpdate();
  };

  private onDocumentScroll = () => {
    if (!this.contextMenuOpen) return;
    this.contextMenuOpen = false;
    this.requestUpdate();
  };

  private onDocumentKeyDown = (event: KeyboardEvent) => {
    if (!this.contextMenuOpen || event.key !== 'Escape') return;
    event.preventDefault();
    event.stopPropagation();
    this.contextMenuOpen = false;
    this.requestUpdate();
  };

  override connectedCallback() {
    super.connectedCallback();
    document.addEventListener('pointerdown', this.onDocumentPointerDown, true);
    document.addEventListener('keydown', this.onDocumentKeyDown, true);
    document.addEventListener('scroll', this.onDocumentScroll, true);
  }

  override disconnectedCallback() {
    document.removeEventListener('pointerdown', this.onDocumentPointerDown, true);
    document.removeEventListener('keydown', this.onDocumentKeyDown, true);
    document.removeEventListener('scroll', this.onDocumentScroll, true);
    this.removeResizeListeners();
    super.disconnectedCallback();
  }

  private selectBlock = () => {
    this.selection.update(() => [this.selection.create(BlockSelection, { blockId: this.blockId })]);
  };

  private dispatch(eventName: string) {
    (this.std.host as HTMLElement).dispatchEvent(new CustomEvent(eventName, { bubbles: true, composed: true, detail: {
      blockId: this.blockId,
      resourceId: this.props.resourceId,
      docId: this.props.docId,
      title: this.props.title,
    } }));
  }

  private stopAndDispatch(event: Event, eventName: string) {
    event.preventDefault();
    event.stopPropagation();
    this.selectBlock();
    this.dispatch(eventName);
  }

  private open = (event: Event) => this.stopAndDispatch(event, CANVAS_REF_OPEN_EVENT);
  private copy = (event: Event) => this.stopAndDispatch(event, CANVAS_REF_COPY_EVENT);
  private removeReference = (event: Event) => this.stopAndDispatch(event, CANVAS_REF_DELETE_EVENT);

  private onKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Escape') { this.contextMenuOpen = false; this.requestUpdate(); return; }
    if (event.key === 'Enter' && !this.contextMenuOpen) { this.open(event); return; }
    if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) {
      event.preventDefault(); this.selectBlock(); this.contextMenuOpen = true; this.requestUpdate();
    }
  };

  private onContextMenu = (event: MouseEvent) => {
    event.preventDefault(); event.stopPropagation(); this.selectBlock(); this.contextMenuOpen = true; this.requestUpdate();
  };

  private beginResize = (event: PointerEvent) => {
    event.preventDefault(); event.stopPropagation();
    const article = (event.currentTarget as HTMLElement).closest<HTMLElement>('.canvas-ref');
    const preview = article?.querySelector<HTMLElement>('.preview');
    if (!article || !preview) return;
    const rect = article.getBoundingClientRect();
    const previewRect = preview.getBoundingClientRect();
    this.resizing = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, width: rect.width, height: previewRect.height, maxWidth: article.parentElement?.getBoundingClientRect().width ?? rect.width };
    this.previewBox = { width: rect.width, height: previewRect.height };
    (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
    window.addEventListener('pointermove', this.resizeMove, true);
    window.addEventListener('pointerup', this.finishResize, true);
    window.addEventListener('pointercancel', this.cancelResize, true);
  };

  private resizeMove = (event: PointerEvent) => {
    const resize = this.resizing;
    if (!resize || event.pointerId !== resize.pointerId) return;
    this.previewBox = {
      width: Math.max(320, Math.min(resize.maxWidth, Math.round(resize.width + event.clientX - resize.startX))),
      height: Math.max(140, Math.min(680, Math.round(resize.height + event.clientY - resize.startY))),
    };
    this.requestUpdate();
  };

  private finishResize = (event: PointerEvent) => {
    if (!this.resizing || event.pointerId !== this.resizing.pointerId) return;
    const size = this.previewBox;
    this.removeResizeListeners(); this.resizing = null; this.previewBox = null;
    if (!size) return;
    this.store.captureSync();
    this.store.updateBlock(this.model, { previewWidth: size.width, previewHeight: size.height });
    this.store.captureSync();
    (this.std.host as HTMLElement).dispatchEvent(new CustomEvent(CANVAS_REF_RESIZE_EVENT, { bubbles: true, composed: true, detail: { blockId: this.blockId, width: size.width, height: size.height } }));
  };

  private cancelResize = () => { this.removeResizeListeners(); this.resizing = null; this.previewBox = null; this.requestUpdate(); };

  private removeResizeListeners() {
    window.removeEventListener('pointermove', this.resizeMove, true);
    window.removeEventListener('pointerup', this.finishResize, true);
    window.removeEventListener('pointercancel', this.cancelResize, true);
  }

  override renderBlock() {
    const title = this.props.title || '内嵌画布';
    const state = this.props.state;
    const preview = readPreview(this.props.previewJson);
    const bounds = preview?.map(item => item.bound);
    const minX = bounds?.length ? Math.min(...bounds.map(bound => bound[0])) : 0;
    const minY = bounds?.length ? Math.min(...bounds.map(bound => bound[1])) : 0;
    const maxX = bounds?.length ? Math.max(...bounds.map(bound => bound[0] + bound[2])) : 1;
    const maxY = bounds?.length ? Math.max(...bounds.map(bound => bound[1] + bound[3])) : 1;
    const padding = bounds?.length ? Math.max(12, Math.min(maxX - minX, maxY - minY) * .08) : 0;
    const width = this.previewBox?.width ?? this.props.previewWidth;
    const height = this.previewBox?.height ?? this.props.previewHeight;
    const sizeStyle = '--sb-canvas-width:' + (width > 0 ? width + 'px' : '100%') + ';--sb-canvas-height:' + (height > 0 ? height + 'px' : '220px');

    return html`<article class="canvas-ref" data-selected=${String(this.selected$.value)} style=${sizeStyle} role="group" tabindex="0" aria-label="${title}，画布预览。按 Enter 编辑，按 Shift+F10 打开操作菜单。" @click=${this.selectBlock} @dblclick=${this.open} @keydown=${this.onKeyDown} @contextmenu=${this.onContextMenu}>
      <span class="sr-only">${title}</span>
      <div class="preview" aria-label="${title}预览，双击进入编辑">
        ${state === 'missing' || state === 'error'
          ? html`<div class="failure">${this.props.error || '画布资源无法读取；原引用已保留，不会自动创建空画布。'}</div>`
          : state === 'creating'
            ? html`<div class="empty">正在保存独立画布资源，请稍候…</div>`
            : preview === null
              ? html`<div class="failure">预览数据无效；原画布资源仍保留，可重新加载。</div>`
              : preview.length === 0
                ? html`<div class="empty">空白画布 · 双击或按 Enter 开始编辑</div>`
                : html`<svg viewBox="${`${minX-padding} ${minY-padding} ${Math.max(1,maxX-minX+padding*2)} ${Math.max(1,maxY-minY+padding*2)}`}" preserveAspectRatio="xMidYMid meet">
                    ${preview.map(item => {
                      const [x,y,w,h] = item.bound;
                      const fill = item.filled ? resolvePreviewColor(item.fillColor, 'transparent') : 'transparent';
                      const stroke = resolvePreviewColor(item.strokeColor, '#334155');
                      const dash = item.strokeStyle && item.strokeStyle.toLowerCase().includes('dash') ? '6 4' : undefined;
                      const transform = item.rotate ? `rotate(${item.rotate} ${x+w/2} ${y+h/2})` : undefined;
                      if (item.type === 'connector') {
                        const points = item.points ?? [[x,y],[x+w,y+h]];
                        return svg`<polyline class="connector" data-element-id=${item.id} points=${points.map(point => point.join(',')).join(' ')} fill="none" stroke=${stroke} stroke-width=${item.strokeWidth ?? 2} stroke-dasharray=${dash ?? nothing} opacity=${item.opacity ?? 1}></polyline>`;
                      }
                      if (item.type !== 'shape') return nothing;
                      const shape = item.shapeType.toLowerCase().includes('ellipse')
                        ? svg`<ellipse class="shape" data-element-id=${item.id} cx=${x+w/2} cy=${y+h/2} rx=${w/2} ry=${h/2} fill=${fill} stroke=${stroke} stroke-width=${item.strokeWidth ?? 2} stroke-dasharray=${dash ?? nothing} opacity=${item.opacity ?? 1}></ellipse>`
                        : item.shapeType.toLowerCase().includes('triangle')
                          ? svg`<polygon class="shape" data-element-id=${item.id} points="${x+w/2},${y} ${x+w},${y+h} ${x},${y+h}" fill=${fill} stroke=${stroke} stroke-width=${item.strokeWidth ?? 2} stroke-dasharray=${dash ?? nothing} opacity=${item.opacity ?? 1}></polygon>`
                          : item.shapeType.toLowerCase().includes('diamond')
                            ? svg`<polygon class="shape" data-element-id=${item.id} points="${x+w/2},${y} ${x+w},${y+h/2} ${x+w/2},${y+h} ${x},${y+h/2}" fill=${fill} stroke=${stroke} stroke-width=${item.strokeWidth ?? 2} stroke-dasharray=${dash ?? nothing} opacity=${item.opacity ?? 1}></polygon>`
                            : svg`<rect class="shape" data-element-id=${item.id} x=${x} y=${y} width=${w} height=${h} rx=${item.radius ?? 0} fill=${fill} stroke=${stroke} stroke-width=${item.strokeWidth ?? 2} stroke-dasharray=${dash ?? nothing} opacity=${item.opacity ?? 1}></rect>`;
                      const textColor = resolvePreviewColor(item.color, '#263244');
                      const horizontal = (item.textAlign ?? 'center').toLowerCase();
                      const textAnchor = horizontal === 'left' ? 'start' : horizontal === 'right' ? 'end' : 'middle';
                      const textX = horizontal === 'left' ? x + 8 : horizontal === 'right' ? x + w - 8 : x + w / 2;
                      const vertical = (item.textVerticalAlign ?? 'middle').toLowerCase();
                      const textY = vertical === 'top' ? y + 8 + (item.fontSize ?? 14) : vertical === 'bottom' ? y + h - 8 : y + h / 2;
                      return svg`<g transform=${transform ?? nothing}>${shape}${item.text ? svg`<text class="shape-label" x=${textX} y=${textY} text-anchor=${textAnchor} dominant-baseline=${vertical === 'middle' ? 'middle' : 'auto'} fill=${textColor} font-size=${item.fontSize ?? 14} font-family=${item.fontFamily ?? 'sans-serif'} font-weight=${item.fontWeight ?? '400'}>${item.text}</text>` : nothing}</g>`;
                    })}
                  </svg>`}
        ${state === 'missing' || state === 'error' ? html`<span class="status" role="status">画布暂不可用</span>` : nothing}
        <span class="controls"><button type="button" aria-label="画布操作" title="画布操作" @click=${(event: Event) => { event.preventDefault(); event.stopPropagation(); this.contextMenuOpen = !this.contextMenuOpen; this.requestUpdate(); }}>⋯</button></span>
        <button class="resize" type="button" aria-label="调整画布预览大小" title="拖动调整预览大小" @pointerdown=${this.beginResize}>◢</button>
        ${this.contextMenuOpen ? html`<div class="context-menu" role="menu" @click=${(event: Event) => event.stopPropagation()}><button role="menuitem" @click=${this.copy}>复制为独立画布</button><button role="menuitem" @click=${this.removeReference}>从正文移除引用</button></div>` : nothing}
      </div>
    </article>`;
  }
}

if (!customElements.get('sb-canvas-ref')) customElements.define('sb-canvas-ref', CanvasRefBlockComponent);
