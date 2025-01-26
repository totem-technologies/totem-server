#!/usr/bin/env bun
import process from "node:process"

import { watch } from "node:fs"
import { SolidPlugin } from "bun-plugin-solid"
const arg = process.argv[2]
const isWatch = arg === "watch"

async function build() {
  console.log("Building...")
  const res = await Bun.build({
    entrypoints: ["assets/js/app.ts"],
    minify: true,
    sourcemap: isWatch ? "inline" : "none",
    splitting: true,
    outdir: "totem/static/js/bundles",
    format: "esm",
    plugins: [SolidPlugin()],
  })
  console.log("Built")
  // console.log(res)
}

if (isWatch) {
  await build()
  const srcWatcher = watch(
    `${import.meta.dir}/assets`,
    { recursive: true },
    async (event, filename) => {
      console.log(`Detected ${event} in ${filename} (src)`)
      await build()
    }
  )

  process.on("SIGINT", () => {
    srcWatcher.close()
    process.exit(0)
  })
} else {
  await build()
}
