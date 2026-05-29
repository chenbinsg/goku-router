import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  // When the backend serves the SPA (Docker build), it lives under /console.
  // Dev server (npm run dev) leaves this at '/'.
  base: process.env.VITE_BASE || '/',
  plugins: [react()],
  server: {
    port: 3000
  },
  build: {
    chunkSizeWarningLimit: 900,
  },
});
