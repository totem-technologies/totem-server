import tailwindcss from "@tailwindcss/vite"
import solid from "vite-plugin-solid"
import { defineConfig } from "vitest/config"

export default defineConfig(({ mode }) => ({
  plugins: [solid(), tailwindcss()],
  resolve: {
    tsconfigPaths: true,
    // Solid's dev build for tests only; builds use the default conditions.
    conditions: mode === "test" ? ["development", "browser"] : undefined,
  },
  build: {
    outDir: "totem/static/js/bundles",
    // atcb.min.js is built into the same dir by build:atcb.
    emptyOutDir: false,
    minify: mode === "production",
    sourcemap: mode === "production" ? false : ("inline" as const),
    rollupOptions: {
      // Fixed output names: Django templates reference these via {% static %}.
      input: {
        app: "assets/js/app.ts",
        styles: "assets/css/styles.css",
      },
      output: {
        entryFileNames: "[name].js",
        chunkFileNames: "[name]-[hash].js",
        assetFileNames: "[name][extname]",
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./assets/js/testSetup.ts"],
    alias: {
      "tippy.js/headless": "tippy.js/headless/dist/tippy-headless.cjs.js",
    },
  },
}))
