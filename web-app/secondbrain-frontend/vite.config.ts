import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const coreProxyTarget = (globalThis as typeof globalThis & {
    process?: { env?: Record<string, string | undefined> };
}).process?.env?.SB_CORE_PROXY_TARGET ?? 'http://127.0.0.1:8000';

export default defineConfig({
    base: '/',
    plugins: [react({ jsxRuntime: 'classic' })],
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
