import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built into the Docker image and served by FastAPI at "/". In dev, /api is
// proxied to a local or sandbox backend (VITE_API_PROXY, default :8000).
export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", sourcemap: false, emptyOutDir: true },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: process.env.VITE_API_PROXY ?? "http://localhost:8000", changeOrigin: true },
      "/healthz": { target: process.env.VITE_API_PROXY ?? "http://localhost:8000", changeOrigin: true },
    },
  },
});
