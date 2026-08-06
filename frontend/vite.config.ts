import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Proxy des routes du backend (pipelines diagnostic et économie)
      '/api': {
        target: 'http://localhost:8765',
        changeOrigin: true,
      },
      '/diagnostic': {
        target: 'http://localhost:8765',
        changeOrigin: true,
      },
    },
  },
});