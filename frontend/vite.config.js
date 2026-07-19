import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  // Ensure VITE_API_BASE_URL is always defined in production builds.
  // Without this, import.meta.env.VITE_API_BASE_URL may resolve to
  // a literal "${...}" placeholder in the production bundle.
  define: {
    "import.meta.env.VITE_API_BASE_URL":
      mode === "production"
        ? JSON.stringify(process.env.VITE_API_BASE_URL || "/v1")
        : undefined,
  },
  server: {
    host: "127.0.0.1",
    port: 4173,
    proxy: {
      "/v1": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/health": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
}));
