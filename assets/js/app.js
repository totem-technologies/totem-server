import bot from "./bot"
import components from "./components"
import copyToClipboard from "./copyToClipboard"
import emailSpellChecker from "./emailSpellCheck"
import htmxLoader from "./htmx-loader"
import loginChannel from "./loginChannel"
import shadowfill from "./shadowfill"
import timezoneDetect from "./timezone"

import logger from "./logger"

window.dismiss_alert = function (e) {
  e.closest(".alert-dismissible").remove()
}

components()
timezoneDetect()
htmxLoader()
loginChannel()
copyToClipboard()

window.addEventListener("DOMContentLoaded", () => {
  emailSpellChecker()
  bot()
  shadowfill()
  document.querySelectorAll(".no-js").forEach((el) => {
    // Remove elements with the no-js class
    el.remove()
  })
})

console.log(
  "Hey! Curious about how Totem works? Check out our open source code at https://github.com/totem-technologies/totem-server. Want to work with us? We'd love to talk to you, send me a message at bo@totem.org."
)
logger(window.TOTEM_DATA.debug)
