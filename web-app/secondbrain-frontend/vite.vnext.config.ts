import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  base: '/',
  plugins: [react({ jsxRuntime: 'classic' })],
  publicDir: false,
  build: {
    outDir: 'dist-vnext-workbench',
    emptyOutDir: true,
    rollupOptions: { input: 'vnext.html' },
  },
  server: { host: '127.0.0.1', port: 4182, strictPort: true },
});
