import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { vanillaExtractPlugin } from '@vanilla-extract/vite-plugin';

const coreProxyTarget = (globalThis as typeof globalThis & {
    process?: { env?: Record<string, string | undefined> };
}).process?.env?.SB_CORE_PROXY_TARGET ?? 'http://127.0.0.1:8000';

export default defineConfig({
    base: '/',
    plugins: [vanillaExtractPlugin(), react({ jsxRuntime: 'classic' })],
    esbuild: { target: 'es2022', include: /node_modules\/@blocksuite\/.*\.ts$|src\/.*\.tsx?$/ },
    resolve: { dedupe: ['yjs', 'lit', 'lit-html', '@lit/reactive-element', 'zod'] },
    build: { assetsInlineLimit: 4096 },
    server: {
        proxy: {
            '/api': {
                target: coreProxyTarget,
                changeOrigin: false,
                configure(proxy) {
                    proxy.on('proxyReq', (proxyRequest, request) => {
                        if (request.headers.host) proxyRequest.setHeader('host', request.headers.host);
                    });
                },
            },
        },
    },
});
