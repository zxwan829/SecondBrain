/** Removes only the update prefixes included in a completed save request. */
export function removeCommittedPrefixes<T>(pending: Map<string, T[]>, committedCounts: Map<string, number>) {
  for (const [docId, committedCount] of committedCounts) {
    if (committedCount <= 0) continue;
    const current = pending.get(docId);
    if (!current) continue;
    const remaining = current.slice(committedCount);
    if (remaining.length) pending.set(docId, remaining);
    else pending.delete(docId);
  }
}
