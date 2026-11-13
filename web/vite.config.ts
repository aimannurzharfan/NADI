/// <reference types="vitest" />
import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Built files go to web/dist, which FastAPI serves (committed, so the demo laptop needs no Node).
// Dev: npm run dev, with the NADI server on port 8000.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src"), "@strings": path.resolve(__dirname, "../dashboard/strings.json"),
    "@plan": path.resolve(__dirname, "../dashboard/plan.json") } },
  server: { proxy: { "/api": "http://127.0.0.1:8000" }, fs: { allow: [".."] } },
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 900 },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test/setup.ts"] },
});
