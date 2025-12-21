import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    chunkSizeWarningLimit: 1500, // Monaco adds ~1.2MB (lazy-loaded by @monaco-editor/react)
  },
  server: {
    port: 12001,
    proxy: {
      '/api': {
        target: 'http://localhost:12000',
        changeOrigin: true,
      },
    },
  },
});
