import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  const pluginId = env.VITE_PLUGIN_ID || 'secondbrain-fe-test';
  return {
    base: env.VITE_ASSET_BASE || '/dashboard-plugins/secondbrain-fe-test/',
    define: { __SB_PLUGIN_ID__: JSON.stringify(pluginId) },
    plugins: [react({ jsxRuntime: 'classic' })],
    build: {
      assetsInlineLimit: 4096,
      rollupOptions: {
        external: ['react', 'react-dom'],
        output: {
          format: 'iife',
          name: 'SecondBrainFeTest',
          globals: {
            react: '__HERMES_PLUGIN_SDK__.React',
            'react-dom': '__HERMES_PLUGIN_SDK__.ReactDOM',
          }
        }
      }
    }
  };
});
