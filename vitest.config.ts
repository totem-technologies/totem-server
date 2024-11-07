import { defineConfig } from "vitest/config"
import tsconfigPaths from "vite-tsconfig-paths"
import solid from "vite-plugin-solid"

export default defineConfig({
  plugins: [tsconfigPaths(), solid()],
  resolve: {
    conditions: ["development", "browser"],
  },
  test: {
    globals: true,
    environment: "jsdom",
    alias: {
      "tippy.js/headless": "tippy.js/headless/dist/tippy-headless.cjs.js",
    },
  },
})
