import { defineConfig } from "@hey-api/openapi-ts"

export default defineConfig({
  format: "prettier",
  lint: "eslint",
  client: "fetch",
  input: "openapi.json",
  output: "assets/js/client",
})
