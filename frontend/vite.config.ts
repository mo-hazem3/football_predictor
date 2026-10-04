import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development the Django API runs on :8000; proxying /api avoids CORS entirely. In production the build is
// served from another origin and calls VITE_API_URL directly (the backend's CORS_ALLOWED_ORIGINS must list it).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    css: false,
  },
});
