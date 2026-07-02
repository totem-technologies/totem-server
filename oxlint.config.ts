import { defineConfig } from "oxlint"
// Pull in eslint-plugin-solid's `typescript` recommended ruleset directly, so the
// Solid rules stay in sync with the installed plugin instead of being a hand-copied
// snapshot. oxlint doesn't apply a jsPlugin's preset on its own, so we spread its
// rules into our config explicitly.
import solidTs from "eslint-plugin-solid/configs/typescript"

export default defineConfig({
  ignorePatterns: [
    "assets/js/client/**/*.ts",
    "**/*.min.*",
    "totem/static/js/bundles/**",
  ],
  env: {
    browser: true,
    es2024: true,
  },
  jsPlugins: ["eslint-plugin-solid"],
  categories: {
    correctness: "error",
  },
  rules: {
    ...solidTs.rules,
    "no-unused-vars": [
      "error",
      {
        args: "all",
        argsIgnorePattern: "^_",
        caughtErrors: "all",
        caughtErrorsIgnorePattern: "^_",
        destructuredArrayIgnorePattern: "^_",
        varsIgnorePattern: "^_",
        ignoreRestSiblings: true,
      },
    ],
  },
  overrides: [
    {
      files: ["scripts/**/*.mjs", "*.config.*", "build.ts"],
      env: {
        node: true,
      },
    },
  ],
})
