import { describe, expect, it } from 'vitest';
import { z } from 'zod';

describe('pinned Zod GHSA regression', () => {
  it('uses the fixed Zod release and rejects an oversized constrained collection', () => {
    expect(z.core.version).toEqual({ major: 4, minor: 6, patch: 6 });
    const bounded = z.array(z.string().max(8)).max(32);
    const hostile = Array.from({ length: 200_000 }, () => 'x'.repeat(64));
    expect(bounded.safeParse(hostile).success).toBe(false);
  });
});
