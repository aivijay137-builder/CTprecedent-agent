import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

const demo = (f: string) => fileURLToPath(new URL(`./src/demo/${f}`, import.meta.url));

// /api goes to the FastAPI server, so the browser sees one origin.
// `vite build --mode demo` builds the click-through demo: no server, saved real results (src/demo/data.json), output in dist-demo/.
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: { host: true, port: 5173, strictPort: true, proxy: { "/api": "http://127.0.0.1:8765" } },
  ...(mode === "demo" ? {
    resolve: { alias: [
      { find: /^(\.\.?\/)+api$/, replacement: demo("api.ts") },
      { find: /^(\.\.?\/)+source$/, replacement: demo("source.ts") },
    ] },
    build: { outDir: "dist-demo", assetsInlineLimit: 100_000_000, cssCodeSplit: false },
  } : {}),
}));
