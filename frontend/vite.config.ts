import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Config Vite.
 * En dev (npm run dev) hace proxy de /api, /proxy y /ws al backend (VITE_API_TARGET,
 * por defecto http://localhost:8000).
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_API_TARGET ?? env.VITE_BACKEND_URL ?? "http://localhost:8000";
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": { target, changeOrigin: true },
        "/proxy": { target, changeOrigin: true },
        "/ws": { target, ws: true, changeOrigin: true },
      },
    },
    build: { sourcemap: false, chunkSizeWarningLimit: 1200 },
  };
});
