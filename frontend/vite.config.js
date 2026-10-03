import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

function enabled(value) {
  return ["1", "true", "on"].includes(String(value || "").trim().toLowerCase());
}

function productionJobsBuildConfig() {
  const dataMode = String(process.env.VITE_PERSONALIZED_JOBS_DATA_MODE || "synthetic").trim().toLowerCase() === "real"
    ? "real"
    : "synthetic";
  return {
    dataMode,
    replaceLegacyJobsNav: enabled(process.env.VITE_REPLACE_LEGACY_JOBS_NAV) && dataMode === "real",
  };
}

function emitProductionBuildConfig() {
  return {
    name: "emit-production-jobs-build-config",
    generateBundle() {
      this.emitFile({
        type: "asset",
        fileName: "runr-build-config.json",
        source: JSON.stringify({ jobs: productionJobsBuildConfig() }, null, 2),
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), emitProductionBuildConfig()],
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
});
