import fs from 'node:fs/promises';

const file = new URL('../node_modules/@blocksuite/affine-gfx-template/src/toolbar/template-panel.ts', import.meta.url);
let source = await fs.readFile(file, 'utf8');
const scopeMarker = 'sb-template-search-scope-zh-v1';
if (!source.includes(scopeMarker)) {
  source = source.replace('  .template-list {', `  /* ${scopeMarker}: this panel searches registered templates, never files. */
  .template-empty-state { padding: 24px 16px; color: var(--affine-text-secondary-color); font-size: 13px; text-align: center; }

  .template-list {`);
  source = source.replace('placeholder="Search file or anything..."', 'placeholder="搜索画布模板（不搜索文件）" aria-label="搜索画布模板"');
  source = source.replace(': repeat(\n                    _templates,', `: _templates.length === 0
                  ? html\`<div class="template-empty-state" role="status">\${this._searchKeyword ? '没有匹配的画布模板' : _categories.length ? '此分类暂无画布模板' : '画布模板库未配置'}。此搜索仅查找模板名称，不搜索文档或文件。</div>\`
                  : repeat(
                    _templates,`);
}
if (source.includes('Search file or anything...')) throw new Error('Misleading canvas template search placeholder remains');
if (!source.includes('没有匹配的画布模板')) throw new Error('Canvas template empty-state patch missing');

const escapeMarker = 'sb-template-search-escape-v1';
if (!source.includes(escapeMarker)) {
  const closePanel = `  private _closePanel() {
    if (this.isDragging) return;
    this.dispatchEvent(new CustomEvent('closepanel'));
  }`;
  if (!source.includes(closePanel)) throw new Error('Canvas template close handler anchor missing');
  source = source.replace(closePanel, `${closePanel}

  private readonly _onPanelKeyDown = (event: KeyboardEvent) => {
    if (event.key !== 'Escape') return;
    event.preventDefault();
    event.stopPropagation();
    this._closePanel();
  }; // ${escapeMarker}`);
  const panelRoot = '<div\n        class="edgeless-templates-panel"';
  if (!source.includes(panelRoot)) throw new Error('Canvas template panel root anchor missing');
  source = source.replace(panelRoot, '<div\n        class="edgeless-templates-panel"\n        @keydown=${this._onPanelKeyDown}');
}

await fs.writeFile(file, source);
console.log('PATCHED · canvas template scope, empty state, and Esc close');
