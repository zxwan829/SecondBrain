import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { vanillaExtractPlugin } from '@vanilla-extract/vite-plugin';

export default defineConfig({
  plugins: [vanillaExtractPlugin(), react({ jsxRuntime: 'classic' })],
  test: { environment: 'jsdom', restoreMocks: true },
});
