import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    // The unified Docker image uses VITE_BASE=/console/. The standalone
    // frontend deployment uses VITE_FRONTEND_BASE=/router/.
    base: env.VITE_FRONTEND_BASE || process.env.VITE_BASE || '/',
    plugins: [react()],
    server: {
      port: 3000
    },
    build: {
      chunkSizeWarningLimit: 900,
    },
  };
});
