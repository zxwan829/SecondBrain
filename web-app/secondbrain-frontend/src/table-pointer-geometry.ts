/** Resolve a point inside a merged cell using the rendered row/column sizes. */
export function weightedCellOffset(offset: number, extent: number, sizes: number[]): number {
  if (!sizes.length || !Number.isFinite(extent) || extent <= 0) return 0;
  const weights = sizes.map(size => Number.isFinite(size) && size > 0 ? size : 1);
  const total = weights.reduce((sum, size) => sum + size, 0);
  let remaining = Math.max(0, Math.min(extent - 0.001, offset));
  for (let index = 0; index < weights.length; index++) {
    const segment = extent * weights[index] / total;
    if (remaining < segment || index === weights.length - 1) return index;
    remaining -= segment;
  }
  return weights.length - 1;
}
