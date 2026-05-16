import { defineConfig } from "vite";

export default defineConfig({
  // Tenants embed the widget with a single <script src="..."> tag, so we
  // bundle everything into one self-executing file with no external deps.
  build: {
    lib: {
      entry: "src/main.ts",
      formats: ["iife"],
      name: "RagWidget",
      fileName: () => "rag-widget.js",
    },
    rollupOptions: {
      output: {
        // No globals needed; everything is bundled.
        extend: true,
      },
    },
    cssCodeSplit: false,
  },
  server: {
    port: 5173,
  },
});
