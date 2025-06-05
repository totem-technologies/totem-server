#!/usr/bin/env bun
import process from "node:process"

import { SolidPlugin } from "bun-plugin-solid"
const arg = process.argv[2]
const isDev = arg === "dev"

async function build() {
  console.log("Building...")
  const res = await Bun.build({
    entrypoints: ["assets/js/app.ts"],
    minify: true,
    sourcemap: isDev ? "inline" : "none",
    splitting: true,
    outdir: "totem/static/js/bundles",
    format: "esm",
    plugins: [SolidPlugin()],
  })
  console.log("Built")
  // console.log(res)
}

await build()
 