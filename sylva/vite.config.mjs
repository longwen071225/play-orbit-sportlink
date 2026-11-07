import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  build: {
    outDir: "dist/client",
  },
  optimizeDeps: {
    include: ["react", "react-dom/client"],
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8100",
      "/demo": "http://127.0.0.1:8100",
      "/console": "http://127.0.0.1:8100",
      "/coach-app": "http://127.0.0.1:8100",
      "/motion-coach": "http://127.0.0.1:8100",
      "/docs": "http://127.0.0.1:8100",
      "/openapi.json": "http://127.0.0.1:8100",
      "/static": "http://127.0.0.1:8100",
      "/assistant/": "http://127.0.0.1:8100",
      "/coach/": "http://127.0.0.1:8100",
      "/family/": "http://127.0.0.1:8100",
      "/admin/": "http://127.0.0.1:8100",
      "/photos/": "http://127.0.0.1:8100",
    },
    host: "0.0.0.0",
    allowedHosts: ["terminal.local"],
    warmup: {
      clientFiles: ["./src/main.jsx"],
    },
  },
  plugins: [react()],
});
