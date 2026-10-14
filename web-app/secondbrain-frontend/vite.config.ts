import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
    base: '/',
    plugins: [react({ jsxRuntime: 'classic' })],
    build: { assetsInlineLimit: 4096 },
    server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
});
