/** Full-format native resources must never be silently projected into plain Notes. */
export type PlainMarkdownFormatViolation = {
  reason: 'paragraph-alignment' | 'table-merge' | 'table-alignment' | 'table-color' | 'table-row-height'
    | 'table-column-width' | 'inline-format' | 'native-resource-block' | 'native-graphics' | 'invalid-snapshot';
  blockId: string | null;
};
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const present = (value: unknown) => value !== undefined && value !== null && value !== '' && value !== false;
const entries = (value: unknown): Record<string, unknown>[] => object(value) ? Object.values(value).filter(object) : [];
const nativeFlavours = new Set(['affine:database', 'affine:data-view', 'affine:surface-ref', 'affine:edgeless-text', 'affine:frame', 'sb:canvas-ref']);
const lostInline = new Set(['color', 'background', 'backgroundColor', 'fontSize', 'fontFamily', 'textAlign', 'underline', 'reference']);

export function findPlainMarkdownFormatViolations(snapshot: unknown): PlainMarkdownFormatViolation[] {
  if (!object(snapshot)) return [{ reason: 'invalid-snapshot', blockId: null }];
  const violations: PlainMarkdownFormatViolation[] = [];
  const seen = new WeakSet<object>();
  const pending: Array<{ value: unknown; blockId: string | null }> = [{ value: snapshot, blockId: null }];
  const add = (reason: PlainMarkdownFormatViolation['reason'], blockId: string | null) => {
    if (!violations.some(item => item.reason === reason && item.blockId === blockId)) violations.push({ reason, blockId });
  };
  while (pending.length) {
    const { value, blockId: inheritedId } = pending.pop()!;
    if (!value || typeof value !== 'object' || seen.has(value)) continue;
    seen.add(value);
    if (violations.length >= 32) break;
    if (Array.isArray(value)) { value.forEach(child => pending.push({ value: child, blockId: inheritedId })); continue; }
    const node = value as Record<string, unknown>;
    const blockId = typeof node.flavour === 'string' && typeof node.id === 'string' ? node.id : inheritedId;
    const props = object(node.props) ? node.props : {};
    if (node.flavour === 'affine:paragraph' && present(props.textAlign) && props.textAlign !== 'left') add('paragraph-alignment', blockId);
    if (node.flavour === 'affine:table') {
      if (object(props.mergeRegions) && Object.keys(props.mergeRegions).length) add('table-merge', blockId);
      for (const cell of entries(props.cells)) {
        if ((present(cell.textAlign) && cell.textAlign !== 'left') || (present(cell.verticalAlign) && cell.verticalAlign !== 'top')) add('table-alignment', blockId);
        if (['backgroundColor', 'background', 'color', 'textColor'].some(key => present(cell[key]))) add('table-color', blockId);
      }
      for (const row of entries(props.rows)) {
        if (present(row.minHeight)) add('table-row-height', blockId);
        if (present(row.backgroundColor)) add('table-color', blockId);
      }
      for (const column of entries(props.columns)) {
        if (present(column.width)) add('table-column-width', blockId);
        if (present(column.backgroundColor)) add('table-color', blockId);
      }
    }
    if (nativeFlavours.has(String(node.flavour))) add('native-resource-block', blockId);
    if (node.flavour === 'affine:surface' && object(props.elements) && Object.keys(props.elements).length) add('native-graphics', blockId);
    if (object(node.attributes) && Object.entries(node.attributes).some(([key, val]) => lostInline.has(key) && present(val))) add('inline-format', blockId);
    Object.values(node).forEach(child => pending.push({ value: child, blockId }));
  }
  return violations;
}

export class PlainMarkdownFormatError extends Error {
  constructor(readonly violations: PlainMarkdownFormatViolation[]) {
    super('当前格式无法无损保存为普通 Markdown；已停止正文写入并保留原始文档。请下载恢复副本，或显式创建富 Page 副本继续。');
    this.name = 'PlainMarkdownFormatError';
  }
}
export function assertPlainSnapshotMarkdownCompatible(snapshot: unknown): void {
  const violations = findPlainMarkdownFormatViolations(snapshot);
  if (violations.length) throw new PlainMarkdownFormatError(violations);
}
