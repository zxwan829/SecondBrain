import { readdirSync } from 'node:fs';
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
    // BlockSuite publishes source entrypoints with `.css.ts` Vanilla Extract files.
    // Vite's dependency optimizer bypasses the Vanilla Extract transform, so keep
    // this lazy editor graph in the normal plugin pipeline during dev.
    optimizeDeps: {
        // This CJS child dependency of @blocksuite/store still needs Vite's
        // ESM compatibility wrapper when its BlockSuite parent is excluded.
        include: ['lodash.ismatch', 'bind-event-listener', 'raf-schd', 'extend', 'debug', 'ms', 'bytes'],
        // Every BlockSuite package must stay in the same source module graph.
        // Optimizing a resource package while Foundation remains source creates
        // different Lit constructors for registration and instantiation.
        exclude: readdirSync(new URL('./node_modules/@blocksuite/', import.meta.url))
            .map(name => `@blocksuite/${name}`),
    },
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
