import bot from "./bot"
import components from "./components"
import emailSpellChecker from "./emailSpellCheck"
import htmxLoader from "./htmx-loader"
import timezoneDetect from "./timezone"

import logger from "./logger"

dismiss_alert = function (e) {
  e.closest(".alert-dismissible").remove()
}

components()
timezoneDetect()
htmxLoader()
window.addEventListener("DOMContentLoaded", () => {
  emailSpellChecker()
  bot()
})

console.log(
  "Hey! Curious about how Totem works? Check out our open source code at https://github.com/totem-technologies/totem-server. Want to work with us? We'd love to talk to you, send me a message at bo@totem.org."
)
logger(window.TOTEM_DATA.debug)
