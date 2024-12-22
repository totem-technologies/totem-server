import components from "./components"
import bot from "./libs/bot"
import copyToClipboard from "./libs/copyToClipboard"
import emailSpellChecker from "./libs/emailSpellCheck"
import loginChannel from "./libs/loginChannel"
import shadowfill from "./libs/shadowfill"
import timezoneDetect from "./libs/timezone"

import logger from "./libs/logger"

globalThis.dismiss_alert = (e) => {
  e.closest(".alert-dismissible").remove()
}

// Fix for instagram browser errors in sentry
globalThis._AutofillCallbackHandler =
  // eslint-disable-next-line @typescript-eslint/no-empty-function
  globalThis._AutofillCallbackHandler || (() => {})

components()
timezoneDetect()
loginChannel()
copyToClipboard()

globalThis.addEventListener("DOMContentLoaded", () => {
  emailSpellChecker()
  bot()
  shadowfill()
  for (const el of globalThis.document.querySelectorAll(".no-js")) {
    el.remove()
  }
})

globalThis.console.log(
  "Hey! Curious about how Totem works? Check out our open source code at https://github.com/totem-technologies/totem-server. Want to work with us? We'd love to talk to you, send me a message at bo@totem.org."
)
logger(globalThis.TOTEM_DATA.debug)
