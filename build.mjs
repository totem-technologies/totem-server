#!/usr/bin/env node
import * as esbuild from "esbuild"
import { solidPlugin } from "esbuild-plugin-solid"
import fs from "node:fs"
import process from "node:process"

const arg = process.argv[2]

const options = {
  entryPoints: ["assets/js/app.js", "assets/js/social.ts"],
  bundle: true,
  minify: true,
  metafile: true,
  loader: {
    ".svg": "dataurl",
    // ".css": "local-css",
  },
  logLevel: "info",
  sourcemap: true,
  // outfile: "totem/static/js/app.min.js",
  splitting: true,
  outdir: "totem/static/js/bundles",
  legalComments: "none",
  format: "esm",
  plugins: [solidPlugin()],
  define: {
    "process.env.NODE_ENV": '"production"',
  },
}

if (arg === "watch") {
  options.sourcemap = "inline"
  options.minify = false
  options.define["process.env.NODE_ENV"] = '"development"'
  const ctx = await esbuild.context(options)
  await ctx.watch()
} else {
  const result = await esbuild.build(options)
  fs.writeFileSync("meta.json", JSON.stringify(result.metafile))
}
