import { mergeConfig } from 'vitest/config';
import base from './vitest.config';

// Compile the full BlockSuite Vanilla Extract graph in its own Vite instance.
export default mergeConfig(base, { test: {
  include: ['src/blocksuite-resource-views.lifecycle.ts'],
  // BlockSuite ships Vanilla Extract source under node_modules. Externalizing
  // it bypasses the Vite plugin and leaves the generated CSS virtual modules
  // unresolved in this focused lifecycle smoke test.
  server: { deps: { inline: [/[@]blocksuite[/\\]/] } },
} });
