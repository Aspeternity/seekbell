import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@workspace': '/src/prototype/store.ts' } },
  server: { host: '127.0.0.1', port: 5174, strictPort: true },
  build: { outDir: 'dist-prototype', rollupOptions: { input: 'prototype.html' } },
})
