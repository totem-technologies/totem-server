#!/usr/bin/env node
import { TS_COMMON_PRESET, TypeScriptGenerator } from "@asyncapi/modelina"

import fs from "fs/promises"

// get first augment as openapi path
// eslint-disable-next-line no-undef
const openapi = process.argv[2]
// eslint-disable-next-line no-undef
const output = "assets/js/models"

const generator = new TypeScriptGenerator({
  moduleSystem: "ESM",
  presets: [
    {
      preset: TS_COMMON_PRESET,
      options: {
        marshalling: true,
      },
    },
  ],
})

async function getOpenAPI() {
  // read from file
  return await fs.readFile(openapi, "utf8")
}

export async function generate() {
  // clear output
  await fs.rm(output, { recursive: true, force: true })
  await fs.mkdir(output, { recursive: true })
  const json = JSON.parse(await getOpenAPI())
  const models = await generator.generateCompleteModels(json)
  for (const model of models) {
    // console.log(model.result)
    await fs.writeFile(`${output}/${model.modelName}.ts`, model.result)
  }
}

generate()
