import { mergeConfig } from 'vitest/config';
import base from './vitest.config';

// Compile the full BlockSuite Vanilla Extract graph in its own Vite instance.
export default mergeConfig(base, { test: { include: ['src/blocksuite-resource-views.lifecycle.ts'] } });
