import js from "@eslint/js"
import solid from "eslint-plugin-solid/configs/typescript.js"
import tailwind from "eslint-plugin-tailwindcss"
import ts from "typescript-eslint"

/* @type {import("eslint").Linter.FlatConfig[]} */
export default [
  { ignores: ["assets/js/client/**/*.ts", "assets/js/models/**/*.ts", "**/*.min.*"] },
  // JavaScript
  js.configs.recommended,

  // TypeScript
  ...ts.configs.recommendedTypeChecked,
  ...ts.configs.stylisticTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        project: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },

  // JavaScript...again
  {
    files: ["**/*.cjs", "**/*.js", "**/*.jsx", "**/*.mjs"],
    ...ts.configs.disableTypeChecked,
  },

  // JSX/Solid/TailwindCSS
  solid,
  ...tailwind.configs["flat/recommended"],
  {
    rules: {
      "@typescript-eslint/no-unused-vars": [
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
  },
]
