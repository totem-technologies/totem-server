#!/usr/bin/env node
import * as esbuild from "esbuild"
import { solidPlugin } from "esbuild-plugin-solid"
import fs from "fs"
import process from "process"

var arg = process.argv[2]

var options = {
  entryPoints: ["assets/js/app.js"],
  bundle: true,
  minify: true,
  metafile: true,
  loader: {
    ".svg": "dataurl",
  },
  logLevel: "info",
  sourcemap: true,
  outfile: "totem/static/js/app.min.js",
  legalComments: "none",
  plugins: [solidPlugin()],
  define: {
    "process.env.NODE_ENV": '"production"',
  },
}

if (arg === "watch") {
  options.sourcemap = "inline"
  options.minify = false
  options.define["process.env.NODE_ENV"] = '"development"'
  let ctx = await esbuild.context(options)
  await ctx.watch()
} else {
  const result = await esbuild.build(options)
  fs.writeFileSync("meta.json", JSON.stringify(result.metafile))
}
