import { resolve } from "node:path";
import { defineConfig } from "vite";

/**
 * DORMANT until Node is installed — the extension currently loads unpacked
 * straight from `src/` with no build step.
 *
 * MV3 content scripts cannot be ES modules, so each entry is emitted as a
 * self-contained IIFE with no shared chunks and stable filenames the manifest
 * can reference.
 */
export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        content: resolve(__dirname, "src/content/content.ts"),
        background: resolve(__dirname, "src/background/service-worker.ts"),
        popup: resolve(__dirname, "src/popup/popup.html"),
      },
      output: {
        format: "iife",
        inlineDynamicImports: false,
        entryFileNames: "[name].js",
        assetFileNames: "[name].[ext]",
      },
      preserveEntrySignatures: false,
    },
    target: "chrome111",
    sourcemap: true,
  },
});
