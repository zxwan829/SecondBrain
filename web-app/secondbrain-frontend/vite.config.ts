import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react({ jsxRuntime: 'classic' })],
  build: {
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
});
