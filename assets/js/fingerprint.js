import { load } from "@fingerprintjs/botd"

function setBot(result) {
  window.TOTEM_DATA.bot = result.bot
}

export default function () {
  const botdPromise = load()
  botdPromise
    .then((botd) => botd.detect())
    .then((result) => setBot(result))
    .catch((error) => console.error(error))
}
