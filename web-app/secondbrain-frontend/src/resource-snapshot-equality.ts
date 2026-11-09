function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    return Object.fromEntries(Object.keys(record).sort().map(key => [key, canonical(record[key])]));
  }
  return value;
}

/** Compare persisted BlockSuite snapshots independent of object insertion order. */
export function sameBlockSuiteSnapshot(left: unknown, right: unknown): boolean {
  return JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
}

/** Edgeless recalculates affine:note frame height while hydrating its viewport. */
export function sameBlockSuiteSnapshotExceptEdgelessNoteFrames(left: unknown, right: unknown): boolean {
  const withoutNoteFrames = (value: unknown): unknown => {
    if (Array.isArray(value)) return value.map(withoutNoteFrames);
    if (!value || typeof value !== 'object') return value;
    const record = value as Record<string, unknown>;
    const copy = Object.fromEntries(Object.entries(record).map(([key, nested]) => [key, withoutNoteFrames(nested)]));
    if (record.flavour === 'affine:note' && copy.props && typeof copy.props === 'object' && !Array.isArray(copy.props)) {
      const props = { ...(copy.props as Record<string, unknown>) };
      delete props.xywh;
      copy.props = props;
    }
    return copy;
  };
  return sameBlockSuiteSnapshot(withoutNoteFrames(left), withoutNoteFrames(right));
}
