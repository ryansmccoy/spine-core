import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  
  // Backend URL - defaults to localhost:8001 (Market Spine Basic)
  const backendUrl = env.VITE_MARKET_SPINE_URL || 'http://localhost:8001';
  
  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 3000,
      proxy: {
        // Proxy /v1/* to the Market Spine backend
        '/v1': {
          target: backendUrl,
          changeOrigin: true,
        },
        // Legacy /api/* proxy for backwards compatibility
        '/api': {
          target: backendUrl,
          changeOrigin: true,
        },
      },
    },
    define: {
      // Expose the profile name for display purposes
      'import.meta.env.VITE_MARKET_SPINE_PROFILE': JSON.stringify(
        env.VITE_MARKET_SPINE_PROFILE || 'basic'
      ),
    },
  };
});
