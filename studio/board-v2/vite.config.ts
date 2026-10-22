import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Construit vers lib/jarvis/studio_v2 : le Studio Python sert ce dossier sous /v2/ (aucun serveur Node en production).
export default defineConfig({
  base: "/v2/",
  plugins: [react()],
  build: {
    outDir: "../../lib/jarvis/studio_v2",
    emptyOutDir: true,
    target: "es2022",
    sourcemap: false,
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (id.includes("pdfjs-dist")) return "pdf";
          if (id.includes("@xyflow")) return "flow";
          if (id.includes("node_modules/react") || id.includes("scheduler")) return "react";
          if (id.includes("node_modules/motion") || id.includes("framer")) return "motion";
          return undefined;
        },
      },
    },
  },
  server: {
    port: 5178,
    proxy: { "/api": "http://127.0.0.1:7718" },
  },
});
